"""Labeled evaluation for Qwen Judge and Repair behavior over generated cases."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from verifigen import QualityBudget, QualityLoop, make_qwen3_8b_stack
from verifigen.domains.rag_review import make_rag_task
from verifigen.rag_eval import score_rag_output
from verifigen.retrieval import BM25Retriever

DIRECTORY = Path(__file__).parent


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


async def execute(args: argparse.Namespace) -> int:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("Set DASHSCOPE_API_KEY in the current shell; never commit it")
    cases = jsonl(args.cases)[: args.limit]
    if not cases:
        raise ValueError("Evaluation case file is empty")
    documents = jsonl(args.corpus)
    retriever = BM25Retriever(documents)
    stack = make_qwen3_8b_stack(
        api_key=api_key,
        base_url=os.environ.get(
            "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        model=os.environ.get("DASHSCOPE_MODEL", "qwen3-8b"),
        thinking_budget=args.thinking_budget,
    )
    records = []
    for case in cases:
        required_ids = {
            claim.get("chunk_id")
            for claim in case.get("required_claims", [])
            if isinstance(claim.get("chunk_id"), str)
        }
        hits = retriever.search(
            case["question"], top_k=3, filters={"product_category": case["category"]}
        )
        actual_ids = {hit.document["chunk_id"] for hit in hits}
        if required_ids and not required_ids.issubset(actual_ids):
            raise ValueError(f"Retrieval for {case['id']} is missing required evidence")
        source = {
            "question": case["question"],
            "product_category": case["category"],
            "retrieved_chunks": [hit.document for hit in hits],
        }
        result = await QualityLoop(
            judge=stack.judge,
            repairer=stack.repairer,
            budget=QualityBudget(max_model_calls=5, max_repair_rounds=2),
        ).run(make_rag_task(source), initial=case["initial"])
        first_status = result.verdicts[0].status if result.verdicts else "error"
        detection_correct = (first_status == "pass") == case["initial_should_pass"]
        final_correct = score_rag_output(result.output, case)
        records.append(
            {
                "id": case["id"],
                "initial_should_pass": case["initial_should_pass"],
                "first_judge_status": first_status,
                "detection_correct": detection_correct,
                "final_correct": final_correct,
                "status": result.status,
                "reason": result.reason,
                "repair_rounds": result.repair_rounds,
                "model_calls": result.model_calls,
                "output": result.output,
                "verdicts": [
                    {
                        "status": verdict.status,
                        "score": verdict.score,
                        "summary": verdict.summary,
                        "issues": [issue.criterion_id for issue in verdict.issues],
                    }
                    for verdict in result.verdicts
                ],
            }
        )
        print(case["id"], first_status, result.status, "oracle=", final_correct)

    bad = [record for record in records if not record["initial_should_pass"]]
    summary = {
        "model": stack.generator.model,
        "cases": len(records),
        "judge_case_accuracy": sum(item["detection_correct"] for item in records) / len(records),
        "bad_case_repair_success": sum(item["final_correct"] for item in bad) / len(bad),
        "final_oracle_success": sum(item["final_correct"] for item in records) / len(records),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in summary.items() if key != "records"}, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Qwen Judge/Repair on labeled RAG cases")
    parser.add_argument("--cases", type=Path, default=DIRECTORY / "eval_cases.jsonl")
    parser.add_argument("--corpus", type=Path, default=DIRECTORY / "policies.jsonl")
    parser.add_argument("--output", type=Path, default=Path("runs/rag-qwen-eval.json"))
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--thinking-budget", type=int, default=2048)
    args = parser.parse_args()
    if args.limit <= 0 or args.thinking_budget <= 0:
        parser.error("--limit and --thinking-budget must be positive")
    try:
        code = asyncio.run(execute(args))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Configuration/input error: {exc}\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
