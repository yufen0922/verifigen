import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from verifigen import FunctionJudge, FunctionRepairer, JudgeIssue, JudgeVerdict, QualityLoop
from verifigen.domains.report_review import make_report_task
from verifigen.domains.support_review import make_support_task
from verifigen.scenario_eval import (
    inspect_report_output,
    inspect_support_output,
    score_report_output,
    score_support_output,
)

ROOT = Path(__file__).resolve().parents[1]
SUPPORT_CASES = ROOT / "examples" / "customer_support" / "eval_cases.jsonl"
REPORT_CASES = ROOT / "examples" / "data_to_text" / "eval_cases.jsonl"


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_each_new_scenario_has_sixty_balanced_labeled_cases():
    for path, scorer in (
        (SUPPORT_CASES, score_support_output),
        (REPORT_CASES, score_report_output),
    ):
        cases = jsonl(path)
        assert len(cases) == 60
        assert len({case["id"] for case in cases}) == 60
        assert set(Counter(case["scenario"] for case in cases).values()) == {10}
        assert Counter(case["initial_should_pass"] for case in cases) == {True: 6, False: 54}
        for case in cases:
            assert scorer(case["expected"], case)
            assert scorer(case["initial"], case) == case["initial_should_pass"]


def test_multiscenario_fixture_builder_is_deterministic(tmp_path):
    support = tmp_path / "support.jsonl"
    report = tmp_path / "report.jsonl"
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_multiscenario_eval.py"),
            "--support-output",
            str(support),
            "--report-output",
            str(report),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stderr
    assert jsonl(support) == jsonl(SUPPORT_CASES)
    assert jsonl(report) == jsonl(REPORT_CASES)


async def test_same_quality_loop_repairs_support_and_report_cases():
    specs = (
        (jsonl(SUPPORT_CASES)[1], make_support_task, inspect_support_output),
        (jsonl(REPORT_CASES)[1], make_report_task, inspect_report_output),
    )
    for case, task_factory, inspect in specs:

        def judge(request, *, _case=case, _inspect=inspect):
            failures = _inspect(request.candidate, _case)
            if not failures:
                return JudgeVerdict("pass", 0.98, "ok")
            return JudgeVerdict(
                "fail",
                0.2,
                "repair",
                tuple(JudgeIssue(item, "incorrect") for item in failures),
            )

        result = await QualityLoop(
            judge=FunctionJudge(judge),
            repairer=FunctionRepairer(lambda _request, _case=case: _case["expected"]),
        ).run(task_factory(case["source"]), initial=case["initial"])
        assert result.status == "passed"
        assert result.repair_rounds == 1
        assert result.text != str(result.output)


def test_unified_offline_evaluator_runs_all_three_scenarios(tmp_path):
    output = tmp_path / "result.json"
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples" / "multi_scenario" / "evaluate.py"),
            "--limit-per-scenario",
            "10",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["cases"] == 30
    assert set(result["scenarios"]) == {"rag", "support", "report"}
    assert all(row["final_oracle_success"] == 1 for row in result["scenarios"].values())
