"""Independent field-label scoring. No runtime, verifier, or domain imports.

Gold labels are checked-in fixture data, not the output of the system under test.
The scorer accepts either supported tone, and otherwise requires the annotated
field set and exact JSON types. It is for this controlled-output corpus only.
"""

from __future__ import annotations

from typing import Any


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            result.update(flatten(child, prefix + "/" + escaped))
        return result
    return {prefix: value}


def field_correctness(output: Any, gold: dict[str, Any]) -> dict[str, bool]:
    actual = flatten(output)
    expected = flatten(gold)
    states = {}
    for key, value in expected.items():
        if key == "/tone":
            states[key] = actual.get(key) in ("neutral", "empathetic")
        else:
            states[key] = (
                key in actual and type(actual[key]) is type(value) and actual[key] == value
            )
    states["$field_set"] = set(actual) == set(expected)
    return states


def score_output(output: Any, gold: dict[str, Any] | None) -> bool:
    if gold is None:
        return output is None
    return isinstance(output, dict) and all(field_correctness(output, gold).values())


def regression_counts(before: Any, after: Any, gold: dict[str, Any]) -> tuple[int, int]:
    """Gold-correct fields that become wrong / gold-correct fields before repair.

    Abstentions have no repaired answer and are reported separately, not as
    zero-error successful repairs. The caller excludes them from this statistic.
    """
    was = field_correctness(before, gold)
    now = field_correctness(after, gold)
    denominator = sum(was.values())
    numerator = sum(correct and not now[key] for key, correct in was.items())
    return numerator, denominator


def rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None
