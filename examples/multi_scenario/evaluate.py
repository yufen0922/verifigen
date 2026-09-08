"""Evaluate one QualityLoop across RAG, support and data-to-text scenarios."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from verifigen import (
    FunctionJudge,
    FunctionRepairer,
    JudgeIssue,
    JudgeVerdict,
    QualityBudget,
    QualityLoop,
    QualityTask,
    make_qwen3_8b_stack,
)
from verifigen.domains.rag_review import make_rag_task
from verifigen.domains.report_review import make_report_task
from verifigen.domains.support_review import make_support_task
from verifigen.rag_eval import score_rag_output
from verifigen.retrieval import BM25Retriever
from verifigen.scenario_eval import inspect_report_output, inspect_support_output

ROOT = Path(__file__).resolve().parents[2]
PATHS = {
    "rag": ROOT / "examples" / "rag_qa" / "eval_cases.jsonl",
    "support": ROOT / "examples" / "customer_support" / "eval_cases.jsonl",
    "report": ROOT / "examples" / "data_to_text" / "eval_cases.jsonl",
}


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def rag_failures(output: Any, case: dict[str, Any]) -> tuple[str, ...]:
    if score_rag_output(output, case):
        return ()
    mutation = case["id"].rsplit("--", 1)[-1]
    if mutation in {"no_citations", "fabricated_citation", "cross_category"}:
        return ("citation",)
    if mutation in {"missing_fee", "missing_condition"}:
        return ("completeness",)
    if mutation == "unsupported_promise":
        return ("relevance",)
    return ("grounding",)


def make_source_and_task(
    scenario: str,
    case: dict[str, Any],
    retriever: BM25Retriever,
) -> tuple[QualityTask, Any, Callable[[Any, dict[str, Any]], tuple[str, ...]]]:
    if scenario == "rag":
        hits = retriever.search(
            case["question"], top_k=3, filters={"product_category": case["category"]}
        )
        source = {
            "question": case["question"],
            "product_category": case["category"],
            "retrieved_chunks": [hit.document for hit in hits],
        }
        return make_rag_task(source), None, rag_failures
    if scenario == "support":
        return make_support_task(case["source"]), case["expected"], inspect_support_output
    return make_report_task(case["source"]), case["expected"], inspect_report_output


def offline_agents(
    case: dict[str, Any],
    expected: Any,
    inspect: Callable[[Any, dict[str, Any]], tuple[str, ...]],
) -> tuple[FunctionJudge, FunctionRepairer]:
    def judge(request: Any) -> JudgeVerdict:
        failures = inspect(request.candidate, case)
        if not failures:
            return JudgeVerdict("pass", 0.98, "独立规则检查通过。")
        issues = tuple(
            JudgeIssue(
                criterion_id,
                f"候选输出未通过 {criterion_id} 检查。",
                "离线 oracle 根据样本标注检测到差异。",
                "仅依据任务 source 修正对应字段或文本。",
            )
            for criterion_id in failures
        )
        return JudgeVerdict("fail", 0.2, "候选输出存在可修复问题。", issues)

    return FunctionJudge(judge), FunctionRepairer(lambda _request: expected)


async def execute(args: argparse.Namespace) -> int:
    selected = list(PATHS) if args.scenario == "all" else [args.scenario]
    cases_by_scenario = {name: jsonl(PATHS[name])[: args.limit_per_scenario] for name in selected}
    documents = jsonl(ROOT / "examples" / "rag_qa" / "policies.jsonl")
    retriever = BM25Retriever(documents)
    rag_clean = {
        case["category"]: case["initial"]
        for case in jsonl(PATHS["rag"])
        if case["id"].endswith("--clean")
    }

    stack = None
    if args.mode == "qwen":
        api_key = os.environ.get("DASHSCOPE_API_KEY")
        if not api_key:
            raise ValueError("Set DASHSCOPE_API_KEY before running --mode qwen")
        stack = make_qwen3_8b_stack(
            api_key=api_key,
            base_url=os.environ.get(
                "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
            ),
            model=os.environ.get("DASHSCOPE_MODEL", "qwen3-8b"),
            thinking_budget=args.thinking_budget,
        )

    scenario_cases = [
        (scenario, case) for scenario, cases in cases_by_scenario.items() for case in cases
    ]
    jobs = [(index, scenario, case) for index, (scenario, case) in enumerate(scenario_cases)]
    semaphore = asyncio.Semaphore(args.concurrency)

    async def run_case(index: int, scenario: str, case: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            task, expected, inspect = make_source_and_task(scenario, case, retriever)
            if scenario == "rag":
                expected = rag_clean[case["category"]]
            if stack is None:
                judge, repairer = offline_agents(case, expected, inspect)
            else:
                judge, repairer = stack.judge, stack.repairer
            result = await QualityLoop(
                judge=judge,
                repairer=repairer,
                budget=QualityBudget(max_model_calls=5, max_repair_rounds=2),
            ).run(task, initial=case["initial"])
            first_status = result.verdicts[0].status if result.verdicts else "error"
            final_correct = not inspect(result.output, case)
            return {
                "_index": index,
                "id": case["id"],
                "scenario": scenario,
                "initial_should_pass": case["initial_should_pass"],
                "first_judge_status": first_status,
                "detection_correct": (first_status == "pass") == case["initial_should_pass"],
                "final_correct": final_correct,
                "status": result.status,
                "reason": result.reason,
                "repair_rounds": result.repair_rounds,
                "model_calls": result.model_calls,
                "input_tokens": sum(usage.input_tokens or 0 for usage in result.usages),
                "output_tokens": sum(usage.output_tokens or 0 for usage in result.usages),
                "output": result.output,
                "best_candidate": result.best_candidate,
                "verdicts": [
                    {
                        "status": verdict.status,
                        "score": verdict.score,
                        "summary": verdict.summary,
                        "issues": [
                            {
                                "criterion_id": issue.criterion_id,
                                "message": issue.message,
                                "evidence": issue.evidence,
                                "suggestion": issue.suggestion,
                            }
                            for issue in verdict.issues
                        ],
                    }
                    for verdict in result.verdicts
                ],
                "issue_ids": [
                    issue.criterion_id for verdict in result.verdicts for issue in verdict.issues
                ],
            }

    records: list[dict[str, Any]] = []
    tasks = [asyncio.create_task(run_case(*job)) for job in jobs]
    for completed, task in enumerate(asyncio.as_completed(tasks), 1):
        records.append(await task)
        if args.mode == "qwen" and (completed % 10 == 0 or completed == len(tasks)):
            print(f"completed {completed}/{len(tasks)}", flush=True)
    records.sort(key=lambda record: record.pop("_index"))

    per_scenario: dict[str, dict[str, Any]] = {}
    for scenario in selected:
        rows = [row for row in records if row["scenario"] == scenario]
        bad = [row for row in rows if not row["initial_should_pass"]]
        published = [row for row in rows if row["status"] == "passed"]
        per_scenario[scenario] = {
            "cases": len(rows),
            "initial_pass_rate": sum(row["initial_should_pass"] for row in rows) / len(rows),
            "judge_detection_accuracy": sum(row["detection_correct"] for row in rows) / len(rows),
            "bad_case_repair_success": sum(row["final_correct"] for row in bad) / len(bad)
            if bad
            else None,
            "final_oracle_success": sum(row["final_correct"] for row in rows) / len(rows),
            "fallback_rate": sum(row["status"] == "fallback" for row in rows) / len(rows),
            "published_outputs": len(published),
            "wrong_releases": sum(not row["final_correct"] for row in published),
            "published_oracle_precision": sum(row["final_correct"] for row in published)
            / len(published)
            if published
            else None,
            "avg_repair_rounds": sum(row["repair_rounds"] for row in rows) / len(rows),
            "avg_model_calls": sum(row["model_calls"] for row in rows) / len(rows),
            "input_tokens": sum(row["input_tokens"] for row in rows),
            "output_tokens": sum(row["output_tokens"] for row in rows),
        }
    published = [record for record in records if record["status"] == "passed"]
    bad = [record for record in records if not record["initial_should_pass"]]
    summary = {
        "mode": args.mode,
        "model": stack.generator.model if stack is not None else None,
        "thinking_budget": args.thinking_budget if stack is not None else None,
        "concurrency": args.concurrency,
        "note": (
            "Offline mode validates loop wiring and oracle closure; it is not a measured LLM score."
            if args.mode == "offline"
            else "Qwen outputs are scored by deterministic scenario oracles."
        ),
        "cases": len(records),
        "overall": {
            "judge_detection_accuracy": sum(record["detection_correct"] for record in records)
            / len(records),
            "bad_case_repair_success": sum(record["final_correct"] for record in bad) / len(bad),
            "final_oracle_success": sum(record["final_correct"] for record in records)
            / len(records),
            "fallback_rate": sum(record["status"] == "fallback" for record in records)
            / len(records),
            "published_outputs": len(published),
            "wrong_releases": sum(not record["final_correct"] for record in published),
            "published_oracle_precision": sum(record["final_correct"] for record in published)
            / len(published)
            if published
            else None,
            "model_calls": sum(record["model_calls"] for record in records),
        },
        "scenarios": per_scenario,
        "issue_counts": dict(Counter(issue for record in records for issue in record["issue_ids"])),
        "reason_counts": dict(Counter(record["reason"] for record in records)),
        "total_input_tokens": sum(record["input_tokens"] for record in records),
        "total_output_tokens": sum(record["output_tokens"] for record in records),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {key: value for key, value in summary.items() if key != "records"},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate one loop over three quality scenarios")
    parser.add_argument("--mode", choices=("offline", "qwen"), default="offline")
    parser.add_argument("--scenario", choices=("all", "rag", "support", "report"), default="all")
    parser.add_argument("--limit-per-scenario", type=int, default=60)
    parser.add_argument("--thinking-budget", type=int, default=2048)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--output", type=Path, default=Path("runs/multi-scenario-eval.json"))
    args = parser.parse_args()
    if args.limit_per_scenario <= 0 or args.thinking_budget <= 0 or args.concurrency <= 0:
        parser.error("limits must be positive")
    try:
        code = asyncio.run(execute(args))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Configuration/input error: {exc}\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
