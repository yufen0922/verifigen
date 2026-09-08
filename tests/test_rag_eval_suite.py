import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from verifigen.rag_eval import score_rag_output

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "examples" / "rag_qa" / "eval_cases.jsonl"
SMOKE = ROOT / "examples" / "rag_qa" / "eval_smoke.jsonl"


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_large_set_has_sixty_balanced_cases_and_matching_labels():
    cases = jsonl(CASES)
    assert len(cases) == 60
    assert len({case["id"] for case in cases}) == 60
    per_product = Counter(case["id"].split("--")[0] for case in cases)
    assert set(per_product) == {
        "headphones",
        "laptops",
        "clothing",
        "speakers",
        "tablets",
        "shoes",
    }
    assert all(count == 10 for count in per_product.values())
    assert Counter(case["initial_should_pass"] for case in cases) == {True: 6, False: 54}
    for case in cases:
        assert score_rag_output(case["initial"], case) == case["initial_should_pass"]


def test_legacy_smoke_set_still_scores_under_old_rule_shape():
    cases = jsonl(SMOKE)
    assert len(cases) == 6
    for case in cases:
        assert score_rag_output(case["initial"], case) == case["initial_should_pass"]


def test_generator_is_deterministic(tmp_path):
    generated = tmp_path / "eval_cases.jsonl"
    process = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_rag_eval.py"), "--output", str(generated)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stderr
    assert jsonl(generated) == jsonl(CASES)
