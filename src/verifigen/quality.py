"""Bounded generate -> judge -> repair -> re-judge orchestration."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from .agents import Judge, Repairer
from .generators import Generator
from .jsonutil import digest, json_copy
from .review import (
    JudgeRequest,
    JudgeVerdict,
    QualityBudget,
    QualityResult,
    QualityTask,
    QualityTraceEvent,
    RepairRequest,
)
from .types import GenerationRequest, Usage

_UNSET = object()


class QualityLoop:
    """Use an LLM judge as the semantic gate and an LLM repairer as the editor."""

    def __init__(
        self,
        *,
        judge: Judge,
        repairer: Repairer,
        generator: Generator | None = None,
        budget: QualityBudget | None = None,
    ) -> None:
        self.judge = judge
        self.repairer = repairer
        self.generator = generator
        self.budget = budget or QualityBudget()

    async def run(self, task: QualityTask, *, initial: Any = _UNSET) -> QualityResult:
        started = time.monotonic()
        run_id = uuid.uuid4().hex
        # Snapshot mutable caller input once. Judge and repair see the same evidence.
        task = replace(
            task,
            source=json_copy(task.source),
            output_schema=json_copy(task.output_schema),
        )
        trace: list[QualityTraceEvent] = []
        verdicts: list[JudgeVerdict] = []
        usages: list[Usage] = []
        model_calls = 0
        in_flight_model_calls = 0
        repair_rounds = 0
        best_candidate: Any | None = None
        best_score = -1.0

        def emit(event: str, **details: Any) -> None:
            trace.append(
                QualityTraceEvent(
                    event,
                    round((time.monotonic() - started) * 1000, 3),
                    details,
                )
            )

        def render(candidate: Any) -> str:
            if task.renderer is not None:
                rendered = task.renderer(json_copy(candidate))
                if not isinstance(rendered, str) or not rendered.strip():
                    raise ValueError("renderer must return non-empty text")
                return rendered
            if isinstance(candidate, str):
                return candidate
            if isinstance(candidate, dict) and isinstance(candidate.get("answer"), str):
                return candidate["answer"]
            return json.dumps(candidate, ensure_ascii=False)

        def finish(reason: str, output: Any | None = None) -> QualityResult:
            passed = output is not None
            if passed:
                try:
                    text = render(output)
                except Exception:
                    passed = False
                    output = None
                    reason = "renderer_error"
                    text = task.fallback_text
            else:
                text = task.fallback_text
            emit("published" if passed else "fallback", reason=reason)
            return QualityResult(
                run_id=run_id,
                status="passed" if passed else "fallback",
                output=json_copy(output),
                best_candidate=json_copy(best_candidate),
                text=text,
                reason=reason,
                verdicts=tuple(verdicts),
                trace=tuple(trace),
                model_calls=model_calls,
                repair_rounds=repair_rounds,
                usages=tuple(usages),
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

        def reserve(component: Any, role: str) -> int:
            nonlocal in_flight_model_calls, model_calls
            cost = getattr(component, "model_calls_per_request", 1)
            if type(cost) is not int or cost < 0:
                raise RuntimeError("invalid_agent_call_cost")
            if model_calls + cost > self.budget.max_model_calls:
                raise RuntimeError("model_budget")
            stop = token_stop()
            if stop:
                raise RuntimeError(stop)
            model_calls += cost
            in_flight_model_calls += cost
            emit("call_started", role=role, model_calls=model_calls)
            return cost

        def complete(cost: int) -> None:
            nonlocal in_flight_model_calls
            in_flight_model_calls -= cost

        async def create_candidate() -> Any:
            if self.generator is None:
                raise RuntimeError("generator_unavailable")
            cost = reserve(self.generator, "generator")
            try:
                generated = await self.generator.generate(
                    GenerationRequest(
                        source=json_copy(task.source),
                        prompt=task.prompt,
                        output_schema=json_copy(task.output_schema),
                        instructions=task.instructions,
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                if cost:
                    usages.append(Usage())
                complete(cost)
                raise RuntimeError("generator_error") from None
            complete(cost)
            usages.append(generated.usage)
            emit(
                "call_finished",
                role="generator",
                provider=generated.provider,
                total_tokens=generated.usage.total_tokens,
            )
            return json_copy(generated.content)

        async def judge(candidate: Any, round_index: int) -> JudgeVerdict:
            nonlocal best_candidate, best_score
            cost = reserve(self.judge, "judge")
            try:
                response = await self.judge.judge(
                    JudgeRequest(task, json_copy(candidate), round_index, tuple(verdicts))
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                if cost:
                    usages.append(Usage())
                complete(cost)
                raise RuntimeError("judge_error") from None
            complete(cost)
            usages.append(response.usage)
            verdicts.append(response.verdict)
            if response.verdict.score > best_score:
                best_score = response.verdict.score
                best_candidate = json_copy(candidate)
            emit(
                "judged",
                round=round_index,
                status=response.verdict.status,
                score=response.verdict.score,
                issue_ids=[issue.criterion_id for issue in response.verdict.issues],
                provider=response.provider,
                total_tokens=response.usage.total_tokens,
            )
            return response.verdict

        async def repair(candidate: Any, verdict: JudgeVerdict, round_index: int) -> Any:
            cost = reserve(self.repairer, "repair")
            try:
                response = await self.repairer.repair(
                    RepairRequest(
                        task,
                        json_copy(candidate),
                        verdict,
                        round_index,
                        tuple(verdicts),
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                if cost:
                    usages.append(Usage())
                complete(cost)
                raise RuntimeError("repair_error") from None
            complete(cost)
            usages.append(response.usage)
            emit(
                "call_finished",
                role="repair",
                provider=response.provider,
                total_tokens=response.usage.total_tokens,
            )
            return json_copy(response.candidate)

        async def execute() -> QualityResult:
            nonlocal repair_rounds, best_candidate
            emit(
                "started",
                criteria=[criterion.id for criterion in task.criteria],
                max_repair_rounds=self.budget.max_repair_rounds,
            )
            try:
                candidate = await create_candidate() if initial is _UNSET else json_copy(initial)
            except (TypeError, ValueError):
                return finish("candidate_not_json")
            except RuntimeError as exc:
                return finish(str(exc))
            best_candidate = json_copy(candidate)
            seen = {digest(candidate)}

            while True:
                try:
                    verdict = await judge(candidate, repair_rounds)
                except RuntimeError as exc:
                    return finish(str(exc))
                stop = token_stop()
                if stop:
                    return finish(stop)
                if verdict.status == "unknown":
                    return finish("judge_unknown")
                if verdict.status == "pass":
                    if verdict.score < self.budget.min_pass_score:
                        return finish("score_below_threshold")
                    return finish("judge_passed", candidate)
                if repair_rounds >= self.budget.max_repair_rounds:
                    return finish("repair_budget")
                repair_rounds += 1
                try:
                    proposed = await repair(candidate, verdict, repair_rounds)
                except RuntimeError as exc:
                    return finish(str(exc))
                proposed_digest = digest(proposed)
                if proposed_digest in seen:
                    return finish("no_progress")
                seen.add(proposed_digest)
                candidate = proposed
                emit("repair_committed", round=repair_rounds, candidate_digest=proposed_digest)

        try:
            return await asyncio.wait_for(execute(), timeout=self.budget.deadline_seconds)
        except TimeoutError:
            # Preserve uncertainty for an in-flight, potentially billable request.
            usages.extend(Usage() for _ in range(in_flight_model_calls))
            return finish("deadline")


def write_quality_trace(result: QualityResult, path: str | Path) -> None:
    """Write metadata-only JSONL; candidate and issue text are deliberately excluded."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for event in result.trace:
            handle.write(
                json.dumps({"run_id": result.run_id, **asdict(event)}, ensure_ascii=False) + "\n"
            )


__all__ = ["QualityLoop", "write_quality_trace"]
