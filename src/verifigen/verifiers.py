"""Deterministic verifiers and the async extension protocol."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from .jsonutil import get_path, json_copy
from .types import CheckResult, Context, Violation

Expected = Callable[[dict[str, Any], Context], Any]
Predicate = Callable[[dict[str, Any], Context], bool | None]


class EvidenceUnavailable(ValueError):
    """Missing, conflicting, stale or inapplicable evidence; never silently PASS."""


class Verifier(Protocol):
    @property
    def name(self) -> str: ...

    async def verify(self, candidate: dict[str, Any], context: Context) -> CheckResult: ...


@dataclass(frozen=True)
class FieldVerifier:
    name: str
    target: str
    expected: Expected
    source_paths: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    repairable: bool = True

    def compute(self, candidate: dict[str, Any], context: Context) -> Any:
        return json_copy(self.expected(json_copy(candidate), context))

    async def verify(self, candidate: dict[str, Any], context: Context) -> CheckResult:
        expected = self.compute(candidate, context)
        actual = get_path(candidate, self.target)
        if type(actual) is type(expected) and actual == expected:
            return CheckResult(self.name, "pass")
        return CheckResult(
            self.name,
            "fail",
            Violation(
                "DERIVED_MISMATCH" if self.depends_on else "FACT_MISMATCH",
                self.target,
                "Value differs from its declared evidence or dependencies",
                expected,
                actual,
                self.source_paths,
                self.repairable,
            ),
        )


@dataclass(frozen=True)
class FactVerifier(FieldVerifier):
    """Named convenience class for direct source-to-field bindings."""

    @classmethod
    def from_path(cls, name: str, target: str, source_path: str) -> FactVerifier:
        return cls(
            name, target, lambda _draft, ctx: get_path(ctx.source, source_path), (source_path,)
        )


@dataclass(frozen=True)
class RuleVerifier:
    name: str
    predicate: Predicate
    target: str = "/"
    message: str = "Business rule rejected the candidate"
    source_paths: tuple[str, ...] = ()

    async def verify(self, candidate: dict[str, Any], context: Context) -> CheckResult:
        accepted = self.predicate(candidate, context)
        if accepted is True:
            return CheckResult(self.name, "pass")
        if accepted is not False and accepted is not None:
            raise TypeError("A rule must return bool or None")
        return CheckResult(
            self.name,
            "unknown" if accepted is None else "fail",
            Violation(
                "EVIDENCE_UNKNOWN" if accepted is None else "RULE_VIOLATION",
                self.target,
                self.message,
                source_paths=self.source_paths,
            ),
        )
