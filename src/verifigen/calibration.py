"""Development-only release-threshold diagnostics, not probability calibration."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


def threshold_curve(
    records: Sequence[dict[str, Any]],
    samples: Sequence[dict[str, Any]],
    thresholds: Sequence[float] = (0.0, 0.5, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0),
) -> dict[str, Any]:
    if not records:
        raise ValueError("Need development records")
    indexed = {s["id"]: s for s in samples}
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("Duplicate development records")
    for record in records:
        sample = indexed.get(record["id"])
        if sample is None or sample["local_split"] != "dev":
            raise ValueError("Threshold tuning must use development IDs only")
        if record["initial_should_pass"] != (not sample["has_hallucination"]):
            raise ValueError("Original label differs from the frozen sample")
    if not thresholds or any(not math.isfinite(t) or not 0 <= t <= 1 for t in thresholds):
        raise ValueError("Thresholds must be finite and in [0, 1]")
    rows = []
    for threshold in sorted(set(thresholds)):
        released = []
        for record in records:
            verdicts = record.get("verdicts", [])
            gates = [g for g in record.get("gate_reports", []) if g["round_index"] == 0]
            if (
                verdicts
                and verdicts[0]["status"] == "pass"
                and verdicts[0]["score"] >= threshold
                and not any(g["issues"] for g in gates)
            ):
                released.append(record)
        clean = sum(r["initial_should_pass"] for r in released)
        wrong = len(released) - clean
        rows.append(
            {
                "threshold": threshold,
                "released": len(released),
                "clean_released": clean,
                "hallucinated_released": wrong,
                "coverage": len(released) / len(records),
                "release_label_precision": clean / len(released) if released else None,
                "wrong_release_rate": wrong / len(released) if released else None,
            }
        )
    return {
        "split": "dev",
        "cases": len(records),
        "curve": rows,
        "automatically_selected_threshold": None,
        "note": "Empirical threshold sensitivity only. Scores are not calibrated probabilities; choose a risk/coverage target on development data and validate a frozen threshold separately. Small samples cannot establish rare-error safety.",
    }
