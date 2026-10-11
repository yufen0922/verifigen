import pytest

from verifigen.human_review import annotation_template, reconcile, score_outputs

PACKET = {
    "review_id": "anonymous",
    "task": "report amount",
    "evidence": {"paid": 799},
    "candidate": {"answer": "paid 899"},
}
PASS = {"grounding": "pass", "fulfillment": "pass", "explanation": "Supported"}
FAIL = {
    "grounding": "fail",
    "fulfillment": "pass",
    "explanation": "Wrong amount",
    "issues": [{"kind": "contradiction", "claim": "paid 899", "evidence": "paid 799"}],
}


def vote(who, review):
    return {**annotation_template([PACKET], who)[0], "review": review}


def test_export_is_unfilled_and_has_no_ground_truth():
    row = annotation_template([PACKET], "reviewer-a")[0]
    assert row["review"] is None and "arm" not in row and "initial_should_pass" not in row
    assert len(row["packet_sha256"]) == 64


def test_two_independent_agreeing_reviews_resolve():
    result = reconcile([PACKET], [vote("a", PASS), vote("b", PASS)])
    assert result["resolved"] == 1 and result["dimension_agreement"] == 1
    assert result["results"][0]["status"] == "agreed"


def test_disagreement_requires_distinct_adjudicator():
    votes = [vote("a", PASS), vote("b", FAIL)]
    conflict = reconcile([PACKET], votes)
    assert conflict["resolved"] == 0 and conflict["unresolved_disagreements"] == 1
    resolved = reconcile([PACKET], votes, [vote("c", FAIL)])
    assert resolved["results"][0]["status"] == "adjudicated"
    assert resolved["results"][0]["review"]["grounding"] == "fail"
    with pytest.raises(ValueError, match="Adjudicator"):
        reconcile([PACKET], votes, [vote("a", FAIL)])


def test_single_reviewer_and_empty_templates_never_count_as_labels():
    pending = reconcile([PACKET], [vote("a", PASS)])
    assert pending["pending"] == 1 and pending["resolved"] == 0
    with pytest.raises(ValueError):
        reconcile([PACKET], annotation_template([PACKET], "a"))


def test_duplicate_reviewer_and_modified_packet_are_rejected():
    with pytest.raises(ValueError, match="twice"):
        reconcile([PACKET], [vote("a", PASS), vote("a", PASS)])
    with pytest.raises(ValueError, match="modified"):
        reconcile([{**PACKET, "candidate": {"answer": "changed"}}], [vote("a", PASS)])
    with pytest.raises(ValueError, match="missing"):
        reconcile([PACKET], [vote("a", PASS)], [vote("b", FAIL)])


def test_unknown_agreement_remains_unknown_not_correct():
    unknown = {
        "grounding": "unknown",
        "fulfillment": "unknown",
        "explanation": "Conflicting source",
    }
    result = reconcile([PACKET], [vote("a", unknown), vote("b", unknown)])
    assert result["results"][0]["review"]["grounding"] == "unknown"


def test_partial_human_reviews_cannot_produce_a_repair_success_claim():
    from verifigen.jsonutil import digest

    rows = [{"id": "1", "status": "passed", "output": {"answer": "paid 799"}}]
    identifier = digest({"sample": "1", "candidate": rows[0]["output"]})
    packet = {**PACKET, "review_id": identifier, "candidate": rows[0]["output"]}
    votes = [{**annotation_template([packet], who)[0], "review": PASS} for who in ("a", "b")]
    mapping = [{"id": "1", "arm": "quality_loop", "review_id": identifier}]
    samples = [{"id": "1", "response": "paid 899", "has_hallucination": True}]
    partial = score_outputs(rows, mapping, reconcile([packet], votes[:1]), samples)
    assert partial["arms"]["quality_loop"]["human_bad_initial_rescue_rate"] is None
    completed = score_outputs(rows, mapping, reconcile([packet], votes), samples)
    assert completed["arms"]["quality_loop"]["human_bad_initial_rescue_rate"] == 1
    assert completed["arms"]["quality_loop"]["human_usable_yield"] == 1
    with pytest.raises(ValueError, match="mapping"):
        score_outputs(
            [{**rows[0], "output": {"answer": "changed"}}],
            mapping,
            reconcile([packet], votes),
            samples,
        )
