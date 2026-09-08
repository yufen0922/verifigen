"""Minimal *dependency-closed* repair, staged before the runtime commits it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contract import Contract
from .jsonutil import get_path, json_copy, replace_path
from .types import Context, VerificationReport


@dataclass(frozen=True)
class RepairPlan:
    targets: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class Patch:
    candidate: dict[str, Any]
    plan: RepairPlan
    changed_paths: tuple[str, ...]


def stage_repair(
    contract: Contract,
    candidate: dict[str, Any],
    report: VerificationReport,
    context: Context,
) -> Patch | None:
    if report.status == "unknown":
        return None
    roots = {v.target for v in report.violations if v.repairable}
    fields = contract.affected_fields(roots)
    if not fields or any(not field.repairable for field in fields):
        return None
    staged = json_copy(candidate)
    changed = []
    for field in fields:
        expected = field.compute(staged, context)
        actual = get_path(staged, field.target)
        if type(actual) is not type(expected) or actual != expected:
            replace_path(staged, field.target, expected)
            changed.append(field.target)
    if not changed:
        return None
    return Patch(
        staged,
        RepairPlan(
            tuple(field.target for field in fields),
            "Repair incorrect facts and their declared dependents",
        ),
        tuple(changed),
    )
