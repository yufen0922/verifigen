"""Deterministic release checks complement the LLM's semantic judgment."""

from __future__ import annotations

from itertools import islice
from typing import Any, Protocol

from jsonschema import Draft202012Validator
from referencing import Registry

from .jsonutil import json_copy
from .review import JudgeIssue, QualityTask


class CandidateGate(Protocol):
    """Return repairable issues, or raise when a check cannot be completed.

    Implementations must be stateless (or concurrency-safe) and cooperative
    async functions. They receive isolated candidate and task snapshots.
    """

    async def check(self, candidate: Any, task: QualityTask) -> tuple[JudgeIssue, ...]: ...


class SchemaGate:
    """Validate Draft 2020-12 schemas without retrieving external references."""

    def __init__(self, schema: dict[str, Any]) -> None:
        schema = json_copy(schema)
        dialect = schema.get("$schema", "https://json-schema.org/draft/2020-12/schema")
        if dialect.rstrip("#") != "https://json-schema.org/draft/2020-12/schema":
            raise ValueError("Only JSON Schema Draft 2020-12 is supported")
        Draft202012Validator.check_schema(schema)
        # An explicit empty registry disables implicit network retrieval.
        self._validator = Draft202012Validator(schema, registry=Registry())

    async def check(self, candidate: Any, task: QualityTask) -> tuple[JudgeIssue, ...]:
        issues = []
        for error in islice(self._validator.iter_errors(candidate), 20):
            pointer = "".join(
                "/" + str(part).replace("~", "~0").replace("/", "~1")
                for part in error.absolute_path
            )
            issues.append(
                JudgeIssue(
                    "general",
                    f"Output schema violation at {pointer or '/'}: {error.message}",
                    evidence=f"JSON Schema keyword: {error.validator}",
                    suggestion="Match the declared output schema without inventing facts.",
                )
            )
        return tuple(issues)


__all__ = ["CandidateGate", "SchemaGate"]
