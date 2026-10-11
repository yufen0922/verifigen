import asyncio
from dataclasses import replace

import pytest

from verifigen import (
    AgentResponseError,
    Criterion,
    FunctionGenerator,
    JudgeIssue,
    JudgeVerdict,
    LLMJudge,
    LLMRepairer,
    QualityBudget,
    QualityLoop,
    QualityTask,
    ReplayJudge,
    ReplayRepairer,
)
from verifigen.generators import ProviderError
from verifigen.review import JudgeResponse
from verifigen.types import Generation, Usage

TASK = QualityTask(
    source={"amount": 799},
    prompt="Explain the amount.",
    criteria=(Criterion("grounding", "Use only supported facts."),),
    output_schema={
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    },
)
PASS = JudgeVerdict("pass", 1, "Supported")
FAIL = JudgeVerdict("fail", 0, "Wrong", (JudgeIssue("grounding", "Wrong amount"),))


class ScriptedModel:
    def __init__(self, contents):
        self.contents = iter(contents)

    async def generate(self, request):
        return Generation(next(self.contents), Usage(100, 20), "test")


async def test_invalid_judge_is_retried_once_with_all_usage_and_attempts_accounted():
    judge = LLMJudge(
        ScriptedModel(
            [
                {"status": "pass", "private": "SECRET"},
                {"status": "pass", "score": 1, "summary": "Supported", "issues": []},
            ]
        )
    )
    result = await QualityLoop(judge=judge, repairer=ReplayRepairer([])).run(
        TASK,
        initial={"answer": "799"},
    )
    assert result.status == "passed" and result.model_calls == 2
    assert [u.total_tokens for u in result.usages] == [120, 120]
    failures = [e.details for e in result.trace if e.event == "call_failed"]
    assert failures == [
        {"role": "judge", "category": "invalid_agent_response", "total_tokens": 120}
    ]
    assert "SECRET" not in str(result.trace)


async def test_protocol_retry_changes_the_instruction_not_the_evidence():
    class CapturingModel(ScriptedModel):
        def __init__(self):
            super().__init__(
                [{}, {"status": "pass", "score": 1, "summary": "Supported", "issues": []}]
            )
            self.requests = []

        async def generate(self, request):
            self.requests.append(request)
            return await super().generate(request)

    model = CapturingModel()
    result = await QualityLoop(judge=LLMJudge(model), repairer=ReplayRepairer([])).run(
        TASK,
        initial={"answer": "799"},
    )
    assert result.status == "passed" and len(model.requests) == 2
    assert "previous attempt failed" not in model.requests[0].instructions
    assert "previous attempt failed" in model.requests[1].instructions
    assert model.requests[0].source == model.requests[1].source
    assert model.requests[0].previous == model.requests[1].previous


@pytest.mark.parametrize(
    "budget,reason",
    [
        (QualityBudget(max_model_calls=1), "model_budget"),
        (QualityBudget(max_observed_tokens=100), "token_threshold"),
    ],
)
async def test_retry_cannot_escape_any_budget(budget, reason):
    result = await QualityLoop(
        judge=LLMJudge(ScriptedModel([{}])),
        repairer=ReplayRepairer([]),
        budget=budget,
    ).run(TASK, initial={"answer": "799"})
    assert result.reason == reason and result.model_calls == 1 and result.output is None
    assert result.usages[0].total_tokens == 120


async def test_retry_is_explicitly_bounded_and_can_be_disabled():
    for retries, expected in ((0, 1), (1, 2)):
        result = await QualityLoop(
            judge=LLMJudge(ScriptedModel([{}, {}])),
            repairer=ReplayRepairer([]),
            max_protocol_retries=retries,
        ).run(TASK, initial={"answer": "799"})
        assert result.reason == "judge_error" and result.model_calls == expected
        assert len(result.usages) == expected
    for invalid in (True, -1, 2):
        with pytest.raises(ValueError):
            QualityLoop(
                judge=ReplayJudge([]), repairer=ReplayRepairer([]), max_protocol_retries=invalid
            )


@pytest.mark.parametrize("error", [AgentResponseError("private"), ProviderError("private")])
async def test_unknown_billing_or_provider_failure_is_not_retried(error):
    class BrokenJudge:
        model_calls_per_request = 1

        async def judge(self, request):
            raise error

    result = await QualityLoop(judge=BrokenJudge(), repairer=ReplayRepairer([])).run(
        TASK,
        initial={"answer": "799"},
    )
    assert result.reason == "judge_error" and result.model_calls == 1
    assert result.usages[0].total_tokens is None
    assert not any(e.event == "protocol_retry" for e in result.trace)


async def test_invalid_repair_is_retried_without_using_an_extra_revision_round():
    repairer = LLMRepairer(ScriptedModel([{}, {"revised_candidate": {"answer": "799"}}]))
    result = await QualityLoop(judge=ReplayJudge([FAIL, PASS]), repairer=repairer).run(
        TASK,
        initial={"answer": "899"},
    )
    assert result.status == "passed" and result.repair_rounds == 1 and result.model_calls == 2
    assert sum(u.total_tokens for u in result.usages) == 240


async def test_initial_refinement_is_a_budgeted_edit_and_never_skips_final_judgment():
    judge = ReplayJudge([FAIL, PASS])
    result = await QualityLoop(
        initial_refiner=ScriptedModel([{"answer": "899"}]),
        judge=judge,
        repairer=ReplayRepairer([{"answer": "799"}]),
        judge_history="none",
    ).run(TASK, initial={"answer": "999"})
    assert result.output == {"answer": "799"} and result.repair_rounds == 2
    assert result.model_calls == 1 and judge.calls == 2
    assert result.rounds[0].round_index == 1 and result.rounds[1].round_index == 2
    assert result.trace[0].details["initial_refinement"] is True


async def test_unchanged_initial_refinement_is_not_a_failed_repair():
    result = await QualityLoop(
        initial_refiner=FunctionGenerator(lambda request: request.previous),
        judge=ReplayJudge([PASS]),
        repairer=ReplayRepairer([]),
    ).run(TASK, initial={"answer": "799"})
    assert result.status == "passed" and result.repair_rounds == 1
    assert [e.details["changed"] for e in result.trace if e.event == "initial_refined"] == [False]


async def test_initial_refinement_does_not_bypass_schema_or_revision_limit():
    for budget, candidate, reason in (
        (QualityBudget(max_repair_rounds=0), {"answer": "799"}, "repair_budget"),
        (QualityBudget(max_repair_rounds=1), {"invalid": "799"}, "repair_budget"),
    ):
        result = await QualityLoop(
            initial_refiner=ScriptedModel([candidate]),
            judge=ReplayJudge([PASS]),
            repairer=ReplayRepairer([]),
            budget=budget,
        ).run(TASK, initial={"answer": "799"})
        assert result.output is None and result.reason == reason


async def test_deadline_cancels_refinement_and_preserves_unknown_billing():
    class SlowModel:
        async def generate(self, request):
            await asyncio.sleep(10)

    result = await QualityLoop(
        initial_refiner=SlowModel(),
        judge=ReplayJudge([]),
        repairer=ReplayRepairer([]),
        budget=QualityBudget(deadline_seconds=0.01),
    ).run(TASK, initial={"answer": "799"})
    assert result.reason == "deadline" and result.model_calls == 1
    assert len(result.usages) == 1 and result.usages[0].total_tokens is None


async def test_business_failures_and_unknown_are_not_protocol_retries():
    class SemanticJudge:
        model_calls_per_request = 1

        async def judge(self, request):
            return JudgeResponse(JudgeVerdict("unknown", 0, "Evidence missing"), Usage(10, 10))

    result = await QualityLoop(judge=SemanticJudge(), repairer=ReplayRepairer([])).run(
        replace(TASK, source={}),
        initial={"answer": "799"},
    )
    assert result.reason == "judge_unknown" and result.model_calls == 1
    assert not any(e.event == "protocol_retry" for e in result.trace)
