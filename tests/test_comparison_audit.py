import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "mutation",
    ["revision_budget", "accounting", "final_candidate", "review_packet", "duplicate_review"],
)
def test_audit_rejects_tampered_release_or_accounting(tmp_path, mutation):
    source = ROOT / "benchmarks/results/ragtruth-optimized-eval-60"
    for name in (
        "config.json",
        "summary.json",
        "review-mapping.jsonl",
        "reviews.jsonl",
        "blind-packets.jsonl",
    ):
        (tmp_path / name).write_bytes((source / name).read_bytes())
    rows = [json.loads(line) for line in (source / "records.jsonl").read_text().splitlines()]
    row = next(r for r in rows if r["arm"] == "quality_loop" and r["status"] == "passed")
    if mutation == "revision_budget":
        row["runtime"]["repair_rounds"] = 999
    elif mutation == "accounting":
        row["runtime"]["model_calls"] += 1
    elif mutation == "final_candidate":
        row["runtime"]["rounds"][-1]["candidate"] = {"answer": "Unverified replacement"}
    elif mutation == "review_packet":
        packets = [
            json.loads(line) for line in (tmp_path / "blind-packets.jsonl").read_text().splitlines()
        ]
        packets[0]["candidate"] = {"answer": "Changed reviewer input"}
        (tmp_path / "blind-packets.jsonl").write_text(
            "".join(json.dumps(p) + "\n" for p in packets)
        )
    else:
        reviews = (tmp_path / "reviews.jsonl").read_text()
        (tmp_path / "reviews.jsonl").write_text(reviews + reviews.splitlines()[0] + "\n")
    (tmp_path / "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/audit_comparison.py"), "--results", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and "Audit failed:" in result.stderr
    expected = {
        "revision_budget": "Revision ceiling exceeded",
        "accounting": "Runtime accounting differs",
        "final_candidate": "Release differs from its final passing candidate",
        "review_packet": "Anonymous review packets differ",
        "duplicate_review": "Review set incomplete",
    }
    assert expected[mutation] in result.stderr


@pytest.mark.parametrize(
    "experiment",
    [
        "ragtruth-comparison-60",
        "ragtruth-optimized-dev-30",
        "ragtruth-quoted-dev-30",
        "ragtruth-json-dev-30",
        "ragtruth-optimized-eval-60",
        "ragtruth-plus-judge-dev-30",
        "ragtruth-evidence-dev-30",
        "ragtruth-source-first-dev-30",
        "ragtruth-evidence-v2-dev-30",
        "ragtruth-evidence-plus-dev-30",
        "ragtruth-evidence-plus-restored-dev-30",
        "ragtruth-evidence-plus-eval-60",
    ],
)
def test_published_comparison_passes_audit(experiment):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/audit_comparison.py"),
            "--results",
            str(ROOT / "benchmarks/results" / experiment),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "mutation", ["unresolved", "missing_criterion", "unknown_criterion", "empty_claims"]
)
def test_audit_rejects_invalid_assessments_in_passing_release(tmp_path, mutation):
    source = ROOT / "benchmarks/results/ragtruth-evidence-dev-30"
    for name in (
        "config.json",
        "summary.json",
        "review-mapping.jsonl",
        "reviews.jsonl",
        "blind-packets.jsonl",
    ):
        (tmp_path / name).write_bytes((source / name).read_bytes())
    rows = [json.loads(line) for line in (source / "records.jsonl").read_text().splitlines()]
    row = next(r for r in rows if r["arm"] == "refine_verify" and r["status"] == "passed")
    final = row["runtime"]["rounds"][-1]
    if mutation == "unresolved":
        final["assessments"][0]["status"] = "unknown"
    elif mutation == "missing_criterion":
        final["assessments"] = [a for a in final["assessments"] if a["kind"] != "criterion"]
    elif mutation == "unknown_criterion":
        final["assessments"][0]["criterion_id"] = "invented"
    else:
        final["assessments"] = [a for a in final["assessments"] if a["kind"] != "claim"]
    (tmp_path / "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/audit_comparison.py"), "--results", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    expected = (
        "Claim-assessed release has invalid criterion coverage"
        if mutation in ("missing_criterion", "unknown_criterion")
        else "Claim-assessed release contains unresolved checks"
    )
    assert expected in result.stderr
