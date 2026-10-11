"""Live evaluation with source-grouped data and resumable per-response records."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from verifigen import QualityBudget, QualityLoop
from verifigen.config import ModelSettings
from verifigen.metrics import detection_correct, detection_metrics
from verifigen.ragtruth import TASKS, make_ragtruth_task, read_jsonl

ROOT = Path(__file__).resolve().parents[2]


async def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    settings = ModelSettings.from_env(ROOT / ".env.local")
    stack = settings.stack(
        thinking_budget=args.thinking_budget,
        enable_thinking=args.enable_thinking,
        validate_judge_quotes=args.validate_judge_quotes,
    )
    budget = QualityBudget(
        max_model_calls=args.max_model_calls,
        max_repair_rounds=args.max_repair_rounds,
        deadline_seconds=120,
    )
    all_samples = read_jsonl(args.samples)
    selected = []
    for task in TASKS:
        eligible = [
            r for r in all_samples if r["task_type"] == task and r["local_split"] == args.split
        ]
        half = args.limit_per_task // 2
        for bad in (False, True):
            pool = [r for r in eligible if r["has_hallucination"] == bad]
            if len(pool) < half:
                raise ValueError("Requested cohort exceeds available task/label samples")
            selected.extend(pool[:half])
    args.output.mkdir(parents=True, exist_ok=True)
    records_path = args.output / "records.jsonl"
    config = {
        "model": settings.model,
        "samples_sha256": hashlib.sha256(args.samples.read_bytes()).hexdigest(),
        "split": args.split,
        "limit_per_task": args.limit_per_task,
        "thinking_budget": args.thinking_budget,
        "enable_thinking": args.enable_thinking,
        "validate_judge_quotes": args.validate_judge_quotes,
        "budget": asdict(budget),
        "selected_case_ids": [r["id"] for r in selected],
    }
    config_path = args.output / "config.json"
    records: list[dict[str, Any]] = []
    if records_path.exists():
        if not args.resume:
            raise ValueError("Output already exists; use a new directory or --resume")
        if not config_path.exists() or json.loads(config_path.read_text()) != config:
            raise ValueError("Cannot resume a different model, configuration or cohort")
        records = read_jsonl(records_path)
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    completed = {r["id"] for r in records}
    semaphore = asyncio.Semaphore(args.concurrency)

    async def one(sample: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            result = await QualityLoop(
                judge=stack.judge, repairer=stack.repairer, budget=budget
            ).run(make_ragtruth_task(sample), initial={"answer": sample["response"]})
            first = result.verdicts[0].status if result.verdicts else "error"
            return {
                "id": sample["id"],
                "source_id": sample["source_id"],
                "task_type": sample["task_type"],
                "initial_should_pass": not sample["has_hallucination"],
                "first_judge_status": first,
                "detection_correct": detection_correct(first, not sample["has_hallucination"]),
                "final_review": "pending_independent_review",
                **result.to_dict(),
            }

    tasks = [asyncio.create_task(one(r)) for r in selected if r["id"] not in completed]
    try:
        for future in asyncio.as_completed(tasks):
            record = await future
            with records_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            records.append(record)
            if len(records) % 10 == 0 or len(records) == len(selected):
                print(f"completed {len(records)}/{len(selected)}", flush=True)
    finally:
        for future in tasks:
            if not future.done():
                future.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    summary = {
        "dataset": "RAGTruth-600",
        "run_date": datetime.now(UTC).isoformat(),
        **config,
        "concurrency": args.concurrency,
        "overall": detection_metrics(records),
        "tasks": {t: detection_metrics([r for r in records if r["task_type"] == t]) for t in TASKS},
        "model_calls": sum(r["model_calls"] for r in records),
        "tokens": sum(
            u["input_tokens"] + u["output_tokens"]
            for r in records
            for u in r["usages"]
            if u["input_tokens"] is not None and u["output_tokens"] is not None
        ),
        "unknown_usage_records": sum(
            any(u["input_tokens"] is None or u["output_tokens"] is None for u in r["usages"])
            for r in records
        ),
        "fallback_rate": sum(r["status"] == "fallback" for r in records) / len(records),
        "repair_success_rate": None,
        "note": "Original human labels score first judgments only. Final repaired candidates require new independent review; no repair success claim is made.",
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--samples", type=Path, default=ROOT / "benchmarks/data/ragtruth-600/samples.jsonl"
    )
    parser.add_argument("--split", choices=("dev", "eval"), default="eval")
    parser.add_argument("--limit-per-task", type=int, required=True)
    parser.add_argument("--thinking-budget", type=int, default=1024)
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument("--validate-judge-quotes", action="store_true")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--max-model-calls", type=int, default=5)
    parser.add_argument("--max-repair-rounds", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if (
        args.limit_per_task < 2
        or args.limit_per_task % 2
        or not 1 <= args.concurrency <= 16
        or args.thinking_budget <= 0
        or not 1 <= args.max_model_calls <= 7
        or not 0 <= args.max_repair_rounds <= 2
    ):
        parser.error(
            "Use a positive even task limit, concurrency 1..16 and positive thinking budget"
        )
    try:
        print(json.dumps(asyncio.run(evaluate(args)), indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Evaluation failed: {exc}\n")


if __name__ == "__main__":
    main()
