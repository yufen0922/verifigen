"""Public data contracts; a PASS is always scoped to declared checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from .jsonutil import digest, freeze, json_copy

Status = Literal["pass", "fail", "unknown"]


@dataclass(frozen=True)
class Context:
    source: Any
    now: datetime
    source_digest: str

    @classmethod
    def create(cls, source: dict[str, Any], now: datetime | None = None) -> Context:
        snapshot = json_copy(source)
        moment = now or datetime.now(UTC)
        if moment.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        return cls(freeze(snapshot), moment, digest(snapshot))


@dataclass(frozen=True)
class Violation:
    code: str
    target: str
    message: str
    expected: Any = None
    actual: Any = None
    source_paths: tuple[str, ...] = ()
    repairable: bool = False


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    status: Status
    violation: Violation | None = None
    method: str = "deterministic"

    def __post_init__(self) -> None:
        if self.status not in ("pass", "fail", "unknown"):
            raise ValueError("Invalid check status")
        if (self.status == "pass") != (self.violation is None):
            raise ValueError("Non-passing checks need a violation; passing checks cannot have one")


@dataclass(frozen=True)
class VerificationReport:
    checks: tuple[CheckResult, ...]

    @property
    def status(self) -> Status:
        if not self.checks or any(check.status == "unknown" for check in self.checks):
            return "unknown"
        return "fail" if any(check.status == "fail" for check in self.checks) else "pass"

    @property
    def violations(self) -> tuple[Violation, ...]:
        return tuple(check.violation for check in self.checks if check.violation is not None)

    def regressions_from(self, previous: VerificationReport) -> tuple[str, ...]:
        after = {check.check_id: check.status for check in self.checks}
        return tuple(
            check.check_id
            for check in previous.checks
            if check.status == "pass" and after.get(check.check_id) != "pass"
        )


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    # Dollar cost is never guessed. An adapter can supply it from configured prices.
    cost_usd: float | None = None

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class Generation:
    content: Any
    usage: Usage = field(default_factory=Usage)
    provider: str = "mock"


@dataclass(frozen=True)
class GenerationRequest:
    source: dict[str, Any]
    prompt: str
    output_schema: dict[str, Any]
    instructions: str
    previous: Any = None
    violations: tuple[Violation, ...] = ()


@dataclass(frozen=True)
class Budget:
    max_model_calls: int = 3
    max_repair_rounds: int = 2
    deadline_seconds: float = 30.0
    # A post-response stop threshold, NOT a prepaid/hard token reservation.
    max_observed_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.max_model_calls < 0 or self.max_repair_rounds < 0:
            raise ValueError("Budgets must be non-negative")
        if self.deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")
        if self.max_observed_tokens is not None and self.max_observed_tokens <= 0:
            raise ValueError("max_observed_tokens must be positive")


@dataclass(frozen=True)
class TraceEvent:
    event: str
    elapsed_ms: float
    details: dict[str, Any]


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: Literal["passed", "fallback"]
    output: dict[str, Any] | None
    text: str
    reason: str
    report: VerificationReport
    trace: tuple[TraceEvent, ...]
    model_calls: int
    repair_rounds: int
    usages: tuple[Usage, ...]
    source_digest: str
    contract_version: str

    def to_dict(self) -> dict[str, Any]:
        """Full reports include source-derived values. Treat this export as sensitive."""
        return asdict(self)
