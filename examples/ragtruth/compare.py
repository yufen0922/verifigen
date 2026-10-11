"""Run resumable, paired live baselines and anonymous cross-model output review."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from verifigen.comparison import (
    ARMS,
    OPTIMIZED_ARMS,
    PROTOCOL,
    REVIEW_INSTRUCTIONS,
    SELF_REFINE_INSTRUCTIONS,
    blind_packets,
    review_packet,
    run_arm,
    select_cohort,
    summarize,
)
from verifigen.config import ModelSettings
from verifigen.generators import CompatibleChatGenerator
from verifigen.ragtruth import read_jsonl
from verifigen.review import QualityBudget

ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


async def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    settings = ModelSettings.from_env(ROOT / ".env.local")
    if args.reviewer_model == settings.model:
        raise ValueError(
            "Use a different reviewer model; same-model self-review is not independent"
        )
    stack = settings.stack(thinking_budget=args.thinking_budget)
    reviewer = CompatibleChatGenerator(
        base_url=settings.base_url,
        api_key=settings.api_key,
        model=args.reviewer_model,
        timeout=90,
        max_output_tokens=4096,
    )
    budget = QualityBudget(
        max_model_calls=5,
        max_repair_rounds=2,
        deadline_seconds=120,
        max_observed_tokens=24000,
    )
    excluded_sources = (
        sorted({r["source_id"] for r in read_jsonl(args.exclude_records)})
        if args.exclude_records
        else []
    )
    arms = OPTIMIZED_ARMS if args.optimized else ARMS
    samples = select_cohort(
        read_jsonl(args.samples),
        per_task=args.per_task,
        split=args.split,
        excluded_sources=excluded_sources,
    )
    code_names = (
        "comparison.py",
        "agents.py",
        "generators.py",
        "quality.py",
        "review.py",
        "policy.py",
        "gates.py",
        "ragtruth.py",
    )
    config = {
        "protocol": PROTOCOL,
        "model": settings.model,
        "reviewer_model": args.reviewer_model,
        "provider_base_url": settings.base_url,
        "provider_snapshot": "Alias; upstream exact weights/version may change.",
        "samples_sha256": hashlib.sha256(args.samples.read_bytes()).hexdigest(),
        "selected_case_ids": [s["id"] for s in samples],
        "per_task": args.per_task,
        "thinking_budget": args.thinking_budget,
        "temperature": 0,
        "max_output_tokens": 4096,
        "budget_ceiling": asdict(budget),
        "arms": list(arms),
        "split": args.split,
        "excluded_sources": excluded_sources,
        "judge_history": args.judge_history,
        "max_protocol_retries": args.max_protocol_retries,
        "refine_verify_initial_edits": 1 if args.optimized else 0,
        "self_refine_rounds": 2,
        "concurrency": args.concurrency,
        "prompt_hashes": {
            "self_refine": hashlib.sha256(SELF_REFINE_INSTRUCTIONS.encode()).hexdigest(),
            "review": hashlib.sha256(REVIEW_INSTRUCTIONS.encode()).hexdigest(),
        },
        "runtime_sha256": {
            name: hashlib.sha256((ROOT / "src/verifigen" / name).read_bytes()).hexdigest()
            for name in code_names
        },
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    config_path, records_path = args.output / "config.json", args.output / "records.jsonl"
    if config_path.exists() or records_path.exists():
        if not args.resume:
            raise ValueError("Output exists; use a new directory or --resume")
        if not config_path.exists() or json.loads(config_path.read_text()) != config:
            raise ValueError("Resume configuration or code fingerprint differs")
    write_json(config_path, config)
    records = read_jsonl(records_path) if records_path.exists() else []
    expected = {(s["id"], arm) for s in samples for arm in arms}
    completed = {(r["id"], r["arm"]) for r in records}
    if len(completed) != len(records) or not completed.issubset(expected):
        raise ValueError("Duplicate or unexpected arm records")
    semaphore = asyncio.Semaphore(args.concurrency)

    async def one(sample: dict[str, Any], arm: str) -> dict[str, Any]:
        async with semaphore:
            return await run_arm(
                sample,
                arm,
                stack,
                budget,
                judge_history=args.judge_history,
                max_protocol_retries=args.max_protocol_retries,
            )

    async def collect(tasks: list[asyncio.Task[Any]], path: Path, rows: list[Any]) -> None:
        try:
            for future in asyncio.as_completed(tasks):
                row = await future
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    handle.flush()
                rows.append(row)
                if len(rows) % 10 == 0 or len(rows) == len(tasks):
                    print(f"{path.name}: {len(rows)} completed", flush=True)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    await collect(
        [
            asyncio.create_task(one(s, arm))
            for s in samples
            for arm in arms
            if (s["id"], arm) not in completed
        ],
        records_path,
        records,
    )
    packets, mapping = blind_packets(samples, records)
    for name, rows in (("blind-packets.jsonl", packets), ("review-mapping.jsonl", mapping)):
        (args.output / name).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
    review_path = args.output / "reviews.jsonl"
    reviews = read_jsonl(review_path) if review_path.exists() else []
    reviewed_ids = {r["review_id"] for r in reviews}
    if len(reviewed_ids) != len(reviews) or not reviewed_ids.issubset(
        {p["review_id"] for p in packets}
    ):
        raise ValueError("Duplicate or unexpected review records")

    async def external(packet: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await review_packet(packet, reviewer)

    await collect(
        [asyncio.create_task(external(p)) for p in packets if p["review_id"] not in reviewed_ids],
        review_path,
        reviews,
    )
    summary = {"config": config, **summarize(records, mapping, reviews)}
    write_json(args.output / "summary.json", summary)
    print(json.dumps(summary["arms"], indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--samples", type=Path, default=ROOT / "benchmarks/data/ragtruth-600/samples.jsonl"
    )
    parser.add_argument("--per-task", type=int, default=20)
    parser.add_argument("--reviewer-model", default="qwen-plus")
    parser.add_argument("--thinking-budget", type=int, default=1024)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--split", choices=("dev", "eval"), default="eval")
    parser.add_argument("--exclude-records", type=Path)
    parser.add_argument("--optimized", action="store_true")
    parser.add_argument("--judge-history", choices=("full", "none"), default="full")
    parser.add_argument("--max-protocol-retries", type=int, choices=(0, 1), default=1)
    args = parser.parse_args()
    if not 1 <= args.concurrency <= 16 or args.thinking_budget < 1:
        parser.error("Use concurrency 1..16 and a positive thinking budget")
    try:
        asyncio.run(evaluate(args))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Comparison failed: {exc}\n")


if __name__ == "__main__":
    main()
