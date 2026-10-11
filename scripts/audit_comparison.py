"""Recompute public paired results without model calls or reviewer self-scoring."""

import argparse
import hashlib
import json
from pathlib import Path

from verifigen.comparison import ARMS, blind_packets, select_cohort, summarize
from verifigen.ragtruth import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results", type=Path, default=Path("benchmarks/results/ragtruth-comparison-60")
    )
    parser.add_argument(
        "--samples", type=Path, default=Path("benchmarks/data/ragtruth-600/samples.jsonl")
    )
    args = parser.parse_args()
    try:
        config = json.loads((args.results / "config.json").read_text())
        if config["samples_sha256"] != hashlib.sha256(args.samples.read_bytes()).hexdigest():
            raise ValueError("Dataset hash differs")
        samples = select_cohort(read_jsonl(args.samples), per_task=config["per_task"])
        if [s["id"] for s in samples] != config["selected_case_ids"]:
            raise ValueError("Cohort differs")
        records = read_jsonl(args.results / "records.jsonl")
        expected = {(s["id"], arm) for s in samples for arm in ARMS}
        actual = {(r["id"], r["arm"]) for r in records}
        if expected != actual or len(actual) != len(records):
            raise ValueError("Missing, duplicate or unexpected arm records")
        indexed = {s["id"]: s for s in samples}
        for record in records:
            sample = indexed[record["id"]]
            if (
                record["initial_should_pass"] != (not sample["has_hallucination"])
                or record["source_id"] != sample["source_id"]
                or record["task_type"] != sample["task_type"]
            ):
                raise ValueError("Original labels or source identifiers differ")
            if not 0 <= record["model_calls"] <= config["budget_ceiling"]["max_model_calls"]:
                raise ValueError("Runtime call ceiling exceeded")
            if record["status"] != "passed" and record["output"] is not None:
                raise ValueError("Fallback contains a released candidate")
        packets, mapping = blind_packets(samples, records)
        stored_mapping = read_jsonl(args.results / "review-mapping.jsonl")
        if sorted(mapping, key=lambda r: (r["id"], r["arm"])) != sorted(
            stored_mapping, key=lambda r: (r["id"], r["arm"])
        ):
            raise ValueError("Review mapping differs from candidates")
        reviews = read_jsonl(args.results / "reviews.jsonl")
        if {r["review_id"] for r in reviews} != {p["review_id"] for p in packets}:
            raise ValueError("Review set incomplete")
        expected_summary = {"config": config, **summarize(records, mapping, reviews)}
        if json.loads((args.results / "summary.json").read_text()) != expected_summary:
            raise ValueError("Summary differs from recomputed records")
        print(
            f"Audited {len(samples)} paired cases, {len(records)} arm records and {len(reviews)} anonymous reviews; no model calls."
        )
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(2, f"Audit failed: {exc}\n")


if __name__ == "__main__":
    main()
