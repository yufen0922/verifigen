"""Paired offline replay / opt-in live evaluation with a strong template baseline."""

from __future__ import annotations

import json
import platform
import statistics
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .domains.support import make_support_contract, template_response
from .evaluation import field_correctness, rate, regression_counts, score_output
from .generators import FunctionGenerator, Generator
from .jsonutil import digest, json_copy, replace_path
from .runtime import Harness
from .types import Budget, Context, GenerationRequest, Usage


def load_cases(path: str | Path) -> list[dict[str, Any]]:
    cases = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not cases or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Dataset must contain cases with unique IDs")
    return cases


async def run_benchmark(
    dataset: str | Path,
    output_dir: str | Path,
    *,
    live_generator: Generator | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    cases = load_cases(dataset)
    if live_generator is not None:
        # Live mode generates one natural candidate per source family. Do not
        # send the mutation, gold answer, or desired error to the model.
        cases = [case for case in cases if case["mutation"] == "clean"]
    if limit is not None:
        cases = cases[:limit]
    if not cases:
        raise ValueError("No cases selected")
    contract = make_support_contract()
    rows: list[dict[str, Any]] = []
    detection = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    repair_generator = live_generator or FunctionGenerator(
        lambda request: template_response(request.source)
    )
    for case in cases:
        source, gold = case["source"], case["gold"]
        ctx = Context.create(source, datetime.fromisoformat(case["evaluation_time"]))
        initial = json_copy(case["candidate"])
        initial_usages: list[Usage] = []
        initial_calls = 0
        initial_latency = 0.0
        initial_failed = False
        if live_generator is not None:
            initial_calls = 1
            began = time.perf_counter()
            try:
                import asyncio

                generated = await asyncio.wait_for(
                    live_generator.generate(
                        GenerationRequest(
                            source=source,
                            prompt="请说明订单、退款状态和接下来应该做什么。",
                            output_schema=contract.schema.model_json_schema(),
                            instructions=contract.instructions,
                        )
                    ),
                    timeout=30,
                )
                initial, initial_usages = generated.content, [generated.usage]
            except Exception:
                initial_failed, initial, initial_usages = True, None, [Usage()]
            initial_latency = (time.perf_counter() - began) * 1000
        before_report = await contract.verify(initial, ctx)
        if gold is not None and not initial_failed:
            error = not score_output(initial, gold)
            flagged = before_report.status != "pass"
            detection[
                "tp" if error and flagged else "fn" if error else "fp" if flagged else "tn"
            ] += 1

        for strategy in (
            "generator_only",
            "template",
            "field_only_ablation",
            "full_regenerate",
            "dependency_repair",
        ):
            began = time.perf_counter()
            output, calls, usages, rounds = initial, 0, [], 0
            reason = "unchecked"
            trace: list[dict[str, Any]] = []
            if strategy == "template":
                # This baseline starts from the source and incurs no initial LLM call.
                try:
                    candidate = template_response(source)
                    result = await Harness(contract).run(
                        source=source, initial=candidate, context=ctx
                    )
                    output, reason = result.output, result.reason
                except (ValueError, KeyError, TypeError):
                    output, reason = None, "evidence_unavailable"
            elif initial_failed:
                output, reason = None, "initial_provider_error"
            elif strategy == "field_only_ablation":
                if before_report.status == "unknown" or not isinstance(initial, dict):
                    output, reason = None, "unrepairable"
                else:
                    output = json_copy(initial)
                    # Intentionally unsafe ablation: no dependency closure and no
                    # final gate. It is not exposed as a production Harness mode.
                    try:
                        for violation in before_report.violations:
                            if violation.repairable:
                                replace_path(output, violation.target, violation.expected)
                        reason = "unchecked_field_patch"
                    except (KeyError, TypeError):
                        output, reason = None, "unrepairable"
            elif strategy in ("full_regenerate", "dependency_repair"):
                result = await Harness(
                    contract,
                    repair_generator,
                    budget=Budget(max_model_calls=2, max_repair_rounds=2, deadline_seconds=30),
                    repair_mode="regenerate" if strategy == "full_regenerate" else "dependency",
                ).run(source=source, initial=initial, context=ctx)
                output, calls, usages, rounds, reason = (
                    result.output,
                    result.model_calls,
                    list(result.usages),
                    result.repair_rounds,
                    result.reason,
                )
                trace = [{"event": event.event, "details": event.details} for event in result.trace]
            latency = (time.perf_counter() - began) * 1000
            include_initial = strategy != "template"
            all_usages = (initial_usages if include_initial else []) + usages
            total_calls = calls + (initial_calls if include_initial else 0)
            tokens = (
                None
                if any(usage.total_tokens is None for usage in all_usages)
                else sum(usage.total_tokens or 0 for usage in all_usages)
            )
            cost = (
                None
                if any(usage.cost_usd is None for usage in all_usages)
                else sum(usage.cost_usd or 0 for usage in all_usages)
            )
            regressions, eligible = (0, 0)
            if (
                gold is not None
                and output is not None
                and not score_output(initial, gold)
                and strategy in ("field_only_ablation", "full_regenerate", "dependency_repair")
            ):
                regressions, eligible = regression_counts(initial, output, gold)
            rows.append(
                {
                    "case_id": case["id"],
                    "family": case["family"],
                    "mutation": case["mutation"],
                    "strategy": strategy,
                    "correct": score_output(output, gold),
                    "answerable": gold is not None,
                    "abstained": output is None,
                    "initial_wrong": gold is not None and not score_output(initial, gold),
                    "initial_provider_failed": initial_failed,
                    "reason": reason,
                    "calls": total_calls,
                    "repair_calls": calls,
                    "repair_rounds": rounds,
                    "tokens": tokens,
                    "cost_usd": cost,
                    "latency_ms": round(latency + (initial_latency if include_initial else 0), 3),
                    "regressed_fields": regressions,
                    "previously_correct_fields": eligible,
                    "field_accuracy": None
                    if gold is None or output is None
                    else sum(field_correctness(output, gold).values())
                    / len(field_correctness(output, gold)),
                    "initial": initial,
                    "output": output,
                    "trace": trace,
                }
            )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["strategy"]].append(row)
    summaries = {}
    for name, entries in grouped.items():
        answerable = [entry for entry in entries if entry["answerable"]]
        emitted = [entry for entry in entries if not entry["abstained"]]
        errors = [entry for entry in answerable if entry["initial_wrong"]]
        summaries[name] = {
            "cases": len(entries),
            "task_success_rate": rate(sum(entry["correct"] for entry in entries), len(entries)),
            "valid_answer_rate": rate(
                sum(entry["correct"] and not entry["abstained"] for entry in answerable),
                len(answerable),
            ),
            "released_error_rate": rate(
                sum(not entry["correct"] for entry in emitted), len(emitted)
            ),
            "abstention_rate": rate(sum(entry["abstained"] for entry in entries), len(entries)),
            "repair_success_rate": rate(
                sum(entry["correct"] and not entry["abstained"] for entry in errors), len(errors)
            ),
            "repair_regression_rate": rate(
                sum(entry["regressed_fields"] for entry in entries),
                sum(entry["previously_correct_fields"] for entry in entries),
            ),
            "average_generation_calls": statistics.mean(entry["calls"] for entry in entries),
            "average_latency_ms": statistics.mean(entry["latency_ms"] for entry in entries),
            "total_tokens": None
            if any(entry["tokens"] is None for entry in entries)
            else sum(entry["tokens"] for entry in entries),
            "total_cost_usd": None
            if any(entry["cost_usd"] is None for entry in entries)
            else sum(entry["cost_usd"] for entry in entries),
        }
    summary = {
        "mode": "live" if live_generator else "synthetic_replay",
        "model": getattr(live_generator, "model", None),
        "dataset_sha256": digest(cases),
        "python": platform.python_version(),
        "contract_version": contract.version,
        "cases": len(cases),
        "notes": [
            "Synthetic replay measures deterministic mechanics, not LLM quality or production gain.",
            "Offline full_regenerate uses a source-driven template generator, not a real LLM.",
            "Template is a strong baseline and may match the final accuracy with lower complexity.",
            "Live mode shares each initial candidate across strategies, counts initial usage for each LLM strategy, and sends no gold labels.",
            "None means unavailable/undefined. Zero offline tokens means no LLM was called.",
        ],
        "detection_case_level": {
            **detection,
            "precision": rate(detection["tp"], detection["tp"] + detection["fp"]),
            "recall": rate(detection["tp"], detection["tp"] + detection["fn"]),
            "false_positive_rate": rate(detection["fp"], detection["fp"] + detection["tn"]),
        },
        "strategies": summaries,
    }
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (destination / "records.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    lines = [
        "# VerifiBench results",
        "",
        f"Mode: **{summary['mode']}**. Cases: {len(cases)}.",
        "",
        "Synthetic replay is a mechanics check, not evidence of model superiority.",
        "",
        "| Strategy | Valid answer | Released error | Abstention | Repair success | Calls/case |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    def percentage(value: float | None) -> str:
        return "N/A" if value is None else f"{value:.1%}"

    for name, metrics in summaries.items():
        lines.append(
            f"| {name} | {percentage(metrics['valid_answer_rate'])} | {percentage(metrics['released_error_rate'])} | {percentage(metrics['abstention_rate'])} | {percentage(metrics['repair_success_rate'])} | {metrics['average_generation_calls']:.2f} |"
        )
    lines += [
        "",
        "See summary.json for definitions and token availability; records.jsonl contains paired candidates, outputs and trace metadata. These files can contain source-derived data.",
    ]
    (destination / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
