"""Recheck an observed released failure with current prompts; not a new holdout benchmark."""

import argparse
import asyncio
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from verifigen.comparison import blind_packets, review_packet
from verifigen.config import ModelSettings
from verifigen.generators import CompatibleChatGenerator
from verifigen.quality import QualityLoop
from verifigen.ragtruth import make_ragtruth_task, read_jsonl
from verifigen.review import QualityBudget

ROOT = Path(__file__).resolve().parents[2]


async def run(args: argparse.Namespace) -> None:
    if args.output.exists():
        raise ValueError("Use a new output file; do not overwrite evidence")
    samples_path = ROOT / "benchmarks/data/ragtruth-600/samples.jsonl"
    samples = read_jsonl(samples_path)
    sample = next((s for s in samples if s["id"] == args.case_id), None)
    baseline = next(
        (
            r
            for r in read_jsonl(args.records)
            if r["id"] == args.case_id and r["arm"] == "quality_loop"
        ),
        None,
    )
    if sample is None or baseline is None or baseline["output"] is None:
        raise ValueError("Need an existing released candidate for this case")
    settings = ModelSettings.from_env(ROOT / ".env.local")
    stack = settings.stack()
    budget = QualityBudget(max_model_calls=5, max_repair_rounds=2, max_observed_tokens=24000)
    result = await QualityLoop(judge=stack.judge, repairer=stack.repairer, budget=budget).run(
        make_ragtruth_task(sample), initial=baseline["output"]
    )
    row = {"id": sample["id"], "arm": "quality_loop", **result.to_dict()}
    packets, _ = blind_packets(samples, [row])
    external = None
    if packets:
        reviewer = CompatibleChatGenerator(
            base_url=settings.base_url,
            api_key=settings.api_key,
            model="qwen-plus",
            timeout=90,
            max_output_tokens=4096,
        )
        external = await review_packet(packets[0], reviewer)
    output = {
        "kind": "targeted_known_failure_regression_not_holdout_accuracy",
        "case_id": sample["id"],
        "model": settings.model,
        "reviewer_model": "qwen-plus",
        "source_sha256": hashlib.sha256(samples_path.read_bytes()).hexdigest(),
        "agents_sha256": hashlib.sha256(
            (ROOT / "src/verifigen/agents.py").read_bytes()
        ).hexdigest(),
        "baseline_record_sha256": hashlib.sha256(args.records.read_bytes()).hexdigest(),
        "budget": asdict(budget),
        "initial": baseline["output"],
        "result": result.to_dict(),
        "external_review": external,
        "human_review_status": "pending",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "case_id": sample["id"],
                "status": result.status,
                "reason": result.reason,
                "runtime_calls": result.model_calls,
                "external_review": external,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--records",
        type=Path,
        default=ROOT / "benchmarks/results/ragtruth-comparison-60/records.jsonl",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Recheck failed: {exc}\n")


if __name__ == "__main__":
    main()
