import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from verifigen.benchmark import load_cases, run_benchmark
from verifigen.domains.support import demo_source, template_response
from verifigen.evaluation import regression_counts, score_output
from verifigen.generators import FunctionGenerator

ROOT = Path(__file__).resolve().parents[1]


async def test_paired_replay_and_ablation(tmp_path):
    result = await run_benchmark(ROOT / "benchmarks/data/test.jsonl", tmp_path)
    assert result["mode"] == "synthetic_replay" and result["cases"] == 60
    strategies = result["strategies"]
    assert strategies["dependency_repair"]["valid_answer_rate"] == 1.0
    assert strategies["template"]["valid_answer_rate"] == 1.0
    assert strategies["field_only_ablation"]["valid_answer_rate"] < 1.0
    assert strategies["dependency_repair"]["total_tokens"] == 0
    rows = [json.loads(line) for line in (tmp_path / "records.jsonl").read_text().splitlines()]
    assert len(rows) == 60 * 5
    assert (tmp_path / "report.md").exists()
    assert result["detection_case_level"]["fp"] == 0


async def test_live_mode_never_sends_gold_or_mutated_answers(tmp_path):
    requests = []

    def generate(request):
        requests.append(request)
        assert request.previous is None
        assert request.violations == ()
        return template_response(request.source)

    result = await run_benchmark(
        ROOT / "benchmarks/data/test.jsonl",
        tmp_path,
        live_generator=FunctionGenerator(generate),
        limit=2,
    )
    assert result["mode"] == "live" and len(requests) == 2
    assert result["strategies"]["dependency_repair"]["average_generation_calls"] == 1
    assert result["strategies"]["template"]["average_generation_calls"] == 0


def test_oracle_can_disagree_with_a_claimed_pass():
    gold = load_cases(ROOT / "benchmarks/data/dev.jsonl")[0]["gold"]
    wrong = json.loads(json.dumps(gold))
    wrong["paid_cents"] = 12345
    assert not score_output(wrong, gold)
    wrong["paid_cents"] = float(gold["paid_cents"])
    assert not score_output(wrong, gold)
    assert regression_counts(gold, wrong, gold)[0] == 1


def test_splits_have_disjoint_source_families():
    dev = load_cases(ROOT / "benchmarks/data/dev.jsonl")
    test = load_cases(ROOT / "benchmarks/data/test.jsonl")
    assert not {case["family"] for case in dev}.intersection(case["family"] for case in test)


def invoke(*args, env=None):
    return subprocess.run(
        [sys.executable, "-m", "verifigen.cli", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_no_key_demo_and_trace(tmp_path):
    process = invoke(
        "demo", "--trace", str(tmp_path / "trace.jsonl"), "--output", str(tmp_path / "result.json")
    )
    assert process.returncode == 0
    result = json.loads((tmp_path / "result.json").read_text())
    assert result["model_calls"] == 0 and result["status"] == "passed"
    assert "当前没有退款申请" in process.stdout


def test_live_configuration_error_without_keys(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(demo_source()))
    env = {key: value for key, value in os.environ.items() if not key.startswith("VERIFIGEN_")}
    process = invoke("live", "--source", str(source), env=env)
    assert process.returncode == 2 and "VERIFIGEN_API_KEY" in process.stderr


def test_live_benchmark_requires_explicit_limit():
    process = invoke("benchmark", "--dataset", "benchmarks/data/test.jsonl", "--live")
    assert process.returncode == 2 and "--limit" in process.stderr


def test_check_command(tmp_path):
    source = demo_source()
    draft = template_response(source)
    (tmp_path / "source.json").write_text(json.dumps(source))
    (tmp_path / "draft.json").write_text(json.dumps(draft))
    process = invoke(
        "check",
        "--source",
        str(tmp_path / "source.json"),
        "--candidate",
        str(tmp_path / "draft.json"),
    )
    assert process.returncode == 0


async def test_invalid_dataset_is_rejected(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("")
    with pytest.raises(ValueError, match="unique"):
        load_cases(path)
