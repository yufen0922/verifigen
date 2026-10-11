"""Recompute public paired results without model calls or reviewer self-scoring."""

import argparse
import hashlib
import json
from pathlib import Path

from verifigen.comparison import OPTIMIZED_ARMS, blind_packets, select_cohort, summarize
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
        samples = select_cohort(
            read_jsonl(args.samples),
            per_task=config["per_task"],
            split=config.get("split", "eval"),
            excluded_sources=config.get("excluded_sources", []),
        )
        if [s["id"] for s in samples] != config["selected_case_ids"]:
            raise ValueError("Cohort differs")
        records = read_jsonl(args.results / "records.jsonl")
        arms = config["arms"]
        if not arms or len(arms) != len(set(arms)) or not set(arms).issubset(OPTIMIZED_ARMS):
            raise ValueError("Invalid arm configuration")
        expected = {(s["id"], arm) for s in samples for arm in arms}
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
            runtime = record.get("runtime", {})
            if record["arm"] in ("judge_only", "quality_loop", "refine_verify"):
                if (
                    not 0
                    <= runtime["repair_rounds"]
                    <= config["budget_ceiling"]["max_repair_rounds"]
                ):
                    raise ValueError("Revision ceiling exceeded")
                if (
                    runtime["model_calls"] != record["model_calls"]
                    or runtime["usages"] != record["usages"]
                ):
                    raise ValueError("Runtime accounting differs from the arm record")
                if record["status"] == "passed" and record["arm"] in (
                    "judge_only",
                    "quality_loop",
                    "refine_verify",
                ):
                    if not runtime.get("rounds"):
                        raise ValueError("Verified release has no final judgment")
                    final = runtime["rounds"][-1]
                    if (
                        final["candidate"] != record["output"]
                        or final["effective_verdict"]["status"] != "pass"
                        or final["effective_verdict"]["score"]
                        < config["budget_ceiling"]["min_pass_score"]
                    ):
                        raise ValueError("Release differs from its final passing candidate")
        packets, mapping = blind_packets(samples, records)
        packet_path = args.results / "blind-packets.jsonl"
        # The original pilot published mappings but not standalone input packets.
        if packet_path.exists() or "split" in config:
            stored_packets = read_jsonl(packet_path)
            if sorted(packets, key=lambda r: r["review_id"]) != sorted(
                stored_packets, key=lambda r: r["review_id"]
            ):
                raise ValueError("Anonymous review packets differ from source/candidates")
        stored_mapping = read_jsonl(args.results / "review-mapping.jsonl")
        if sorted(mapping, key=lambda r: (r["id"], r["arm"])) != sorted(
            stored_mapping, key=lambda r: (r["id"], r["arm"])
        ):
            raise ValueError("Review mapping differs from candidates")
        reviews = read_jsonl(args.results / "reviews.jsonl")
        if len(reviews) != len(packets) or {r["review_id"] for r in reviews} != {
            p["review_id"] for p in packets
        }:
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
