"""Data-rich offline walkthrough of Judge -> Repair -> re-Judge.

This script uses predetermined verdicts and a deterministic repair so it can run
without an API key. It exercises the same QualityLoop state machine and records
the exact context and data each role would receive. Use run_qwen.py to replace
these recorded values with real Qwen3-8B responses.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from verifigen import (
    FunctionJudge,
    FunctionRepairer,
    JudgeIssue,
    JudgeVerdict,
    QualityLoop,
)
from verifigen.domains.rag_review import make_rag_task
from verifigen.retrieval import BM25Retriever, SearchHit

ROOT = Path(__file__).resolve().parent
QUERY = "耳机拆封后还能七天无理由退货吗，非质量问题退货运费由谁承担？"

BAD_CANDIDATE = {
    "answer": (
        "耳机拆封后仍可在15天内无理由退货，非质量问题运费由商家承担。[KB-LAPTOP-RETURN-15D]"
    ),
    "citations": ["KB-LAPTOP-RETURN-15D"],
}

FIXED_CANDIDATE = {
    "answer": (
        "耳机符合退货条件时可在收货后七天内申请退货。[KB-HEADPHONE-RETURN-7D] "
        "非质量问题下，耳机拆封后不适用七天无理由退货。[KB-HEADPHONE-OPENED] "
        "非质量问题退货运费由客户承担。[KB-HEADPHONE-FEE]"
    ),
    "citations": [
        "KB-HEADPHONE-RETURN-7D",
        "KB-HEADPHONE-OPENED",
        "KB-HEADPHONE-FEE",
    ],
}

FAILED = JudgeVerdict(
    "fail",
    0.25,
    "退货期限、拆封条件和运费方均与检索原文冲突，且引用了不在本次检索结果中的片段。",
    (
        JudgeIssue(
            "grounding",
            "“15天内可退、商家承担运费”与耳机政策原文冲突",
            (
                "KB-HEADPHONE-RETURN-7D：符合退货条件的耳机可在收货后七天内申请退货；"
                "KB-HEADPHONE-OPENED：非质量问题下耳机拆封后不适用七天无理由退货；"
                "KB-HEADPHONE-FEE：非质量问题退货运费由客户承担。"
            ),
            "改写为七天窗口、拆封后不适用、客户承担运费，并引用本次检索到的耳机片段。",
        ),
        JudgeIssue(
            "citation",
            "引用的 KB-LAPTOP-RETURN-15D 不在本次检索结果中，属于跨商品类别引用",
            "本次检索到 KB-HEADPHONE-RETURN-7D、KB-HEADPHONE-OPENED、KB-HEADPHONE-FEE。",
            "citations 只保留本次检索到且支持结论的片段 ID。",
        ),
    ),
)

PASSED = JudgeVerdict(
    "pass",
    0.97,
    "退货期限、拆封条件、运费方和引用片段均与检索原文一致，无需继续修复。",
)


def load_documents(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def make_source(hits: tuple[SearchHit, ...]) -> dict[str, Any]:
    return {
        "question": QUERY,
        "product_category": "headphones",
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
    documents = load_documents(ROOT / "policies.jsonl")
    hits = BM25Retriever(documents).search(
        QUERY,
        top_k=3,
        filters={"product_category": "headphones"},
    )
    if not hits:
        raise ValueError("Retriever returned no chunks")

    task = make_rag_task(make_source(hits))
    observed: dict[str, Any] = {}

    def judge_fn(request: Any) -> JudgeVerdict:
        observed[f"judge_round_{request.round_index}"] = {
            "received_task_prompt": request.task.prompt,
            "received_instructions": request.task.instructions,
            "received_criteria": [asdict(item) for item in request.task.criteria],
            "received_source": request.task.source,
            "received_candidate": request.candidate,
            "round_index": request.round_index,
            "previous_verdicts": [asdict(item) for item in request.history],
        }
        return PASSED if request.history else FAILED

    def repair_fn(request: Any) -> dict[str, Any]:
        observed["repair_round_1"] = {
            "received_task_prompt": request.task.prompt,
            "received_source": request.task.source,
            "received_candidate": request.candidate,
            "received_verdict": asdict(request.verdict),
        }
        return FIXED_CANDIDATE

    result = await QualityLoop(
        judge=FunctionJudge(judge_fn),
        repairer=FunctionRepairer(repair_fn),
    ).run(task, initial=BAD_CANDIDATE)

    observed["final"] = {
        "status": result.status,
        "reason": result.reason,
        "output": result.output,
        "published_text": result.text,
        "repair_rounds": result.repair_rounds,
        "model_calls": result.model_calls,
        "verdicts": [asdict(verdict) for verdict in result.verdicts],
        "trace": [
            {
                "event": event.event,
                "elapsed_ms": event.elapsed_ms,
                "details": event.details,
            }
            for event in result.trace
        ],
    }
    report = {
        "title": "VerifiGen RAG offline process walkthrough",
        "mode": "recorded_replay_no_api_key",
        "note": "Verdicts and repair are recorded demo values, not Qwen3-8B output.",
        "input": {
            "question": task.source["question"],
            "product_category": task.source["product_category"],
            "retrieved_chunks": task.source["retrieved_chunks"],
            "output_schema": task.output_schema,
            "criteria": [asdict(item) for item in task.criteria],
            "initial_candidate": BAD_CANDIDATE,
        },
        "observed": observed,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print a data-rich offline Judge/Repair walkthrough"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runs/process-demo.json"),
        help="Write the full JSON report to this path",
    )
    args = parser.parse_args()
    try:
        code = asyncio.run(execute(args))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Configuration/input error: {exc}\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
