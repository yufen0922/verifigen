"""Independent, deterministic oracles for non-RAG evaluation scenarios."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _has_exact_keys(value: Any, keys: set[str]) -> bool:
    return isinstance(value, Mapping) and set(value) == keys


def _contains_any(value: Any, phrases: list[str]) -> bool:
    if isinstance(value, str):
        return any(phrase in value for phrase in phrases)
    if isinstance(value, Mapping):
        return any(_contains_any(item, phrases) for item in value.values())
    if isinstance(value, list):
        return any(_contains_any(item, phrases) for item in value)
    return False


def inspect_support_output(output: Any, case: Mapping[str, Any]) -> tuple[str, ...]:
    """Return failed criterion IDs without importing task or agent code."""
    expected = case.get("expected")
    if not isinstance(expected, Mapping):
        return ("general",)
    top_keys = {
        "order_id",
        "paid_cents",
        "order_status",
        "refund_state",
        "refund_cents",
        "next_step",
        "tone",
        "sections",
    }
    section_keys = {"payment", "fulfillment", "refund", "next_step"}
    failures: list[str] = []
    if not _has_exact_keys(output, top_keys) or not _has_exact_keys(
        output.get("sections") if isinstance(output, Mapping) else None, section_keys
    ):
        failures.append("consistency")
    if not isinstance(output, Mapping):
        return tuple(failures or ["consistency"])
    if any(
        output.get(key) != expected.get(key) for key in ("order_id", "paid_cents", "order_status")
    ):
        failures.append("factual_grounding")
    if any(output.get(key) != expected.get(key) for key in ("refund_state", "refund_cents")):
        failures.append("refund_status")
    if output.get("next_step") != expected.get("next_step"):
        failures.append("next_action")
    if output.get("sections") != expected.get("sections"):
        failures.append("consistency")
    if output.get("tone") not in ("neutral", "empathetic"):
        failures.append("consistency")
    forbidden = case.get("forbidden_phrases", [])
    if isinstance(forbidden, list) and _contains_any(output, forbidden):
        failures.append("safety")
    return tuple(dict.fromkeys(failures))


def score_support_output(output: Any, case: Mapping[str, Any]) -> bool:
    return not inspect_support_output(output, case)


def inspect_report_output(output: Any, case: Mapping[str, Any]) -> tuple[str, ...]:
    """Return failed criterion IDs for a structured data-to-text result."""
    expected = case.get("expected")
    if not isinstance(expected, Mapping):
        return ("general",)
    keys = {
        "metric_name",
        "current",
        "previous",
        "delta",
        "direction",
        "change_rate_percent",
        "sentence",
    }
    failures: list[str] = []
    if not _has_exact_keys(output, keys):
        failures.append("consistency")
    if not isinstance(output, Mapping):
        return tuple(failures or ["consistency"])
    if any(output.get(key) != expected.get(key) for key in ("metric_name", "current", "previous")):
        failures.append("numeric_fidelity")
    if any(
        output.get(key) != expected.get(key)
        for key in ("delta", "direction", "change_rate_percent")
    ):
        failures.append("derivation")
    source = case.get("source", {})
    sentence = output.get("sentence")
    if not isinstance(sentence, str) or any(
        not isinstance(source.get(key), str) or source[key] not in sentence
        for key in ("metric_name", "unit", "current_period", "previous_period")
    ):
        failures.append("unit_fidelity")
    if sentence != expected.get("sentence"):
        failures.append("consistency")
    forbidden = case.get("forbidden_phrases", [])
    if isinstance(forbidden, list) and _contains_any(output, forbidden):
        failures.append("restraint")
    return tuple(dict.fromkeys(failures))


def score_report_output(output: Any, case: Mapping[str, Any]) -> bool:
    return not inspect_report_output(output, case)


__all__ = [
    "inspect_report_output",
    "inspect_support_output",
    "score_report_output",
    "score_support_output",
]
