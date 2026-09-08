"""BM25 retrieval -> Qwen3-8B generation -> Judge -> Repair -> re-Judge."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from verifigen import QualityBudget, QualityLoop, make_qwen3_8b_stack
from verifigen.domains.rag_review import make_rag_task
from verifigen.retrieval import BM25Retriever, SearchHit

DEFAULT_CORPUS = Path(__file__).with_name("policies.jsonl")
DEFAULT_QUERY = "耳机拆封后还能七天无理由退货吗，非质量问题退货运费由谁承担？"


def load_documents(path: Path) -> list[dict[str, Any]]:
    documents = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not documents:
        raise ValueError("Policy corpus is empty")
    return documents


def make_source(question: str, category: str, hits: tuple[SearchHit, ...]) -> dict[str, Any]:
    return {
        "question": question,
        "product_category": category,
        "retrieved_chunks": [
            {
                "chunk_id": hit.document["chunk_id"],
                "title": hit.document["title"],
                "text": hit.document["text"],
                "product_category": hit.document["product_category"],
                "retrieval_score": hit.score,
            }
            for hit in hits
        ],
    }


async def execute(args: argparse.Namespace) -> int:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("Set DASHSCOPE_API_KEY in the current shell; never commit it")
    hits = BM25Retriever(load_documents(args.corpus)).search(
        args.query,
        top_k=args.top_k,
        filters={"product_category": args.category},
    )
    if not hits:
        raise ValueError("Retriever returned no chunks")
    print("RETRIEVED:")
    for hit in hits:
        print(f"- {hit.document['chunk_id']} score={hit.score:.4f} {hit.document['text']}")

    stack = make_qwen3_8b_stack(
        api_key=api_key,
        base_url=os.environ.get(
            "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        model=os.environ.get("DASHSCOPE_MODEL", "qwen3-8b"),
        thinking_budget=args.thinking_budget,
        timeout=args.timeout,
    )
    loop = QualityLoop(
        generator=stack.generator,
        judge=stack.judge,
        repairer=stack.repairer,
        budget=QualityBudget(
            max_model_calls=7,
            max_repair_rounds=2,
            deadline_seconds=args.timeout * 7,
            min_pass_score=args.pass_score,
        ),
    )
    task = make_rag_task(make_source(args.query, args.category, hits))
    if args.repair_demo:
        bad = {
            "answer": "耳机拆封后仍可在15天内无理由退货，运费由商家承担。[KB-LAPTOP-RETURN-15D]",
            "citations": ["KB-LAPTOP-RETURN-15D"],
        }
        print("INITIAL CANDIDATE:")
        print(json.dumps(bad, ensure_ascii=False))
        result = await loop.run(task, initial=bad)
    else:
        result = await loop.run(task)

    print("JUDGE HISTORY:")
    for index, verdict in enumerate(result.verdicts):
        print(
            json.dumps(
                {
                    "round": index,
                    "status": verdict.status,
                    "score": verdict.score,
                    "summary": verdict.summary,
                    "issues": [
                        {
                            "criterion_id": issue.criterion_id,
                            "message": issue.message,
                            "evidence": issue.evidence,
                        }
                        for issue in verdict.issues
                    ],
                },
                ensure_ascii=False,
            )
        )
    print("PUBLISHED:")
    print(result.text)
    summary = {
        "model": stack.generator.model,
        "thinking": True,
        "status": result.status,
        "reason": result.reason,
        "model_calls": result.model_calls,
        "repair_rounds": result.repair_rounds,
        "total_tokens": [usage.total_tokens for usage in result.usages],
        "output": result.output,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0 if result.status == "passed" else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Qwen3-8B as generator, judge and repairer")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--category", default="headphones")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--thinking-budget", type=int, default=2048)
    parser.add_argument("--pass-score", type=float, default=0.8)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--repair-demo", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.thinking_budget <= 0 or args.top_k <= 0 or args.timeout <= 0:
        parser.error("thinking budget, top-k and timeout must be positive")
    if not 0 <= args.pass_score <= 1:
        parser.error("--pass-score must be between 0 and 1")
    try:
        code = asyncio.run(execute(args))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Configuration/input error: {exc}\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
