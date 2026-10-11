"""Fault injection and concurrency checks, not model-quality benchmarks."""

import asyncio

from verifigen import (
    Criterion,
    FunctionJudge,
    FunctionRepairer,
    JudgeIssue,
    JudgeVerdict,
    QualityBudget,
    QualityLoop,
    QualityTask,
    ReplayJudge,
    ReplayRepairer,
)


def task(value):
    return QualityTask(
        source={"facts": {"value": value}},
        prompt="Report the value.",
        criteria=(Criterion("grounding", "Use the source value."),),
        output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
    )


FAIL = JudgeVerdict("fail", 0.2, "Wrong", (JudgeIssue("grounding", "Wrong value"),))
PASS = JudgeVerdict("pass", 0.95, "Supported")


async def test_64_shared_loop_runs_keep_evidence_candidate_feedback_and_run_id_isolated():
    async def judge(request):
        value = request.task.source["facts"]["value"]
        await asyncio.sleep((value % 4) / 10000)
        assert all(v.summary == f"wrong-{value}" for v in request.history)
        if request.candidate["answer"] == str(value):
            return PASS
        return JudgeVerdict("fail", 0.2, f"wrong-{value}", (JudgeIssue("grounding", "value"),))

    async def repair(request):
        value = request.task.source["facts"]["value"]
        await asyncio.sleep((value % 3) / 10000)
        assert request.verdict.summary == f"wrong-{value}"
        request.task.source["facts"]["value"] = -1
        return {"answer": str(value)}

    loop = QualityLoop(judge=FunctionJudge(judge), repairer=FunctionRepairer(repair))
    tasks = [task(i) for i in range(64)]
    results = await asyncio.gather(*(loop.run(t, initial={"answer": "wrong"}) for t in tasks))
    assert len({r.run_id for r in results}) == 64
    assert [r.output for r in results] == [{"answer": str(i)} for i in range(64)]
    assert all(r.status == "passed" and r.repair_rounds == 1 for r in results)
    assert [t.source["facts"]["value"] for t in tasks] == list(range(64))


async def test_cancelling_one_run_does_not_cancel_other_runs_on_the_same_loop():
    entered = asyncio.Event()

    async def judge(request):
        if request.task.source["facts"]["value"] == 1:
            entered.set()
            await asyncio.sleep(100)
        return PASS

    loop = QualityLoop(judge=FunctionJudge(judge), repairer=ReplayRepairer([]))
    first = asyncio.create_task(loop.run(task(1), initial={"answer": "1"}))
    second = asyncio.create_task(loop.run(task(2), initial={"answer": "2"}))
    await entered.wait()
    first.cancel()
    outcomes = await asyncio.gather(first, second, return_exceptions=True)
    assert isinstance(outcomes[0], asyncio.CancelledError)
    assert outcomes[1].status == "passed" and outcomes[1].output == {"answer": "2"}


async def test_two_candidate_oscillation_is_stopped_before_a_third_judge():
    judge = ReplayJudge([FAIL, FAIL])
    result = await QualityLoop(
        judge=judge,
        repairer=ReplayRepairer([{"answer": "B"}, {"answer": "A"}]),
        budget=QualityBudget(max_repair_rounds=5),
    ).run(task(1), initial={"answer": "A"})
    assert result.reason == "no_progress" and result.output is None and judge.calls == 2


async def test_high_score_model_pass_cannot_override_a_business_gate():
    class FactGate:
        async def check(self, candidate, task):
            if candidate["answer"] != str(task.source["facts"]["value"]):
                return (JudgeIssue("grounding", "Amount differs from the authoritative snapshot"),)
            return ()

    result = await QualityLoop(
        judge=ReplayJudge([PASS, PASS]),
        repairer=ReplayRepairer([{"answer": "1"}]),
        gates=(FactGate(),),
    ).run(task(1), initial={"answer": "999"})
    assert result.status == "passed" and result.output == {"answer": "1"}
    assert result.rounds[0].verdict.status == "pass"
    assert result.rounds[0].effective_verdict.status == "fail"


async def test_repair_introducing_new_error_does_not_escape_rejudge():
    result = await QualityLoop(
        judge=ReplayJudge([FAIL, FAIL]),
        repairer=ReplayRepairer([{"answer": "new wrong value"}]),
        budget=QualityBudget(max_repair_rounds=1),
    ).run(task(1), initial={"answer": "old wrong value"})
    assert result.reason == "repair_budget" and result.output is None
    assert result.rounds[1].candidate == {"answer": "new wrong value"}
