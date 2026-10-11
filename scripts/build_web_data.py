"""Package curated task inputs and factual evaluation records for the workbench."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path

from verifigen.domains.rag_review import make_rag_task
from verifigen.domains.report_review import make_report_task
from verifigen.domains.support_review import make_support_task
from verifigen.metrics import detection_metrics
from verifigen.ragtruth import TASKS, make_ragtruth_task, read_jsonl
from verifigen.retrieval import BM25Retriever

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src/verifigen/web/data"


def main() -> None:
    retriever = BM25Retriever(read_jsonl(ROOT / "examples/rag_qa/policies.jsonl"))
    presets = []
    for scenario, relative, factory, label in (
        ("rag", "rag_qa", make_rag_task, "RAG 政策问答"),
        ("support", "customer_support", make_support_task, "客服退款回复"),
        ("report", "data_to_text", make_report_task, "数据报告生成"),
    ):
        case = read_jsonl(ROOT / f"examples/{relative}/eval_cases.jsonl")[1]
        if scenario == "rag":
            hits = retriever.search(
                case["question"], top_k=3, filters={"product_category": case["category"]}
            )
            source = {
                "question": case["question"],
                "product_category": case["category"],
                "retrieved_chunks": [h.document for h in hits],
            }
        else:
            source = case["source"]
        task = factory(source)
        presets.append(
            {
                "id": scenario,
                "label": label,
                "dataset": "synthetic",
                "case_id": case["id"],
                "scenario": scenario,
                "source": task.source,
                "prompt": task.prompt,
                "criteria": [asdict(c) for c in task.criteria],
                "output_schema": task.output_schema,
                "instructions": task.instructions,
                "fallback_text": task.fallback_text,
                "fallback_by_reason": task.fallback_by_reason,
                "initial": case["initial"],
                "citation_gate": scenario == "rag",
            }
        )
    samples = read_jsonl(ROOT / "benchmarks/data/ragtruth-600/samples.jsonl")
    for task_type in TASKS:
        sample = next(
            r
            for r in samples
            if r["task_type"] == task_type and r["has_hallucination"] and r["local_split"] == "dev"
        )
        task = make_ragtruth_task(sample)
        presets.append(
            {
                "id": task_type,
                "label": f"RAGTruth · {task_type}",
                "dataset": "RAGTruth",
                "case_id": sample["id"],
                "scenario": task_type,
                "source": task.source,
                "prompt": task.prompt,
                "criteria": [asdict(c) for c in task.criteria],
                "output_schema": task.output_schema,
                "instructions": task.instructions,
                "fallback_text": task.fallback_text,
                "fallback_by_reason": task.fallback_by_reason,
                "initial": {"answer": sample["response"]},
                "citation_gate": False,
            }
        )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        ROOT / "benchmarks/data/ragtruth-600/LICENSE-RAGTruth", OUTPUT / "LICENSE-RAGTruth"
    )
    (OUTPUT / "presets.json").write_text(json.dumps(presets, ensure_ascii=False, indent=2) + "\n")
    historical = ROOT / "benchmarks/results/qwen3.5-flash-180"
    summary = json.loads((historical / "summary.json").read_text())
    records = read_jsonl(historical / "records.jsonl")
    for record in records:
        record["detection_correct"] = record["first_judge_status"] == (
            "pass" if record["initial_should_pass"] else "fail"
        )
    summary["overall"].update(detection_metrics(records))
    evaluations = [
        {
            "id": "synthetic-180",
            "label": "合成集 · 180 条真实调用",
            "dataset": "synthetic",
            "summary": summary,
            "records": records,
        }
    ]
    public = ROOT / "benchmarks/results/ragtruth-qwen3.5-flash"
    if (public / "summary.json").exists():
        evaluations.append(
            {
                "id": "ragtruth",
                "label": "RAGTruth · 公开集",
                "dataset": "RAGTruth",
                "summary": json.loads((public / "summary.json").read_text()),
                "records": read_jsonl(public / "records.jsonl"),
            }
        )
    (OUTPUT / "evaluations.json").write_text(json.dumps(evaluations, ensure_ascii=False) + "\n")
    print(f"Packaged {len(presets)} task presets and {len(evaluations)} evaluations")


if __name__ == "__main__":
    main()
