import asyncio
from dataclasses import replace

import pytest

from verifigen import (
    Criterion,
    FunctionJudge,
    FunctionRepairer,
    JudgeIssue,
    JudgeVerdict,
    QualityBudget,
    QualityLoop,
    QualityPolicy,
    QualityTask,
    ReplayJudge,
    ReplayRepairer,
    SchemaGate,
    write_quality_trace,
)
from verifigen.domains.rag_review import CitationGate, make_rag_task

PASS = JudgeVerdict("pass", 0.95, "Looks correct")


def task(**kwargs):
    return QualityTask(
        source={"amount": 799},
        prompt="Report the amount.",
        criteria=(Criterion("grounding", "Use the exact source amount."),),
        output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string", "minLength": 1}},
            "required": ["answer"],
            "additionalProperties": False,
        },
        fallback_text="Unavailable",
        **kwargs,
    )


def failed(score):
    return JudgeVerdict("fail", score, "Incorrect", (JudgeIssue("grounding", "Wrong amount"),))


async def test_schema_rejection_overrides_model_pass_and_drives_repair():
    observed = []
    judge_history = []

    def judge(request):
        judge_history.append(request.history)
        return PASS

    def repair(request):
        observed.append(request.verdict)
        return {"answer": "799"}

    result = await QualityLoop(judge=FunctionJudge(judge), repairer=FunctionRepairer(repair)).run(
        task(), initial={"answer": 799}
    )
    assert result.output == {"answer": "799"}
    assert result.repair_rounds == 1
    assert observed[0].status == "fail"
    assert result.gate_reports[0].issues == observed[0].issues
    assert judge_history[1][0].status == "fail"
    assert judge_history[1][0].issues == observed[0].issues
    assert "/answer" in observed[0].issues[0].message
    # Raw model verdicts stay available to measure false acceptance independently.
    assert [v.status for v in result.verdicts] == ["pass", "pass"]
    assert [e.details["action"] for e in result.trace if e.event == "decision"] == [
        "repair",
        "publish",
    ]


async def test_repaired_candidate_must_pass_schema_again():
    result = await QualityLoop(
        judge=ReplayJudge([failed(0.2), PASS]),
        repairer=ReplayRepairer([{"answer": 799}]),
        budget=QualityBudget(max_repair_rounds=1),
    ).run(task(), initial={"answer": "899"})
    assert result.status == "fallback" and result.output is None
    assert result.reason == "repair_budget"


async def test_custom_gate_prevents_incorrect_release():
    class AmountGate:
        async def check(self, candidate, task):
            if candidate["answer"] != str(task.source["amount"]):
                return (
                    JudgeIssue("grounding", "Amount differs from source", suggestion="Use 799"),
                )
            return ()

    result = await QualityLoop(
        judge=ReplayJudge([PASS, PASS]),
        repairer=ReplayRepairer([{"answer": "799"}]),
        gates=(AmountGate(),),
    ).run(task(), initial={"answer": "899"})
    assert result.output == {"answer": "799"}
    assert result.repair_rounds == 1


@pytest.mark.parametrize("mode", ["exception", "invalid_result"])
async def test_gate_failure_uses_reason_specific_fallback(mode):
    class BrokenGate:
        async def check(self, candidate, task):
            if mode == "exception":
                raise ValueError("secret provider detail")
            return ["not a tuple of issues"]

    result = await QualityLoop(
        judge=ReplayJudge([PASS]), repairer=ReplayRepairer([]), gates=(BrokenGate(),)
    ).run(task(fallback_by_reason={"gate_error": "Please retry later"}), initial={"answer": "799"})
    assert result.reason == "gate_error" and result.text == "Please retry later"
    assert result.output is None
    assert "secret" not in str(result.to_dict())


async def test_unknown_context_is_not_repaired_by_a_gate():
    class MustNotRun:
        async def check(self, candidate, task):
            raise AssertionError("Insufficient source should stop immediately")

    result = await QualityLoop(
        judge=ReplayJudge([JudgeVerdict("unknown", 0, "Missing evidence")]),
        repairer=ReplayRepairer([]),
        gates=(MustNotRun(),),
    ).run(task(), initial={})
    assert result.reason == "judge_unknown"


async def test_schema_supports_nested_local_refs_without_type_coercion():
    schema = {
        "$defs": {"count": {"type": "integer", "minimum": 0}},
        "type": "object",
        "properties": {"counts": {"type": "array", "items": {"$ref": "#/$defs/count"}}},
    }
    gate = SchemaGate(schema)
    assert await gate.check({"counts": [1, 2]}, task()) == ()
    issues = await gate.check({"counts": [1, "2"]}, task())
    assert len(issues) == 1 and "/counts/1" in issues[0].message


async def test_schema_external_reference_fails_closed_without_fetching():
    custom = replace(task(), output_schema={"$ref": "https://invalid.example/schema.json"})
    result = await QualityLoop(judge=ReplayJudge([PASS]), repairer=ReplayRepairer([])).run(
        custom, initial={"answer": "799"}
    )
    assert result.reason == "gate_error" and result.output is None


@pytest.mark.parametrize("schema", [{"type": "not-a-type"}, {"$schema": "unknown-dialect"}])
async def test_invalid_schema_is_rejected_before_model_call(schema):
    judge = ReplayJudge([])
    result = await QualityLoop(judge=judge, repairer=ReplayRepairer([])).run(
        replace(task(), output_schema=schema), initial={"answer": "799"}
    )
    assert result.reason == "invalid_schema" and judge.calls == 0


async def test_each_adapter_and_gate_receives_an_isolated_task():
    observed = []

    def judge(request):
        observed.append(request.task.source["amount"])
        request.task.source["amount"] = 1
        request.task.output_schema.clear()
        request.task.fallback_by_reason["repair_budget"] = "mutated"
        return failed(0.2) if request.round_index == 0 else PASS

    def repair(request):
        observed.append(request.task.source["amount"])
        request.task.source["amount"] = 2
        return {"answer": "799"}

    class MutatingGate:
        async def check(self, candidate, task):
            observed.append(task.source["amount"])
            task.source["amount"] = 3
            candidate["answer"] = "mutated"
            return ()

    original = task()
    result = await QualityLoop(
        judge=FunctionJudge(judge), repairer=FunctionRepairer(repair), gates=(MutatingGate(),)
    ).run(original, initial={"answer": "899"})
    assert result.output == {"answer": "799"}
    assert observed == [799] * 5
    assert original.source == {"amount": 799}
    assert original.output_schema["required"] == ["answer"]
    assert original.fallback_by_reason == {}


async def test_shared_loop_keeps_concurrent_run_state_separate():
    async def judge(request):
        await asyncio.sleep(0)
        return (
            PASS
            if request.candidate["answer"] == str(request.task.source["amount"])
            else failed(0.2)
        )

    async def repair(request):
        await asyncio.sleep(0)
        return {"answer": str(request.task.source["amount"])}

    loop = QualityLoop(judge=FunctionJudge(judge), repairer=FunctionRepairer(repair))
    results = await asyncio.gather(
        *(
            loop.run(replace(task(), source={"amount": i}), initial={"answer": "wrong"})
            for i in range(12)
        )
    )
    assert len({r.run_id for r in results}) == 12
    assert [r.output for r in results] == [{"answer": str(i)} for i in range(12)]
    assert all(r.repair_rounds == 1 and len(r.verdicts) == 2 for r in results)


async def test_optional_plateau_stops_distinct_but_unimproved_repairs():
    result = await QualityLoop(
        judge=ReplayJudge([failed(0.4), failed(0.4), failed(0.4)]),
        repairer=ReplayRepairer([{"answer": "898"}, {"answer": "897"}]),
        budget=QualityBudget(max_repair_rounds=5),
        policy=QualityPolicy(score_patience=2),
    ).run(task(fallback_by_reason={"score_plateau": "Needs review"}), initial={"answer": "899"})
    assert result.reason == "score_plateau" and result.repair_rounds == 2
    assert result.text == "Needs review" and result.output is None


@pytest.mark.parametrize(
    "scores, action", [([0.2, 0.3, 0.4], "repair"), ([0.7, 0.4, 0.5], "fallback")]
)
def test_plateau_uses_best_score_not_only_previous_round(scores, action):
    verdicts = tuple(failed(score) for score in scores)
    decision = QualityPolicy(score_patience=2).decide(
        verdicts[-1],
        history=verdicts[:-1],
        min_pass_score=0.8,
        repair_rounds=2,
        max_repair_rounds=5,
    )
    assert decision.action == action


def test_passing_candidate_is_released_even_after_score_plateau():
    decision = QualityPolicy(score_patience=1).decide(
        PASS,
        history=(failed(0.95),),
        min_pass_score=0.8,
        repair_rounds=1,
        max_repair_rounds=1,
    )
    assert decision.action == "publish"


async def test_gate_obeys_deadline_and_external_cancellation():
    class SlowGate:
        async def check(self, candidate, task):
            await asyncio.sleep(10)
            return ()

    loop = QualityLoop(
        judge=FunctionJudge(lambda _: PASS),
        repairer=ReplayRepairer([]),
        gates=(SlowGate(),),
        budget=QualityBudget(deadline_seconds=0.02),
    )
    result = await loop.run(task(), initial={"answer": "799"})
    assert result.reason == "deadline"
    pending = asyncio.create_task(loop.run(task(), initial={"answer": "799"}))
    await asyncio.sleep(0)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending


async def test_trace_contains_decisions_and_config_without_business_text(tmp_path):
    result = await QualityLoop(judge=ReplayJudge([PASS]), repairer=ReplayRepairer([])).run(
        task(), initial={"answer": "private customer message"}
    )
    path = tmp_path / "trace.jsonl"
    write_quality_trace(result, path)
    content = path.read_text()
    assert '"action": "publish"' in content and '"min_pass_score": 0.8' in content
    assert "private customer message" not in content


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_model_calls": 1.5},
        {"max_repair_rounds": True},
        {"deadline_seconds": float("nan")},
        {"deadline_seconds": float("inf")},
        {"max_observed_tokens": 3.5},
    ],
)
def test_budget_rejects_values_that_cannot_bound_execution(kwargs):
    with pytest.raises(ValueError):
        QualityBudget(**kwargs)


@pytest.mark.parametrize(
    "kwargs", [{"score_patience": 0}, {"score_patience": True}, {"min_score_gain": 0}]
)
def test_invalid_score_policy(kwargs):
    with pytest.raises(ValueError):
        QualityPolicy(**kwargs)


def test_invalid_fallback_message():
    with pytest.raises(ValueError):
        task(fallback_by_reason={"deadline": " "})


async def test_business_gate_does_not_run_on_invalid_shape():
    class RequiresAnswer:
        async def check(self, candidate, task):
            assert isinstance(candidate["answer"], str)
            return ()

    result = await QualityLoop(
        judge=ReplayJudge([PASS, PASS]),
        repairer=ReplayRepairer([{"answer": "799"}]),
        gates=(RequiresAnswer(),),
    ).run(task(), initial={})
    assert result.status == "passed" and result.repair_rounds == 1


@pytest.mark.parametrize(
    "candidate, issue_count",
    [
        ({"answer": "Allowed [KB-1]", "citations": ["KB-1"]}, 0),
        ({"answer": "Invented [KB-2]", "citations": ["KB-2"]}, 1),
        ({"answer": "No inline citation", "citations": ["KB-1"]}, 1),
        ({"answer": "Invented [KB-2]", "citations": ["KB-1"]}, 2),
    ],
)
async def test_citation_gate_validates_ids_and_inline_consistency(candidate, issue_count):
    custom = make_rag_task({"retrieved_chunks": [{"chunk_id": "KB-1", "text": "Allowed"}]})
    issues = await CitationGate().check(candidate, custom)
    assert len(issues) == issue_count
