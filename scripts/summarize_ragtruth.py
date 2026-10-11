"""Audit completed live records with grouped uncertainty and measured costs."""

import argparse
import hashlib
import json
from pathlib import Path

from verifigen.metrics import clustered_intervals, detection_metrics
from verifigen.ragtruth import TASKS, read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results", type=Path, default=Path("benchmarks/results/ragtruth-qwen3.5-flash")
    )
    args = parser.parse_args()
    records = read_jsonl(args.results / "records.jsonl")
    summary = json.loads((args.results / "summary.json").read_text())
    assert {r["id"] for r in records} == set(summary["selected_case_ids"])
    assert len(records) == len(summary["selected_case_ids"])
    summary["overall"] = detection_metrics(records)
    summary["source_cluster_bootstrap"] = clustered_intervals(records)
    if "runtime_file_audit" not in summary:
        root = Path(__file__).resolve().parents[1] / "src/verifigen"
        names = (
            "agents.py",
            "generators.py",
            "quality.py",
            "review.py",
            "policy.py",
            "gates.py",
            "ragtruth.py",
        )
        summary["runtime_file_audit"] = {
            "timing": "Post-run local code audit; not a provider model snapshot identifier.",
            "sha256": {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names
            },
        }
    summary["tasks"] = {
        task: detection_metrics([r for r in records if r["task_type"] == task]) for task in TASKS
    }
    latencies = sorted(r["trace"][-1]["elapsed_ms"] / 1000 for r in records)
    summary["latency_seconds"] = {
        "mean": sum(latencies) / len(latencies),
        "p50": latencies[int((len(latencies) - 1) * 0.50)],
        "p95": latencies[int((len(latencies) - 1) * 0.95)],
        "note": "Per-run wall time excluding local concurrency queue; includes every repair and re-judge.",
    }
    published_initial = [r for r in records if r["first_judge_status"] == "pass"]
    summary["judge_only_baseline"] = {
        "released": len(published_initial),
        "wrong_releases": sum(not r["initial_should_pass"] for r in published_initial),
        "coverage": len(published_initial) / len(records),
        "release_label_precision": sum(r["initial_should_pass"] for r in published_initial)
        / len(published_initial)
        if published_initial
        else None,
        "note": "Original response label scored after first Judge pass only; no score threshold or other runtime decision simulated.",
    }
    summary["direct_output_baseline"] = {
        "hallucinated_responses": sum(not r["initial_should_pass"] for r in records),
        "hallucination_rate": sum(not r["initial_should_pass"] for r in records) / len(records),
        "note": "Controlled balanced cohort; not natural prevalence.",
    }
    (args.results / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "selected_case_ids"}, indent=2))


if __name__ == "__main__":
    main()
