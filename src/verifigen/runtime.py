"""Run-local state, bounded generation, transactional repair and fail-closed output."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

from .contract import Contract
from .generators import Generator
from .jsonutil import digest, json_copy, thaw
from .repair import stage_repair
from .types import (
    Budget,
    Context,
    GenerationRequest,
    RunResult,
    TraceEvent,
    Usage,
    VerificationReport,
)

_UNSET = object()


class Harness:
    def __init__(
        self,
        contract: Contract,
        generator: Generator | None = None,
        *,
        budget: Budget | None = None,
        repair_mode: Literal["dependency", "regenerate"] = "dependency",
    ) -> None:
        if repair_mode not in ("dependency", "regenerate"):
            raise ValueError("Invalid repair mode")
        self.contract = contract
        self.generator = generator
        self.budget = budget or Budget()
        self.repair_mode = repair_mode

    async def run(
        self,
        *,
        source: dict[str, Any],
        prompt: str = "Generate an evidence-grounded response.",
        initial: Any = _UNSET,
        context: Context | None = None,
    ) -> RunResult:
        started = time.monotonic()
        ctx = context or Context.create(source)
        if context is not None and digest(source) != ctx.source_digest:
            raise ValueError("The supplied context must describe the same source snapshot")
        events: list[TraceEvent] = []
        usages: list[Usage] = []
        report = VerificationReport(())
        model_calls = 0
        repair_rounds = 0
        run_id = uuid.uuid4().hex

        def current_context() -> Context:
            # Advance even a replay clock while the request runs. Evidence that
            # expires during generation must not pass using its initial age.
            return Context(
                ctx.source,
                ctx.now + timedelta(seconds=time.monotonic() - started),
                ctx.source_digest,
            )

        def emit(event: str, **details: Any) -> None:
            events.append(TraceEvent(event, round((time.monotonic() - started) * 1000, 3), details))

        def finish(reason: str, output: dict[str, Any] | None = None) -> RunResult:
            passed = output is not None
            try:
                rendered = (
                    self.contract.render(json_copy(output))
                    if passed
                    else self.contract.fallback_text
                )
                if not isinstance(rendered, str) or not rendered.strip():
                    raise ValueError("Empty renderer result")
            except Exception:
                passed, output, reason = False, None, "renderer_error"
                rendered = self.contract.fallback_text
            emit("done" if passed else "fallback", reason=reason)
            return RunResult(
                run_id,
                "passed" if passed else "fallback",
                json_copy(output),
                rendered,
                reason,
                report,
                tuple(events),
                model_calls,
                repair_rounds,
                tuple(usages),
                ctx.source_digest,
                self.contract.version,
            )

        def token_stop() -> str | None:
            limit = self.budget.max_observed_tokens
            if limit is None:
                return None
            if any(usage.total_tokens is None for usage in usages):
                return "usage_unknown"
            if sum(usage.total_tokens or 0 for usage in usages) >= limit:
                return "token_threshold"
            return None

        async def generate(previous: Any = None) -> Any:
            nonlocal model_calls
            if self.generator is None:
                raise RuntimeError("generator_unavailable")
            if model_calls >= self.budget.max_model_calls:
                raise RuntimeError("model_budget")
            stop = token_stop()
            if stop:
                raise RuntimeError(stop)
            model_calls += 1  # Include attempted/failed requests in the call budget.
            emit("generate", call=model_calls)
            try:
                generation = await self.generator.generate(
                    GenerationRequest(
                        source=thaw(ctx.source),
                        prompt=prompt,
                        output_schema=self.contract.schema.model_json_schema(),
                        instructions=self.contract.instructions,
                        previous=json_copy(previous),
                        violations=report.violations,
                    )
                )
            except Exception:
                # A failed request can still be billable; unknown is not zero.
                usages.append(Usage())
                raise RuntimeError("provider_error") from None
            usages.append(generation.usage)
            emit("generated", call=model_calls, total_tokens=generation.usage.total_tokens)
            try:
                return json_copy(generation.content)
            except (ValueError, TypeError):
                raise RuntimeError("candidate_not_json") from None

        async def execute() -> RunResult:
            nonlocal report, repair_rounds
            emit("start", contract_version=self.contract.version, source_digest=ctx.source_digest)
            evidence = self.contract.check_evidence(current_context())
            if evidence.status != "pass":
                report = VerificationReport((evidence,))
                return finish("evidence_unavailable")
            try:
                candidate = await generate() if initial is _UNSET else json_copy(initial)
            except RuntimeError as exc:
                return finish(str(exc))
            except (TypeError, ValueError):
                return finish("candidate_not_json")
            seen = {digest(candidate)}
            report = await self.contract.verify(candidate, current_context())
            emit(
                "verify",
                status=report.status,
                failed_checks=[c.check_id for c in report.checks if c.status != "pass"],
            )
            while True:
                stop = token_stop()
                if stop:
                    return finish(stop)
                if report.status == "pass":
                    fresh = self.contract.check_evidence(current_context())
                    if fresh.status != "pass":
                        report = VerificationReport((fresh,))
                        return finish("evidence_unavailable")
                    return finish("verified", candidate)
                if report.status == "unknown":
                    return finish("verification_unknown")
                if repair_rounds >= self.budget.max_repair_rounds:
                    return finish("repair_budget")
                repair_rounds += 1
                patch = None
                if self.repair_mode == "dependency" and isinstance(candidate, dict):
                    try:
                        patch = stage_repair(self.contract, candidate, report, current_context())
                    except Exception:
                        emit("patch_unavailable")
                if patch is not None:
                    proposed = patch.candidate
                    emit(
                        "repair_staged",
                        mode="dependency",
                        affected_paths=list(patch.plan.targets),
                        changed_paths=list(patch.changed_paths),
                    )
                else:
                    try:
                        proposed = await generate(candidate)
                        emit("repair_staged", mode="regenerate")
                    except RuntimeError as exc:
                        return finish(str(exc))
                proposed_digest = digest(proposed)
                if proposed_digest in seen:
                    return finish("no_progress")
                seen.add(proposed_digest)
                after = await self.contract.verify(proposed, current_context())
                regressions = after.regressions_from(report)
                emit(
                    "reverify",
                    status=after.status,
                    regressions=list(regressions),
                    failed_checks=[c.check_id for c in after.checks if c.status != "pass"],
                )
                if after.status == "unknown":
                    emit("rollback", reason="unknown")
                    return finish("verification_unknown")
                if regressions:
                    emit("rollback", reason="regression", check_ids=list(regressions))
                    return finish("repair_regression")
                candidate, report = proposed, after
                emit("repair_committed", candidate_digest=proposed_digest)

        try:
            return await asyncio.wait_for(execute(), timeout=self.budget.deadline_seconds)
        except TimeoutError:
            # asyncio cancellation propagates into a cooperative adapter/verifier.
            # A provider may still bill a request already received.
            if model_calls > len(usages):
                usages.append(Usage())
            return finish("deadline")


def write_trace(result: RunResult, path: str | Path) -> None:
    """Metadata-only JSONL; unlike RunResult.to_dict(), excludes fact values/text."""
    import json

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for event in result.trace:
            handle.write(
                json.dumps({"run_id": result.run_id, **asdict(event)}, ensure_ascii=False) + "\n"
            )
