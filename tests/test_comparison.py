import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from verifigen import (
    FunctionGenerator,
    JudgeIssue,
    JudgeVerdict,
    QualityBudget,
    ReplayGenerator,
    ReplayJudge,
    ReplayRepairer,
)
from verifigen.comparison import (
    ARMS,
    OutputReview,
    blind_packets,
    review_packet,
    run_arm,
    select_cohort,
    summarize,
)


def sample(identifier="1", task="QA", bad=True, split="eval"):
    return {
        "id": identifier,
        "source_id": "source-" + identifier,
        "task_type": task,
        "local_split": split,
        "has_hallucination": bad,
        "source_info": {"fact": "paid 799"},
        "prompt": "State the paid amount.",
        "response": "paid 899" if bad else "paid 799",
        "labels": [{"text": "SECRET_LABEL"}],
    }


def test_cohort_is_reproducible_balanced_and_eval_only():
    rows = [
        sample(str(index * 4 + label * 2 + n + 1), task, bool(label))
        for index, task in enumerate(("QA", "Summary", "Data2txt"))
        for label in (0, 1)
        for n in (0, 1)
    ]
    rows.append(sample("999", split="dev"))
    selected = select_cohort(rows, per_task=2)
    assert selected == select_cohort(list(reversed(rows)), per_task=2)
    assert len(selected) == 6 and all(r["local_split"] == "eval" for r in selected)
    assert sum(r["has_hallucination"] for r in selected) == 3
    with pytest.raises(ValueError):
        select_cohort(rows, per_task=3)
    with pytest.raises(ValueError):
        select_cohort(rows, per_task=6)


def test_dev_selection_and_source_exclusion_are_explicit_and_balanced():
    rows = [
        sample(str(index * 4 + label * 2 + n + 1), task, bool(label), "dev")
        for index, task in enumerate(("QA", "Summary", "Data2txt"))
        for label in (0, 1)
        for n in (0, 1)
    ]
    excluded = [r["source_id"] for r in rows[::2]]
    selected = select_cohort(rows, per_task=2, split="dev", excluded_sources=excluded)
    assert len(selected) == 6 and sum(r["has_hallucination"] for r in selected) == 3
    assert not set(excluded) & {r["source_id"] for r in selected}
    with pytest.raises(ValueError):
        select_cohort(rows, per_task=2, split="anything")


async def test_refine_verify_arm_records_actual_edits_and_final_judge():
    stack = SimpleNamespace(
        generator=ReplayGenerator([{"answer": "paid 799"}]),
        judge=ReplayJudge([JudgeVerdict("pass", 1, "Supported")]),
        repairer=ReplayRepairer([]),
    )
    result = await run_arm(sample(), "refine_verify", stack, QualityBudget(), judge_history="none")
    assert result["changed"] and result["runtime"]["repair_rounds"] == 1
    assert result["runtime"]["rounds"][0]["verdict"]["status"] == "pass"


async def test_baselines_publish_different_things_without_faking_judge_approval():
    bad = sample()
    stack = SimpleNamespace(
        generator=ReplayGenerator([{"answer": "paid 799"}, {"answer": "paid 799"}]),
        judge=ReplayJudge([JudgeVerdict("pass", 0.9, "accepted")]),
        repairer=ReplayRepairer([]),
    )
    direct = await run_arm(bad, "direct", stack, QualityBudget())
    refined = await run_arm(bad, "self_refine", stack, QualityBudget())
    assert direct["output"] == {"answer": "paid 899"} and direct["model_calls"] == 0
    assert refined["output"] == {"answer": "paid 799"} and refined["model_calls"] == 2
    assert refined["reason"] == "self_refined_unverified"
    with pytest.raises(ValueError):
        await run_arm(bad, "unknown", stack, QualityBudget())


async def test_self_refine_budget_errors_and_usage_unknown_fail_closed():
    stack = SimpleNamespace(generator=ReplayGenerator([{"unexpected": True}]))
    result = await run_arm(sample(), "self_refine", stack, QualityBudget())
    assert result["status"] == "fallback" and result["reason"] == "invalid_candidate"
    assert result["model_calls"] == 1 and result["output"] is None
    stack = SimpleNamespace(generator=ReplayGenerator([]))
    zero = await run_arm(sample(), "self_refine", stack, QualityBudget(max_model_calls=0))
    assert zero["model_calls"] == 0 and zero["reason"] == "model_budget"
    error = await run_arm(sample(), "self_refine", stack, QualityBudget())
    assert error["reason"] == "provider_error" and error["model_calls"] == 1
    assert error["usages"][0]["input_tokens"] is None


async def test_judge_only_does_not_repair_and_loop_rechecks():
    failure = JudgeVerdict("fail", 0.2, "wrong", (JudgeIssue("grounding", "wrong amount"),))
    stack = SimpleNamespace(judge=ReplayJudge([failure]), repairer=ReplayRepairer([]))
    only = await run_arm(sample(), "judge_only", stack, QualityBudget())
    assert only["output"] is None and stack.repairer.calls == 0
    stack = SimpleNamespace(
        judge=ReplayJudge([failure, JudgeVerdict("pass", 0.9, "supported")]),
        repairer=ReplayRepairer([{"answer": "paid 799"}]),
    )
    result = await run_arm(sample(), "quality_loop", stack, QualityBudget())
    assert result["changed"] and len(result["runtime"]["rounds"]) == 2


async def test_reviewer_inputs_hide_gold_arm_identity_and_runtime_history():
    records = [
        {"id": "1", "arm": arm, "status": "passed", "output": {"answer": "paid 799"}}
        for arm in ARMS
    ]
    packets, mapping = blind_packets([sample()], records)
    assert len(packets) == 1 and len(mapping) == 4
    assert set(packets[0]) == {"review_id", "task", "evidence", "candidate"}
    captured = []

    def review(request):
        captured.append(request)
        return {"grounding": "pass", "fulfillment": "pass", "explanation": "supported"}

    result = await review_packet(packets[0], FunctionGenerator(review))
    text = json.dumps(captured[0].source)
    assert "SECRET_LABEL" not in text and "quality_loop" not in text and "review_id" not in text
    assert "previous_verdicts" not in text and captured[0].previous is None
    assert result["status"] == "reviewed" and result["kind"] == "cross_model_automatic_proxy"


@pytest.mark.parametrize(
    "review",
    [
        {"grounding": "fail", "fulfillment": "pass", "explanation": "bad"},
        {"grounding": "pass", "fulfillment": "fail", "explanation": "bad"},
        {"grounding": "pass", "fulfillment": "pass", "explanation": "good", "extra": 1},
    ],
)
def test_incoherent_review_is_rejected(review):
    with pytest.raises(ValueError):
        OutputReview.model_validate(review)


async def test_review_failure_is_not_a_positive_label():
    packet = {"review_id": "anonymous", "task": "answer", "evidence": {}, "candidate": {}}
    result = await review_packet(packet, ReplayGenerator([{"grounding": "pass"}]))
    assert result["status"] == "error" and result["review"] is None


def test_metrics_do_not_count_fallback_as_correct_or_unreviewed_as_pass():
    records = [
        {
            "id": str(i),
            "arm": "quality_loop",
            "status": status,
            "output": {"answer": "draft"} if status == "passed" else None,
            "initial_should_pass": False,
            "changed": True,
            "model_calls": 3,
            "usages": [],
            "latency_seconds": 1,
            "reason": "test",
        }
        for i, status in enumerate(("passed", "passed", "fallback"))
    ]
    mapping = [{"id": "0", "arm": "quality_loop", "review_id": "r0"}]
    reviews = [
        {
            "review_id": "r0",
            "status": "reviewed",
            "model_calls": 1,
            "review": {"grounding": "pass", "fulfillment": "pass"},
        }
    ]
    summary = summarize(records, mapping, reviews)
    metrics = summary["arms"]["quality_loop"]
    assert metrics["released"] == 2 and metrics["unreviewed_releases"] == 1
    assert metrics["proxy_verified_yield"] == 1 / 3
    assert metrics["proxy_bad_initial_rescue_rate"] == 1 / 3
    assert metrics["proxy_grounded_release_rate"] == 1 / 2
    assert summary["human_review_status"] == "pending"
    with pytest.raises(ValueError):
        summarize(records + records, mapping, reviews)


async def test_blind_rejudge_removes_history_but_repair_keeps_feedback():
    from verifigen import FunctionJudge, FunctionRepairer, QualityLoop
    from verifigen.ragtruth import make_ragtruth_task

    seen = []
    repaired_history = []

    def judge(request):
        seen.append(request.history)
        return (
            JudgeVerdict("fail", 0.2, "wrong", (JudgeIssue("grounding", "amount"),))
            if request.round_index == 0
            else JudgeVerdict("pass", 0.9, "supported")
        )

    def repair(request):
        repaired_history.append(request.history)
        return {"answer": "paid 799"}

    loop = QualityLoop(
        judge=FunctionJudge(judge), repairer=FunctionRepairer(repair), judge_history="none"
    )
    result = await loop.run(make_ragtruth_task(sample()), initial={"answer": "paid 899"})
    assert result.status == "passed" and seen == [(), ()]
    assert repaired_history[0][0].status == "fail"
    assert result.trace[0].details["judge_history"] == "none"
    with pytest.raises(ValueError):
        QualityLoop(judge=loop.judge, repairer=loop.repairer, judge_history="invalid")


async def test_self_refine_timeout_is_counted_and_does_not_publish_partial_candidate():
    import asyncio

    class Slow:
        async def generate(self, request):
            await asyncio.sleep(1)

    result = await run_arm(
        sample(),
        "self_refine",
        SimpleNamespace(generator=Slow()),
        replace(QualityBudget(), deadline_seconds=0.001),
    )
    assert result["reason"] == "deadline" and result["output"] is None
    assert result["model_calls"] == 1 and result["usages"][0]["input_tokens"] is None
