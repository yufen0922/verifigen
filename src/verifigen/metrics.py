"""Detection metrics that distinguish semantic judgments from abstention and errors."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from random import Random
from typing import Any


def detection_correct(status: str, initial_should_pass: bool) -> bool:
    return status == ("pass" if initial_should_pass else "fail")


def detection_metrics(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    def ratio(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None

    bad = [r for r in records if not r["initial_should_pass"]]
    clean = [r for r in records if r["initial_should_pass"]]
    detected = sum(r["first_judge_status"] == "fail" for r in bad)
    false_alarms = sum(r["first_judge_status"] == "fail" for r in clean)
    correct = sum(
        detection_correct(r["first_judge_status"], r["initial_should_pass"]) for r in records
    )
    counts = dict(Counter(r["first_judge_status"] for r in records))
    precision = ratio(detected, detected + false_alarms)
    recall = ratio(detected, len(bad))
    return {
        "cases": len(records),
        "correct": correct,
        "judge_detection_accuracy": ratio(correct, len(records)),
        "error_detection_recall": recall,
        "false_alarm_rate": ratio(false_alarms, len(clean)),
        "detection_precision": precision,
        "detection_f1": (
            (2 * precision * recall / (precision + recall) if precision + recall else 0.0)
            if precision is not None and recall is not None
            else None
        ),
        "first_status_counts": counts,
        "abstention_rate": ratio(counts.get("unknown", 0), len(records)),
        "call_error_rate": ratio(counts.get("error", 0), len(records)),
    }


def clustered_intervals(
    records: Sequence[dict[str, Any]], *, iterations: int = 1000, seed: int = 600
) -> dict[str, Any]:
    """Percentile bootstrap: resample sources with all their responses together."""
    if iterations < 100:
        raise ValueError("Use at least 100 bootstrap iterations")
    if not records:
        return {"source_groups": 0, "iterations": iterations, "seed": seed, "intervals": {}}
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(record["source_id"], []).append(record)
    clusters = list(groups.values())
    keys = (
        "judge_detection_accuracy",
        "error_detection_recall",
        "false_alarm_rate",
        "detection_f1",
    )
    values: dict[str, list[float]] = {key: [] for key in keys}
    rng = Random(seed)
    for _ in range(iterations):
        sample = [r for group in rng.choices(clusters, k=len(clusters)) for r in group]
        measured = detection_metrics(sample)
        for key in keys:
            if measured[key] is not None:
                values[key].append(measured[key])
    intervals = {}
    for key, observations in values.items():
        observations.sort()
        if observations:
            intervals[key] = [
                observations[int((len(observations) - 1) * 0.025)],
                observations[int((len(observations) - 1) * 0.975)],
            ]
    return {
        "source_groups": len(groups),
        "iterations": iterations,
        "seed": seed,
        "confidence": 0.95,
        "method": "source-cluster percentile bootstrap",
        "intervals": intervals,
    }
