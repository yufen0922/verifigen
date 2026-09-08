"""Compiled contract with an explicit acyclic field dependency graph."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from .jsonutil import json_copy, parts
from .types import CheckResult, Context, VerificationReport, Violation
from .verifiers import EvidenceUnavailable, FieldVerifier, Verifier


@dataclass(frozen=True)
class Contract:
    schema: type[BaseModel]
    verifiers: Sequence[Verifier]
    render: Callable[[dict[str, Any]], str]
    version: str = "1"
    instructions: str = "Return an object matching the supplied JSON schema."
    preflight: Callable[[Context], None] | None = None
    fallback_text: str = "暂时无法确认相关信息，请联系人工客服核实。"

    def __post_init__(self) -> None:
        object.__setattr__(self, "verifiers", tuple(self.verifiers))
        names = [verifier.name for verifier in self.verifiers]
        if not names or len(names) != len(set(names)) or {"schema", "evidence"} & set(names):
            raise ValueError("Use unique verifier names, excluding 'schema' and 'evidence'")
        fields = [v for v in self.verifiers if isinstance(v, FieldVerifier)]
        targets = [v.target for v in fields]
        if len(targets) != len(set(targets)):
            raise ValueError("A target must have exactly one authoritative field verifier")
        for verifier in fields:
            parts(verifier.target)
            for dependency in verifier.depends_on:
                parts(dependency)
        self.topological_fields()  # Fail fast on a cycle at construction.

    def topological_fields(self) -> tuple[FieldVerifier, ...]:
        fields = {v.target: v for v in self.verifiers if isinstance(v, FieldVerifier)}
        ordered: list[FieldVerifier] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(target: str) -> None:
            if target in visiting:
                raise ValueError(f"Dependency cycle at {target}")
            if target in visited:
                return
            visiting.add(target)
            for dep in fields[target].depends_on:
                if dep in fields:
                    visit(dep)
            visiting.remove(target)
            visited.add(target)
            ordered.append(fields[target])

        for target in fields:
            visit(target)
        return tuple(ordered)

    def affected_fields(self, roots: set[str]) -> tuple[FieldVerifier, ...]:
        affected = set(roots)
        result = []
        for verifier in self.topological_fields():
            if verifier.target in affected or affected.intersection(verifier.depends_on):
                affected.add(verifier.target)
                result.append(verifier)
        return tuple(result)

    def check_evidence(self, context: Context) -> CheckResult:
        try:
            if self.preflight is not None:
                self.preflight(context)
        except (EvidenceUnavailable, KeyError, IndexError, ValidationError, ValueError):
            return CheckResult(
                "evidence",
                "unknown",
                Violation(
                    "EVIDENCE_UNAVAILABLE",
                    "/",
                    "Evidence is missing, stale, conflicting or invalid",
                ),
            )
        except Exception:
            return CheckResult(
                "evidence",
                "unknown",
                Violation("VERIFIER_ERROR", "/", "Evidence validator raised an exception"),
            )
        return CheckResult("evidence", "pass")

    async def verify(self, candidate: Any, context: Context) -> VerificationReport:
        evidence = self.check_evidence(context)
        if evidence.status != "pass":
            return VerificationReport((evidence,))
        try:
            # Validate the exact object; do not publish Pydantic-coerced data.
            self.schema.model_validate(candidate, strict=True)
        except (ValidationError, TypeError, ValueError):
            return VerificationReport(
                (
                    evidence,
                    CheckResult(
                        "schema",
                        "fail",
                        Violation(
                            "SCHEMA_INVALID", "/", "Candidate does not match the output schema"
                        ),
                    ),
                )
            )

        async def check(verifier: Verifier) -> CheckResult:
            try:
                # Every verifier receives an isolated candidate; accidental mutation cannot
                # change another verifier's verdict or the value eventually published.
                result = await verifier.verify(json_copy(candidate), context)
                if not isinstance(result, CheckResult) or result.check_id != verifier.name:
                    raise TypeError("Verifier returned an invalid result")
                return result
            except (EvidenceUnavailable, KeyError, IndexError):
                return CheckResult(
                    verifier.name,
                    "unknown",
                    Violation(
                        "EVIDENCE_UNAVAILABLE", "/", "Required evidence or target is unavailable"
                    ),
                )
            except Exception:
                # Exception messages can contain source values or credentials; do not log them.
                return CheckResult(
                    verifier.name,
                    "unknown",
                    Violation("VERIFIER_ERROR", "/", "Verifier raised an exception"),
                )

        checks = await asyncio.gather(*(check(verifier) for verifier in self.verifiers))
        return VerificationReport((evidence, CheckResult("schema", "pass"), *checks))
