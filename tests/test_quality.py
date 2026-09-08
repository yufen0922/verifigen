import asyncio
from dataclasses import asdict, replace

from verifigen import (
    Criterion,
    FunctionJudge,
    FunctionRepairer,
    JudgeIssue,
    JudgeVerdict,
    LLMJudge,
    LLMRepairer,
    QualityBudget,
    QualityLoop,
    QualityTask,
    ReplayGenerator,
    ReplayJudge,
    ReplayRepairer,
)


def task(source=None):
    return QualityTask(
        source=source or {"facts": {"amount": 799}},
        prompt="Answer using the business facts.",
        criteria=(
            Criterion("grounding", "All facts must be supported by source."),
            Criterion("format", "Return the requested JSON object."),
        ),
        output_schema={"type": "object", "required": ["answer"]},
        instructions="Keep it concise.",
        fallback_text="fallback",
    )


FAIL = JudgeVerdict(
    "fail",
    0.2,
    "Wrong amount",
    (JudgeIssue("grounding", "899 is unsupported", "source amount is 799", "use 799"),),
)
PASS = JudgeVerdict("pass", 0.95, "All criteria pass")


async def test_fail_repair_pass_loop_publishes_repaired_candidate():
    result = await QualityLoop(
        judge=ReplayJudge([FAIL, PASS]),
        repairer=ReplayRepairer([{"answer": "paid 799"}]),
    ).run(task(), initial={"answer": "paid 899"})

    assert result.status == "passed" and result.reason == "judge_passed"
    assert result.output == {"answer": "paid 799"}
    assert result.text == "paid 799"
    assert result.repair_rounds == 1 and result.model_calls == 0
    assert [verdict.status for verdict in result.verdicts] == ["fail", "pass"]


async def test_pass_stops_without_repair():
    repairer = ReplayRepairer([])
    result = await QualityLoop(judge=ReplayJudge([PASS]), repairer=repairer).run(
        task(), initial={"answer": "paid 799"}
    )
    assert result.status == "passed" and repairer.calls == 0


async def test_unknown_fails_closed_but_retains_best_candidate_for_diagnostics():
    unknown = JudgeVerdict("unknown", 0.3, "Source is contradictory")
    draft = {"answer": "maybe"}
    result = await QualityLoop(judge=ReplayJudge([unknown]), repairer=ReplayRepairer([])).run(
        task(), initial=draft
    )
    assert result.status == "fallback" and result.reason == "judge_unknown"
    assert result.output is None and result.best_candidate == draft and result.text == "fallback"


async def test_same_repair_is_detected_as_no_progress():
    draft = {"answer": "paid 899"}
    result = await QualityLoop(judge=ReplayJudge([FAIL]), repairer=ReplayRepairer([draft])).run(
        task(), initial=draft
    )
    assert result.status == "fallback" and result.reason == "no_progress"


async def test_repair_budget_is_bounded():
    result = await QualityLoop(
        judge=ReplayJudge([FAIL]),
        repairer=ReplayRepairer([]),
        budget=QualityBudget(max_repair_rounds=0),
    ).run(task(), initial={"answer": "bad"})
    assert result.reason == "repair_budget" and result.repair_rounds == 0


async def test_model_call_budget_counts_generation_judge_and_repair():
    judge = LLMJudge(
        ReplayGenerator(
            [
                {
                    "status": "fail",
                    "score": 0.2,
                    "summary": "wrong",
                    "issues": [{"criterion_id": "grounding", "message": "wrong"}],
                }
            ]
        )
    )
    repairer = LLMRepairer(ReplayGenerator([{"revised_candidate": {"answer": "paid 799"}}]))
    result = await QualityLoop(
        generator=ReplayGenerator([{"answer": "paid 899"}]),
        judge=judge,
        repairer=repairer,
        budget=QualityBudget(max_model_calls=3),
    ).run(task())
    assert result.reason == "model_budget"
    assert result.model_calls == 3 and result.repair_rounds == 1


async def test_invalid_judge_payload_falls_back():
    result = await QualityLoop(
        judge=LLMJudge(ReplayGenerator([{"status": "pass"}])),
        repairer=ReplayRepairer([]),
    ).run(task(), initial={"answer": "draft"})
    assert result.status == "fallback" and result.reason == "judge_error"


async def test_low_score_pass_does_not_publish():
    result = await QualityLoop(
        judge=ReplayJudge([JudgeVerdict("pass", 0.5, "weak pass")]),
        repairer=ReplayRepairer([]),
    ).run(task(), initial={"answer": "draft"})
    assert result.status == "fallback" and result.reason == "score_below_threshold"


async def test_deadline_cancels_cooperative_judge():
    async def slow_judge(request):
        await asyncio.sleep(10)
        return PASS

    result = await QualityLoop(
        judge=FunctionJudge(slow_judge),
        repairer=ReplayRepairer([]),
        budget=QualityBudget(deadline_seconds=0.01),
    ).run(task(), initial={"answer": "draft"})
    assert result.status == "fallback" and result.reason == "deadline"


async def test_judge_and_repair_receive_full_task_candidate_and_verdict():
    observed = {}

    def inspect_judge(request):
        observed.setdefault("judges", []).append(
            {
                "source": request.task.source,
                "prompt": request.task.prompt,
                "candidate": request.candidate,
                "history": [asdict(item) for item in request.history],
            }
        )
        return FAIL if request.round_index == 0 else PASS

    def inspect_repair(request):
        observed["repair"] = {
            "source": request.task.source,
            "prompt": request.task.prompt,
            "candidate": request.candidate,
            "verdict": asdict(request.verdict),
        }
        return {"answer": "paid 799"}

    source = {"facts": {"amount": 799}, "private_context": "needed by judge"}
    result = await QualityLoop(
        judge=FunctionJudge(inspect_judge), repairer=FunctionRepairer(inspect_repair)
    ).run(task(source), initial={"answer": "paid 899"})

    assert result.status == "passed"
    assert observed["repair"]["source"] == source
    assert observed["repair"]["candidate"] == {"answer": "paid 899"}
    assert observed["repair"]["verdict"]["issues"][0]["criterion_id"] == "grounding"
    assert observed["judges"][1]["history"][0]["status"] == "fail"


async def test_task_renderer_controls_published_text():
    custom = task()
    custom = replace(custom, renderer=lambda candidate: f"value={candidate['answer']}")
    result = await QualityLoop(judge=ReplayJudge([PASS]), repairer=ReplayRepairer([])).run(
        custom, initial={"answer": "799"}
    )
    assert result.status == "passed" and result.text == "value=799"


async def test_task_renderer_error_falls_back_without_publishing_candidate():
    custom = replace(task(), renderer=lambda _candidate: "")
    result = await QualityLoop(judge=ReplayJudge([PASS]), repairer=ReplayRepairer([])).run(
        custom, initial={"answer": "private"}
    )
    assert result.status == "fallback" and result.reason == "renderer_error"
    assert result.output is None and result.text == custom.fallback_text


def test_quality_task_rejects_duplicate_criterion_ids():
    try:
        QualityTask({}, "task", (Criterion("same", "a"), Criterion("same", "b")))
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("duplicate criterion IDs were accepted")
