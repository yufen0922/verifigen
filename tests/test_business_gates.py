import copy
from pathlib import Path

import pytest

from verifigen import FunctionJudge, FunctionRepairer, JudgeVerdict, QualityBudget, QualityLoop
from verifigen.domains.report_review import ReportFactsGate, expected_report, make_report_task
from verifigen.domains.support_review import SupportFactsGate, make_support_task
from verifigen.ragtruth import read_jsonl

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("current,text", [(13, "增加13"), (-5, "减少5"), (0, "持平")])
def test_zero_baseline_report_does_not_reverse_direction(current, text):
    source = {
        "metric_name": "利润",
        "current": current,
        "previous": 0,
        "unit": "元",
        "current_period": "本月",
        "previous_period": "上月",
    }
    report = expected_report(source)
    assert report["change_rate_percent"] is None
    assert text in report["sentence"]


@pytest.mark.parametrize(
    "scenario,gate,factory",
    [
        ("customer_support", SupportFactsGate, make_support_task),
        ("data_to_text", ReportFactsGate, make_report_task),
    ],
)
async def test_business_gates_accept_authoritative_fields_across_all_patterns(
    scenario, gate, factory
):
    cases = read_jsonl(ROOT / f"examples/{scenario}/eval_cases.jsonl")
    for case in cases:
        task = factory(case["source"])
        assert not await gate().check(case["expected"], task)


@pytest.mark.parametrize(
    "scenario,gate,factory,field",
    [
        ("customer_support", SupportFactsGate, make_support_task, "paid_cents"),
        ("data_to_text", ReportFactsGate, make_report_task, "delta"),
    ],
)
async def test_hard_facts_reject_incorrect_release_despite_llm_pass(scenario, gate, factory, field):
    case = read_jsonl(ROOT / f"examples/{scenario}/eval_cases.jsonl")[0]
    draft = copy.deepcopy(case["expected"])
    draft[field] += 1
    result = await QualityLoop(
        judge=FunctionJudge(lambda r: JudgeVerdict("pass", 1, "Model missed the error")),
        repairer=FunctionRepairer(lambda r: case["expected"]),
        gates=(gate(),),
        budget=QualityBudget(max_repair_rounds=0),
    ).run(factory(case["source"]), initial=draft)
    assert result.status == "fallback" and result.output is None
    assert result.rounds[0].verdict.status == "pass"
    assert result.rounds[0].effective_verdict.status == "fail"
    assert any(field in issue.message for report in result.gate_reports for issue in report.issues)
