import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from verifigen.ragtruth import has_hallucination, make_ragtruth_task, read_jsonl, select_samples

DATA = Path(__file__).resolve().parents[1] / "benchmarks/data/ragtruth-600"


def test_public_cohort_integrity_group_isolation_and_balanced_quotas():
    samples = read_jsonl(DATA / "samples.jsonl")
    selection = read_jsonl(DATA / "selection.jsonl")
    manifest = json.loads((DATA / "manifest.json").read_text())
    assert len(samples) == len(selection) == 600
    assert len({s["id"] for s in samples}) == 600
    assert len({s["source_id"] for s in samples}) == 451
    assert (
        hashlib.sha256((DATA / "samples.jsonl").read_bytes()).hexdigest()
        == manifest["samples_sha256"]
    )
    assert (
        hashlib.sha256((DATA / "selection.jsonl").read_bytes()).hexdigest()
        == manifest["selection_sha256"]
    )
    groups = {}
    counts = Counter()
    for sample in samples:
        key = sample["source_id"]
        assert groups.setdefault(key, sample["local_split"]) == sample["local_split"]
        assert sample["quality"] == "good"
        assert sample["has_hallucination"] == has_hallucination(sample["labels"])
        counts[sample["task_type"], sample["local_split"], sample["has_hallucination"]] += 1
    for task in ("QA", "Summary", "Data2txt"):
        for bad in (False, True):
            assert counts[task, "dev", bad] == 30
            assert counts[task, "eval", bad] == 70


def test_implicit_true_annotation_does_not_create_hallucination_positive():
    assert not has_hallucination([{"implicit_true": True}])
    assert has_hallucination([{"implicit_true": True}, {"text": "unsupported"}])


def test_ragtruth_adapter_keeps_gold_out_of_model_context():
    sample = read_jsonl(DATA / "samples.jsonl")[0]
    task = make_ragtruth_task(sample)
    assert set(task.source) == {"task_type", "source_info"}
    assert "labels" not in task.source and "has_hallucination" not in task.source
    assert task.prompt == sample["prompt"]
    assert task.output_schema["required"] == ["answer"]


def test_selection_rejects_missing_sources_instead_of_silent_dropping():
    with pytest.raises(ValueError, match="missing source"):
        select_samples([{"id": "1", "source_id": "missing"}], [])


def test_selection_rebuilds_same_manifest_from_shuffled_cohort():
    samples = read_jsonl(DATA / "samples.jsonl")
    sources = list({s["source_id"]: s for s in samples}.values())
    assert select_samples(list(reversed(samples)), sources) == read_jsonl(DATA / "selection.jsonl")
