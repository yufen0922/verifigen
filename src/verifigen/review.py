"""Data contracts for the LLM judge-and-repair quality loop."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .jsonutil import json_copy
from .types import Usage

ReviewStatus = Literal["pass", "fail", "unknown"]


@dataclass(frozen=True)
class Criterion:
    """A business-facing requirement that the judge must evaluate."""

    id: str
    description: str

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.description.strip():
            raise ValueError("Criterion id and description are required")


@dataclass(frozen=True)
class JudgeIssue:
    criterion_id: str
    message: str
    evidence: str = ""
    suggestion: str = ""

    def __post_init__(self) -> None:
        if not self.criterion_id.strip() or not self.message.strip():
            raise ValueError("Issue criterion_id and message are required")


@dataclass(frozen=True)
class JudgeVerdict:
    status: ReviewStatus
    score: float
    summary: str
    issues: tuple[JudgeIssue, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in ("pass", "fail", "unknown"):
            raise ValueError("Invalid judge status")
        if not 0 <= self.score <= 1:
            raise ValueError("Judge score must be between 0 and 1")
        if not self.summary.strip():
            raise ValueError("Judge summary is required")
        if self.status == "pass" and self.issues:
            raise ValueError("A passing verdict cannot contain issues")
        if self.status == "fail" and not self.issues:
            raise ValueError("A failing verdict must contain at least one issue")


@dataclass(frozen=True)
class QualityTask:
    """Everything the judge and repairer need to make an in-context decision."""

    source: dict[str, Any]
    prompt: str
    criteria: tuple[Criterion, ...]
    output_schema: dict[str, Any] = field(default_factory=dict)
    instructions: str = ""
    fallback_text: str = "暂时无法生成经过校验的答案，请稍后重试或转人工处理。"
    renderer: Callable[[Any], str] | None = None

    def __post_init__(self) -> None:
        if not self.prompt.strip() or not self.criteria:
            raise ValueError("A task needs a prompt and at least one criterion")
        ids = [criterion.id for criterion in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("Criterion IDs must be unique")
        if not self.fallback_text.strip():
            raise ValueError("fallback_text cannot be empty")
        if self.renderer is not None and not callable(self.renderer):
            raise ValueError("renderer must be callable")
        json_copy(self.source)
        json_copy(self.output_schema)


@dataclass(frozen=True)
class JudgeRequest:
    task: QualityTask
    candidate: Any
    round_index: int
    history: tuple[JudgeVerdict, ...] = ()


@dataclass(frozen=True)
class RepairRequest:
    task: QualityTask
    candidate: Any
    verdict: JudgeVerdict
    round_index: int
    history: tuple[JudgeVerdict, ...] = ()


@dataclass(frozen=True)
class JudgeResponse:
    verdict: JudgeVerdict
    usage: Usage = field(default_factory=Usage)
    provider: str = "custom"


@dataclass(frozen=True)
class RepairResponse:
    candidate: Any
    usage: Usage = field(default_factory=Usage)
    provider: str = "custom"


@dataclass(frozen=True)
class QualityBudget:
    max_model_calls: int = 7
    max_repair_rounds: int = 2
    deadline_seconds: float = 120.0
    min_pass_score: float = 0.8
    max_observed_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.max_model_calls < 0 or self.max_repair_rounds < 0:
            raise ValueError("Budgets must be non-negative")
        if self.deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")
        if not 0 <= self.min_pass_score <= 1:
            raise ValueError("min_pass_score must be between 0 and 1")
        if self.max_observed_tokens is not None and self.max_observed_tokens <= 0:
            raise ValueError("max_observed_tokens must be positive")


@dataclass(frozen=True)
class QualityTraceEvent:
    event: str
    elapsed_ms: float
    details: dict[str, Any]


@dataclass(frozen=True)
class QualityResult:
    run_id: str
    status: Literal["passed", "fallback"]
    output: Any | None
    best_candidate: Any | None
    text: str
    reason: str
    verdicts: tuple[JudgeVerdict, ...]
    trace: tuple[QualityTraceEvent, ...]
    model_calls: int
    repair_rounds: int
    usages: tuple[Usage, ...]

    def to_dict(self) -> dict[str, Any]:
        """Export the full result; source-derived candidate text may be sensitive."""
        return asdict(self)
