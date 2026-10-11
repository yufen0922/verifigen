import pytest

from verifigen.calibration import threshold_curve


def rows():
    samples = [
        {"id": "1", "local_split": "dev", "has_hallucination": False},
        {"id": "2", "local_split": "dev", "has_hallucination": True},
        {"id": "3", "local_split": "dev", "has_hallucination": True},
    ]
    records = [
        {
            "id": s["id"],
            "initial_should_pass": not s["has_hallucination"],
            "verdicts": [{"status": "pass", "score": score}],
            "gate_reports": [],
        }
        for s, score in zip(samples, (0.95, 0.8, 0.99), strict=True)
    ]
    records[2]["gate_reports"] = [{"round_index": 0, "issues": [{"message": "invalid"}]}]
    return samples, records


def test_threshold_curve_respects_score_and_hard_gates():
    samples, records = rows()
    result = threshold_curve(records, samples, (0.8, 0.9, 1.0))
    assert [r["released"] for r in result["curve"]] == [2, 1, 0]
    assert result["curve"][0]["wrong_release_rate"] == 0.5
    assert result["curve"][1]["release_label_precision"] == 1
    assert result["curve"][2]["release_label_precision"] is None
    assert result["automatically_selected_threshold"] is None


def test_threshold_tuning_rejects_eval_data_and_label_drift():
    samples, records = rows()
    with pytest.raises(ValueError, match="development"):
        threshold_curve(records, [{**samples[0], "local_split": "eval"}, *samples[1:]])
    with pytest.raises(ValueError, match="label"):
        threshold_curve([{**records[0], "initial_should_pass": False}, *records[1:]], samples)
    with pytest.raises(ValueError, match="Duplicate"):
        threshold_curve(records + records, samples)


@pytest.mark.parametrize("thresholds", [[], [-0.1], [1.1], [float("nan")]])
def test_invalid_thresholds_are_rejected(thresholds):
    samples, records = rows()
    with pytest.raises(ValueError):
        threshold_curve(records, samples, thresholds)


def test_errors_and_abstentions_are_never_released():
    samples, records = rows()
    records[0]["verdicts"] = []
    records[1]["verdicts"][0]["status"] = "unknown"
    assert threshold_curve(records, samples)["curve"][0]["released"] == 0
