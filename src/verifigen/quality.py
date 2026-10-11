"""Bounded generate -> judge -> repair -> re-judge orchestration."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Literal

from .agents import SELF_REFINE_INSTRUCTIONS, AgentResponseError, Judge, Repairer
from .evidence_judge import SOURCE_FIRST_INSTRUCTIONS
from .gates import CandidateGate, SchemaGate
from .generators import Generator, ProviderError
from .jsonutil import digest, json_copy
from .policy import QualityPolicy
from .review import (
    EvidenceAssessment,
    GateReport,
    JudgeIssue,
    JudgeRequest,
    JudgeVerdict,
    QualityBudget,
    QualityResult,
    QualityRound,
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
        policy: QualityPolicy | None = None,
        gates: tuple[CandidateGate, ...] = (),
        judge_history: Literal["full", "none"] = "full",
        initial_refiner: Generator | None = None,
        max_protocol_retries: int = 1,
        refinement_mode: Literal["edit", "source_first"] = "edit",
    ) -> None:
        if judge_history not in ("full", "none"):
            raise ValueError("judge_history must be full or none")
        if refinement_mode not in ("edit", "source_first"):
            raise ValueError("refinement_mode must be edit or source_first")
        if type(max_protocol_retries) is not int or not 0 <= max_protocol_retries <= 1:
            raise ValueError("max_protocol_retries must be 0 or 1")
        self.judge = judge
        self.repairer = repairer
        self.generator = generator
        self.budget = budget or QualityBudget()
        self.policy = policy or QualityPolicy()
        self.gates = tuple(gates)
        self.judge_history = judge_history
        self.initial_refiner = initial_refiner
        self.max_protocol_retries = max_protocol_retries
        self.refinement_mode = refinement_mode

    async def run(
        self,
        task: QualityTask,
        *,
        initial: Any = _UNSET,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> QualityResult:
        started = time.monotonic()
        run_id = uuid.uuid4().hex
        # Snapshot mutable caller input once. Judge and repair see the same evidence.
        task = replace(
            task,
            source=json_copy(task.source),
            output_schema=json_copy(task.output_schema),
            fallback_by_reason=dict(task.fallback_by_reason),
        )
        trace: list[QualityTraceEvent] = []
        verdicts: list[JudgeVerdict] = []
        feedback_history: list[JudgeVerdict] = []
        gate_reports: list[GateReport] = []
        rounds: list[QualityRound] = []
        usages: list[Usage] = []
        model_calls = 0
        in_flight_model_calls = 0
        repair_rounds = 0
        best_candidate: Any | None = None
        best_score = -1.0
        assessments: tuple[EvidenceAssessment, ...] = ()

        def task_snapshot() -> QualityTask:
            # A frozen dataclass does not freeze nested dicts exposed to adapters.
            return replace(
                task,
                source=json_copy(task.source),
                output_schema=json_copy(task.output_schema),
                fallback_by_reason=dict(task.fallback_by_reason),
            )

        observer = on_event

        def observe(event: str, **details: Any) -> None:
            nonlocal observer
            if observer is not None:
                try:
                    observer(
                        json_copy(
                            {
                                "event": event,
                                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                                "details": details,
                            }
                        )
                    )
                except Exception:
                    # Presentation or telemetry failures must not change release decisions.
                    observer = None
                    trace.append(
                        QualityTraceEvent(
                            "observer_error", round((time.monotonic() - started) * 1000, 3), {}
                        )
                    )

        def emit(event: str, **details: Any) -> None:
            trace.append(
                QualityTraceEvent(
                    event,
                    round((time.monotonic() - started) * 1000, 3),
                    details,
                )
            )
            observe(event, **details)

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
                    text = task.fallback_by_reason.get(reason, task.fallback_text)
            else:
                text = task.fallback_by_reason.get(reason, task.fallback_text)
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
                gate_reports=tuple(gate_reports),
                rounds=tuple(rounds),
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

        async def invoke(
            component: Any, role: str, operation: Callable[[int], Awaitable[Any]]
        ) -> Any:
            for attempt in range(self.max_protocol_retries + 1):
                cost = reserve(component, role)
                if attempt:
                    emit("protocol_retry", role=role, attempt=attempt)
                try:
                    response = await operation(attempt)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    usage = (
                        exc.usage
                        if isinstance(exc, (AgentResponseError, ProviderError))
                        else Usage()
                    )
                    if cost:
                        usages.append(usage)
                    complete(cost)
                    category = (
                        exc.category
                        if isinstance(exc, (AgentResponseError, ProviderError))
                        else "component_error"
                    )
                    emit(
                        "call_failed", role=role, category=category, total_tokens=usage.total_tokens
                    )
                    # Only protocol failures with known billing can be retried safely. No
                    # retries of business FAIL/UNKNOWN, HTTP failures or unknown usage.
                    if (
                        isinstance(exc, AgentResponseError)
                        and usage.total_tokens is not None
                        and attempt < self.max_protocol_retries
                    ):
                        continue
                    raise RuntimeError(role + "_error") from None
                complete(cost)
                usages.append(response.usage)
                return response
            raise AssertionError("Unreachable protocol retry state")

        async def create_candidate() -> Any:
            if self.generator is None:
                raise RuntimeError("generator_unavailable")
            generated = await invoke(
                self.generator,
                "generator",
                lambda _attempt: self.generator.generate(  # type: ignore[union-attr]
                    GenerationRequest(
                        source=json_copy(task.source),
                        prompt=task.prompt,
                        output_schema=json_copy(task.output_schema),
                        instructions=task.instructions,
                    )
                ),
            )
            emit(
                "call_finished",
                role="generator",
                provider=generated.provider,
                total_tokens=generated.usage.total_tokens,
            )
            return json_copy(generated.content)

        async def judge(candidate: Any, round_index: int) -> JudgeVerdict:
            nonlocal best_candidate, best_score, assessments
            response = await invoke(
                self.judge,
                "judge",
                lambda attempt: self.judge.judge(
                    JudgeRequest(
                        task_snapshot(),
                        json_copy(candidate),
                        round_index,
                        tuple(feedback_history) if self.judge_history == "full" else (),
                        protocol_retry=bool(attempt),
                    )
                ),
            )
            verdicts.append(response.verdict)
            assessments = response.assessments
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
            response = await invoke(
                self.repairer,
                "repair",
                lambda attempt: self.repairer.repair(
                    RepairRequest(
                        task_snapshot(),
                        json_copy(candidate),
                        verdict,
                        round_index,
                        tuple(feedback_history),
                        protocol_retry=bool(attempt),
                    )
                ),
            )
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
                budget=asdict(self.budget),
                policy=asdict(self.policy),
                judge_history=self.judge_history,
                initial_refinement=self.initial_refiner is not None,
                max_protocol_retries=self.max_protocol_retries,
                refinement_mode=self.refinement_mode,
            )
            try:
                gates = (SchemaGate(task.output_schema), *self.gates)
            except Exception:
                return finish("invalid_schema")
            try:
                candidate = await create_candidate() if initial is _UNSET else json_copy(initial)
            except (TypeError, ValueError):
                return finish("candidate_not_json")
            except RuntimeError as exc:
                return finish(str(exc))
            best_candidate = json_copy(candidate)
            observe("candidate", round=0, candidate=candidate)
            seen = {digest(candidate)}

            if self.initial_refiner is not None:
                if self.budget.max_repair_rounds == 0:
                    return finish("repair_budget")
                repair_rounds += 1
                try:
                    refined = await invoke(
                        self.initial_refiner,
                        "refine",
                        lambda _attempt: self.initial_refiner.generate(  # type: ignore[union-attr]
                            GenerationRequest(
                                source=json_copy(task.source),
                                prompt=task.prompt,
                                output_schema=json_copy(task.output_schema),
                                instructions=(
                                    SOURCE_FIRST_INSTRUCTIONS
                                    if self.refinement_mode == "source_first"
                                    else SELF_REFINE_INSTRUCTIONS
                                )
                                + "\n"
                                + task.instructions,
                                previous=json_copy(candidate),
                            )
                        ),
                    )
                    proposed = json_copy(refined.content)
                except (TypeError, ValueError):
                    return finish("candidate_not_json")
                except RuntimeError as exc:
                    return finish(str(exc))
                emit(
                    "call_finished",
                    role="refine",
                    provider=refined.provider,
                    total_tokens=refined.usage.total_tokens,
                )
                emit("initial_refined", changed=proposed != candidate, round=repair_rounds)
                candidate = proposed
                best_candidate = json_copy(candidate)
                seen.add(digest(candidate))
                observe("candidate", round=repair_rounds, candidate=candidate)

            while True:
                try:
                    verdict = await judge(candidate, repair_rounds)
                except RuntimeError as exc:
                    return finish(str(exc))
                stop = token_stop()
                if stop:
                    return finish(stop)
                effective_verdict = verdict
                if verdict.status != "unknown":
                    gate_issues: list[JudgeIssue] = []
                    for index, gate in enumerate(gates):
                        try:
                            issues = await gate.check(json_copy(candidate), task_snapshot())
                            if not isinstance(issues, tuple) or any(
                                not isinstance(issue, JudgeIssue) for issue in issues
                            ):
                                raise ValueError("Gate must return a tuple of JudgeIssue")
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            emit("gate_error", gate_index=index)
                            return finish("gate_error")
                        gate_issues.extend(issues)
                        gate_reports.append(GateReport(repair_rounds, index, issues))
                        emit("gate_checked", gate_index=index, issue_count=len(issues))
                        if index == 0 and issues:
                            # Business gates may rely on the validated output shape.
                            break
                    if gate_issues:
                        effective_verdict = replace(
                            verdict,
                            status="fail",
                            summary="Deterministic release checks found issues. " + verdict.summary,
                            issues=verdict.issues + tuple(gate_issues),
                        )
                feedback_history.append(effective_verdict)
                reviewed = QualityRound(
                    repair_rounds, json_copy(candidate), verdict, effective_verdict, assessments
                )
                rounds.append(reviewed)
                observe("round_complete", **asdict(reviewed))
                decision = self.policy.decide(
                    effective_verdict,
                    min_pass_score=self.budget.min_pass_score,
                    repair_rounds=repair_rounds,
                    max_repair_rounds=self.budget.max_repair_rounds,
                    history=tuple(feedback_history[:-1]),
                )
                emit(
                    "decision", round=repair_rounds, action=decision.action, reason=decision.reason
                )
                if decision.action == "publish":
                    return finish(decision.reason, candidate)
                if decision.action == "fallback":
                    return finish(decision.reason)
                repair_rounds += 1
                try:
                    proposed = await repair(candidate, effective_verdict, repair_rounds)
                except RuntimeError as exc:
                    return finish(str(exc))
                proposed_digest = digest(proposed)
                if proposed_digest in seen:
                    return finish("no_progress")
                seen.add(proposed_digest)
                candidate = proposed
                observe("candidate", round=repair_rounds, candidate=candidate)
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
