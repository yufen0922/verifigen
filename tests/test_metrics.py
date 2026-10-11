import pytest

from verifigen.metrics import clustered_intervals, detection_correct, detection_metrics


@pytest.mark.parametrize("status", ["error", "unknown", "anything"])
@pytest.mark.parametrize("clean", [True, False])
def test_abstentions_and_errors_are_never_correct_detections(status, clean):
    assert not detection_correct(status, clean)


def test_detection_denominators_include_errors_and_separate_abstention():
    records = [
        {"initial_should_pass": clean, "first_judge_status": status}
        for clean, status in [
            (False, "fail"),
            (False, "error"),
            (False, "unknown"),
            (True, "pass"),
            (True, "fail"),
        ]
    ]
    metrics = detection_metrics(records)
    assert metrics["judge_detection_accuracy"] == 2 / 5
    assert metrics["error_detection_recall"] == 1 / 3
    assert metrics["false_alarm_rate"] == 1 / 2
    assert metrics["detection_precision"] == 1 / 2
    assert metrics["call_error_rate"] == 1 / 5
    assert metrics["abstention_rate"] == 1 / 5


def test_empty_detection_metrics_have_no_fabricated_accuracy():
    assert detection_metrics([])["judge_detection_accuracy"] is None


def test_f1_is_zero_when_both_defined_components_are_zero():
    records = [
        {"initial_should_pass": True, "first_judge_status": "fail"},
        {"initial_should_pass": False, "first_judge_status": "pass"},
    ]
    assert detection_metrics(records)["detection_f1"] == 0


def test_grouped_bootstrap_is_seeded_and_keeps_source_dependence():
    records = [
        {"source_id": source, "initial_should_pass": clean, "first_judge_status": status}
        for source, clean, status in [
            ("a", True, "pass"),
            ("a", False, "fail"),
            ("b", False, "pass"),
        ]
    ]
    result = clustered_intervals(records, iterations=100)
    assert result == clustered_intervals(records, iterations=100)
    assert result["source_groups"] == 2
    assert result["intervals"]["judge_detection_accuracy"] == [0.0, 1.0]
    assert result["intervals"]["false_alarm_rate"] == [0.0, 0.0]
    assert clustered_intervals([], iterations=100)["intervals"] == {}
    with pytest.raises(ValueError, match="100"):
        clustered_intervals(records, iterations=10)
