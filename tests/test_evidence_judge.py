from dataclasses import replace

import pytest

from verifigen import (
    AgentResponseError,
    Criterion,
    EvidenceJudge,
    FunctionGenerator,
    QualityBudget,
    QualityLoop,
    QualityTask,
    ReplayRepairer,
    make_qwen3_8b_stack,
)
from verifigen.review import JudgeRequest

TASK = QualityTask(
    source={"amount": 799},
    prompt="Explain the amount.",
    criteria=(Criterion("grounding", "Use only source facts."),),
    output_schema={"type": "object", "required": ["answer"]},
)


def check(status="pass", criterion="grounding"):
    return {
        "criterion_id": criterion,
        "statement": "The amount is 799",
        "status": status,
        "evidence": "The source amount is 799.",
    }


@pytest.mark.parametrize(
    "claim,criterion,status",
    [
        ("pass", "pass", "pass"),
        ("fail", "pass", "fail"),
        ("pass", "fail", "fail"),
        ("unknown", "pass", "fail"),
        ("pass", "unknown", "unknown"),
    ],
)
async def test_claim_verdict_is_aggregated_and_every_assessment_is_retained(
    claim, criterion, status
):
    judge = EvidenceJudge(
        FunctionGenerator(
            lambda request: {
                "claims": [check(claim)],
                "criteria": [check(criterion)],
            }
        )
    )
    response = await judge.judge(JudgeRequest(TASK, {"answer": "799"}, 0))
    assert response.verdict.status == status
    assert len(response.assessments) == 2
    assert [a.kind for a in response.assessments] == ["claim", "criterion"]
    assert len(response.verdict.issues) == (claim != "pass") + (criterion == "fail")
    assert response.verdict.score == (1 if status == "pass" else 0)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unexpected", "contradictory_vote"])
async def test_incomplete_or_unauthorized_assessment_payloads_fail_closed(mutation):
    content = {"claims": [check()], "criteria": [check()]}
    if mutation == "missing":
        content["criteria"] = []
    elif mutation == "duplicate":
        content["criteria"].append(check())
    elif mutation == "unexpected":
        content["claims"][0]["criterion_id"] = "hidden_gold"
    else:
        content["status"] = "pass"
    with pytest.raises(AgentResponseError) as caught:
        await EvidenceJudge(FunctionGenerator(lambda request: content)).judge(
            JudgeRequest(TASK, {"answer": "799"}, 0)
        )
    assert caught.value.usage.total_tokens == 0


async def test_fulfillment_failure_cannot_be_published_and_checks_reach_trace():
    task = replace(TASK, criteria=(*TASK.criteria, Criterion("fulfillment", "Answer the question")))
    judge = EvidenceJudge(
        FunctionGenerator(
            lambda request: {
                "claims": [check()],
                "criteria": [check(), check("fail", "fulfillment")],
            }
        )
    )
    result = await QualityLoop(
        judge=judge,
        repairer=ReplayRepairer([]),
        budget=QualityBudget(max_repair_rounds=0),
    ).run(task, initial={"answer": "Generic placeholder"})
    assert result.output is None and result.reason == "repair_budget"
    assert len(result.rounds[0].assessments) == 3
    assert len(result.to_dict()["rounds"][0]["assessments"]) == 3


async def test_empty_claims_are_repairable_for_failed_task_but_never_allow_publication():
    for criterion, expected in (("fail", "fail"), ("unknown", "unknown"), ("pass", None)):
        judge = EvidenceJudge(
            FunctionGenerator(
                lambda request, criterion=criterion: {
                    "claims": [],
                    "criteria": [check(criterion)],
                }
            )
        )
        if expected is None:
            with pytest.raises(AgentResponseError):
                await judge.judge(JudgeRequest(TASK, {"answer": ""}, 0))
        else:
            response = await judge.judge(JudgeRequest(TASK, {"answer": ""}, 0))
            assert response.verdict.status == expected


async def test_claim_uncertainty_can_be_repaired_but_cannot_escape_a_final_check():
    def assess(request):
        status = "pass" if request.previous == {"answer": "799"} else "unknown"
        return {"claims": [check(status)], "criteria": [check()]}

    result = await QualityLoop(
        judge=EvidenceJudge(FunctionGenerator(assess)),
        repairer=ReplayRepairer([{"answer": "799"}]),
    ).run(TASK, initial={"answer": "799 plus an unsupported attribute"})
    assert result.output == {"answer": "799"} and result.repair_rounds == 1
    assert result.rounds[0].verdict.status == "fail"
    assert result.rounds[0].assessments[0].status == "unknown"
    assert result.rounds[1].verdict.status == "pass"


async def test_source_first_refinement_preserves_evidence_and_existing_shared_budgets():
    requests = []

    def revise(request):
        requests.append(request)
        return {"answer": "799"}

    judge = EvidenceJudge(
        FunctionGenerator(
            lambda request: {
                "claims": [check()],
                "criteria": [check()],
            }
        )
    )
    result = await QualityLoop(
        judge=judge,
        repairer=ReplayRepairer([]),
        initial_refiner=FunctionGenerator(revise),
        refinement_mode="source_first",
        budget=QualityBudget(max_repair_rounds=1),
    ).run(TASK, initial={"answer": "899"})
    assert result.output == {"answer": "799"} and result.repair_rounds == 1
    assert requests[0].source == TASK.source
    assert requests[0].previous == {"answer": "899"}
    assert "untrusted draft, not evidence" in requests[0].instructions
    assert result.trace[0].details["refinement_mode"] == "source_first"


def test_claim_strategy_factory_and_incompatible_flags_are_explicit():
    assert isinstance(
        make_qwen3_8b_stack(api_key="test", judge_strategy="claims").judge, EvidenceJudge
    )
    with pytest.raises(ValueError):
        make_qwen3_8b_stack(api_key="test", judge_strategy="claims", validate_judge_quotes=True)
    with pytest.raises(ValueError):
        QualityLoop(
            judge=EvidenceJudge(FunctionGenerator(lambda request: {})),
            repairer=ReplayRepairer([]),
            refinement_mode="invalid",
        )
