from copy import deepcopy

import pytest

from verifigen import Budget, Context, Harness, ReplayGenerator
from verifigen.domains.support import (
    demo_bad_draft,
    demo_source,
    make_support_contract,
    template_response,
)
from verifigen.evaluation import score_output
from verifigen.generators import FunctionGenerator


async def test_all_annotated_scenarios(case, context_for):
    # Gold values come from the separately authored corpus, never from a verifier.
    source = deepcopy(case["source"])
    candidate = deepcopy(case["candidate"])
    generator = FunctionGenerator(lambda request: template_response(request.source))
    result = await Harness(make_support_contract(), generator).run(
        source=source, initial=candidate, context=context_for(case)
    )
    assert score_output(result.output, case["gold"])
    assert result.status == ("fallback" if case["gold"] is None else "passed")
    assert source == case["source"] and candidate == case["candidate"]
    if case["gold"] is not None:
        assert result.report.status == "pass"
        if case["mutation"] != "schema_missing":
            assert result.model_calls == 0
            assert result.output["tone"] == case["candidate"]["tone"]


async def test_wrong_numbers_and_wrong_commitments_are_repaired_together():
    source = demo_source()
    draft = demo_bad_draft(source)
    result = await Harness(make_support_contract()).run(source=source, initial=draft)
    assert result.status == "passed"
    assert "799.00" in result.text and "899.00" not in result.text
    assert "订单已经发货" in result.text and "订单已取消" not in result.text
    assert "当前没有退款申请" in result.text and "已到账" not in result.text
    staged = next(event for event in result.trace if event.event == "repair_staged")
    assert {"/refund_state", "/next_step", "/sections/next_step"} <= set(
        staged.details["affected_paths"]
    )


@pytest.mark.parametrize("bad_value", ["79900", 79900.0, True, -1, 0])
async def test_money_schema_does_not_coerce_or_accept_invalid_values(bad_value):
    source = demo_source()
    draft = template_response(source)
    draft["paid_cents"] = bad_value
    result = await Harness(make_support_contract()).run(source=source, initial=draft)
    assert result.status == "fallback"
    assert result.output is None


async def test_extra_unverified_text_is_not_published():
    source = demo_source()
    draft = template_response(source)
    draft["free_text"] = "已赔偿999元"
    result = await Harness(make_support_contract()).run(source=source, initial=draft)
    assert result.output is None and "999" not in result.text


async def test_missing_evidence_does_not_spend_a_model_call():
    source = demo_source()
    del source["refund"]["receipt"]
    generator = ReplayGenerator([{}])
    result = await Harness(make_support_contract(), generator).run(source=source)
    assert result.reason == "evidence_unavailable"
    assert generator.calls == 0


async def test_processing_receipt_does_not_prove_settlement():
    source = demo_source()
    source["refund"] = {
        "request_id": "R1",
        "requested_cents": 30000,
        "approved_cents": 20000,
        "receipt": {
            "order_id": source["order"]["id"],
            "request_id": "R1",
            "status": "processing",
            "amount_cents": 20000,
            "currency": "CNY",
        },
    }
    result = await Harness(make_support_contract()).run(
        source=source, initial=demo_bad_draft(source)
    )
    assert result.output["refund_cents"] == 20000
    assert result.output["refund_state"] == "processing"
    assert "尚未确认到账" in result.text


async def test_context_cannot_be_substituted_from_another_order():
    source = demo_source()
    ctx = Context.create(source)
    other = deepcopy(source)
    other["order"]["id"] = "OTHER"
    with pytest.raises(ValueError, match="same source"):
        await Harness(make_support_contract()).run(source=other, initial={}, context=ctx)


async def test_no_repairs_budget_leaves_invalid_draft_unpublished():
    source = demo_source()
    result = await Harness(make_support_contract(), budget=Budget(max_repair_rounds=0)).run(
        source=source, initial=demo_bad_draft(source)
    )
    assert result.reason == "repair_budget" and result.output is None
