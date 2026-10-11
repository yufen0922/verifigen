"""Correct the historical detection denominator without rerunning the model."""

import json
from pathlib import Path

from verifigen.metrics import detection_correct, detection_metrics
from verifigen.ragtruth import read_jsonl

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    directory = ROOT / "benchmarks/results/qwen3.5-flash-180"
    records = read_jsonl(directory / "records.jsonl")
    summary = json.loads((directory / "summary.json").read_text())
    for record in records:
        record["detection_correct"] = detection_correct(
            record["first_judge_status"], record["initial_should_pass"]
        )
    summary["metric_revision"] = {
        "date": "2026-10-11",
        "previous_detection_accuracy": 175 / 180,
        "corrected_detection_accuracy": 173 / 180,
        "reason": "Two failed Judge calls were previously counted as correct detections. Only exact pass/fail judgments count as correct; unknown/error never do.",
        "affected_ids": [
            "support--approved--wrong_order_id",
            "support--settled--wrong_paid_amount",
        ],
        "model_outputs_changed": False,
    }
    summary["overall"].update(detection_metrics(records))
    for scenario in summary["scenarios"]:
        summary["scenarios"][scenario].update(
            detection_metrics([r for r in records if r["scenario"] == scenario])
        )
    (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (directory / "records.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records),
        encoding="utf-8",
    )
    print(json.dumps(summary["metric_revision"], indent=2))


if __name__ == "__main__":
    main()
