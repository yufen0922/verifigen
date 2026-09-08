from copy import deepcopy
from datetime import UTC, datetime, timedelta

from verifigen import Harness, ReplayGenerator
from verifigen.domains.rag import (
    demo_bad_draft,
    demo_source,
    make_rag_contract,
    template_response,
)


async def test_rag_facts_citations_and_dependent_text_are_repaired_together():
    source = demo_source()
    result = await Harness(make_rag_contract()).run(
        source=source,
        initial=demo_bad_draft(source),
    )

    assert result.status == "passed" and result.model_calls == 0
    assert result.output["return_window_days"] == 7
    assert result.output["opened_returnable"] is False
    assert result.output["shipping_fee_payer"] == "customer"
    assert result.output["citations"] == {
        "return_window_days": "KB-RETURN-7D",
        "opened_returnable": "KB-OPENED",
        "shipping_fee_payer": "KB-FEE",
    }
    assert "30天" not in result.text and "7天" in result.text
    assert "拆封后不适用" in result.text and "KB-FAKE" not in result.text


async def test_rag_clean_template_passes_without_repair():
    source = demo_source()
    result = await Harness(make_rag_contract()).run(
        source=source,
        initial=template_response(source),
    )
    assert result.status == "passed" and result.repair_rounds == 0


async def test_rag_invalid_chunks_fail_before_generation():
    missing = demo_source()
    missing["chunks"].pop()

    conflicting = demo_source()
    duplicate = deepcopy(conflicting["chunks"][0])
    duplicate["chunk_id"] = "KB-RETURN-CONFLICT"
    duplicate["value"] = 30
    conflicting["chunks"].append(duplicate)

    cross_category = demo_source()
    cross_category["chunks"][0]["product_category"] = "laptops"

    for source in (missing, conflicting, cross_category):
        generator = ReplayGenerator([{}])
        result = await Harness(make_rag_contract(), generator).run(source=source)
        assert result.reason == "evidence_unavailable"
        assert result.output is None and generator.calls == 0


async def test_rag_stale_snapshot_falls_back():
    source = demo_source()
    source["observed_at"] = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    result = await Harness(make_rag_contract(max_age_seconds=60)).run(
        source=source,
        initial=template_response(source),
    )
    assert result.reason == "evidence_unavailable"
    assert result.text == "当前知识库证据不足或存在冲突，请转人工确认政策。"
