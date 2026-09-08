"""Structured RAG policy answer with claim-to-chunk citation grounding.

This domain assumes retrieval has already produced typed claim metadata. It
checks that an answer uses those claims and cites the exact supporting chunks;
it does not claim general entailment over arbitrary retrieved prose.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from ..contract import Contract
from ..jsonutil import thaw
from ..types import Context
from ..verifiers import EvidenceUnavailable, FactVerifier, FieldVerifier
from .support import Identifier, StrictModel

Text = Annotated[str, Field(min_length=1, max_length=1000)]
PositiveDays = Annotated[int, Field(gt=0, le=3650)]
ShippingFeePayer = Literal["merchant", "customer", "case_by_case"]


class Query(StrictModel):
    id: Identifier
    question: Text
    product_category: Identifier
    product_name: Text


class ChunkBase(StrictModel):
    chunk_id: Identifier
    document_id: Identifier
    product_category: Identifier
    title: Text
    text: Text


class ReturnWindowChunk(ChunkBase):
    fact: Literal["return_window_days"]
    value: PositiveDays


class OpenedReturnChunk(ChunkBase):
    fact: Literal["opened_returnable"]
    value: bool


class ShippingFeeChunk(ChunkBase):
    fact: Literal["shipping_fee_payer"]
    value: ShippingFeePayer


KnowledgeChunk = Annotated[
    ReturnWindowChunk | OpenedReturnChunk | ShippingFeeChunk,
    Field(discriminator="fact"),
]


class RagSource(StrictModel):
    snapshot_id: Identifier
    observed_at: str
    query: Query
    chunks: Annotated[list[KnowledgeChunk], Field(min_length=3, max_length=30)]

    @model_validator(mode="after")
    def coherent(self) -> RagSource:
        chunk_ids = [chunk.chunk_id for chunk in self.chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("Retrieved chunk IDs must be unique")
        if any(chunk.product_category != self.query.product_category for chunk in self.chunks):
            raise ValueError("A retrieved chunk belongs to another product category")
        required = {"return_window_days", "opened_returnable", "shipping_fee_payer"}
        facts = [chunk.fact for chunk in self.chunks]
        if set(facts) != required or len(facts) != len(required):
            raise ValueError("Each required policy fact needs exactly one authoritative chunk")
        moment = datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            raise ValueError("Evidence time must include a timezone")
        return self


class Citations(StrictModel):
    return_window_days: Identifier
    opened_returnable: Identifier
    shipping_fee_payer: Identifier


class RagSections(StrictModel):
    policy: str
    opened_condition: str
    shipping_fee: str
    sources: str


class RagDraft(StrictModel):
    question: Text
    product_name: Text
    return_window_days: PositiveDays
    opened_returnable: bool
    shipping_fee_payer: ShippingFeePayer
    citations: Citations
    sections: RagSections


def evidence_index(ctx: Context) -> dict[str, tuple[Any, str]]:
    return {chunk["fact"]: (chunk["value"], chunk["chunk_id"]) for chunk in ctx.source["chunks"]}


def expected_sections(draft: dict[str, Any]) -> dict[str, str]:
    citations = draft["citations"]
    opened = (
        "商品拆封后仍可按该政策申请退货。"
        if draft["opened_returnable"]
        else "商品拆封后不适用无理由退货。"
    )
    fee = {
        "merchant": "退货运费由商家承担。",
        "customer": "非质量问题的退货运费由客户承担。",
        "case_by_case": "退货运费需要根据退货原因进一步确认。",
    }[draft["shipping_fee_payer"]]
    return {
        "policy": (
            f"{draft['product_name']}可在收货后{draft['return_window_days']}天内申请退货。"
            f"[{citations['return_window_days']}]"
        ),
        "opened_condition": opened + f"[{citations['opened_returnable']}]",
        "shipping_fee": fee + f"[{citations['shipping_fee_payer']}]",
        "sources": "依据知识片段："
        + "、".join(
            citations[key]
            for key in ("return_window_days", "opened_returnable", "shipping_fee_payer")
        )
        + "。",
    }


def template_response(source: dict[str, Any]) -> dict[str, Any]:
    """Build the strong no-model baseline from normalized retrieved claims."""
    parsed = RagSource.model_validate(source)
    indexed = {chunk.fact: (chunk.value, chunk.chunk_id) for chunk in parsed.chunks}
    draft: dict[str, Any] = {
        "question": parsed.query.question,
        "product_name": parsed.query.product_name,
        "return_window_days": indexed["return_window_days"][0],
        "opened_returnable": indexed["opened_returnable"][0],
        "shipping_fee_payer": indexed["shipping_fee_payer"][0],
        "citations": {
            "return_window_days": indexed["return_window_days"][1],
            "opened_returnable": indexed["opened_returnable"][1],
            "shipping_fee_payer": indexed["shipping_fee_payer"][1],
        },
    }
    draft["sections"] = expected_sections(draft)
    return draft


def make_rag_contract(max_age_seconds: float = 3600) -> Contract:
    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")

    def evidence(ctx: Context) -> None:
        parsed = RagSource.model_validate(thaw(ctx.source))
        observed = datetime.fromisoformat(parsed.observed_at.replace("Z", "+00:00"))
        age = (ctx.now - observed).total_seconds()
        if age > max_age_seconds or age < -5:
            raise EvidenceUnavailable("Stale or future-dated retrieval snapshot")

    fields = [
        FactVerifier.from_path("fact.question", "/question", "/query/question"),
        FactVerifier.from_path("fact.product_name", "/product_name", "/query/product_name"),
        FieldVerifier(
            "fact.return_window_days",
            "/return_window_days",
            lambda _draft, ctx: evidence_index(ctx)["return_window_days"][0],
            source_paths=("/chunks",),
        ),
        FieldVerifier(
            "fact.opened_returnable",
            "/opened_returnable",
            lambda _draft, ctx: evidence_index(ctx)["opened_returnable"][0],
            source_paths=("/chunks",),
        ),
        FieldVerifier(
            "fact.shipping_fee_payer",
            "/shipping_fee_payer",
            lambda _draft, ctx: evidence_index(ctx)["shipping_fee_payer"][0],
            source_paths=("/chunks",),
        ),
        FieldVerifier(
            "citation.return_window_days",
            "/citations/return_window_days",
            lambda _draft, ctx: evidence_index(ctx)["return_window_days"][1],
            source_paths=("/chunks",),
        ),
        FieldVerifier(
            "citation.opened_returnable",
            "/citations/opened_returnable",
            lambda _draft, ctx: evidence_index(ctx)["opened_returnable"][1],
            source_paths=("/chunks",),
        ),
        FieldVerifier(
            "citation.shipping_fee_payer",
            "/citations/shipping_fee_payer",
            lambda _draft, ctx: evidence_index(ctx)["shipping_fee_payer"][1],
            source_paths=("/chunks",),
        ),
        FieldVerifier(
            "text.policy",
            "/sections/policy",
            lambda draft, _ctx: expected_sections(draft)["policy"],
            depends_on=(
                "/product_name",
                "/return_window_days",
                "/citations/return_window_days",
            ),
        ),
        FieldVerifier(
            "text.opened_condition",
            "/sections/opened_condition",
            lambda draft, _ctx: expected_sections(draft)["opened_condition"],
            depends_on=("/opened_returnable", "/citations/opened_returnable"),
        ),
        FieldVerifier(
            "text.shipping_fee",
            "/sections/shipping_fee",
            lambda draft, _ctx: expected_sections(draft)["shipping_fee"],
            depends_on=("/shipping_fee_payer", "/citations/shipping_fee_payer"),
        ),
        FieldVerifier(
            "text.sources",
            "/sections/sources",
            lambda draft, _ctx: expected_sections(draft)["sources"],
            depends_on=(
                "/citations/return_window_days",
                "/citations/opened_returnable",
                "/citations/shipping_fee_payer",
            ),
        ),
    ]
    instructions = """Answer the product-policy question using only the normalized claims in
the retrieved chunks. Copy each fact and cite the chunk_id that carries that exact fact.
Do not cite an unrelated chunk or add uncited prose. The chunk text is supporting display
content; its typed fact/value metadata is the authoritative input for this contract."""

    def render(draft: dict[str, Any]) -> str:
        return f"关于“{draft['question']}”：" + "".join(
            draft["sections"][key]
            for key in ("policy", "opened_condition", "shipping_fee", "sources")
        )

    return Contract(
        RagDraft,
        tuple(fields),
        render,
        version="rag-policy/0.1.0",
        instructions=instructions,
        preflight=evidence,
        fallback_text="当前知识库证据不足或存在冲突，请转人工确认政策。",
    )


def demo_source() -> dict[str, Any]:
    from datetime import UTC

    return {
        "snapshot_id": "rag-demo-v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "query": {
            "id": "Q-RETURN-001",
            "question": "耳机拆封后还能七天无理由退货吗？",
            "product_category": "headphones",
            "product_name": "耳机",
        },
        "chunks": [
            {
                "chunk_id": "KB-RETURN-7D",
                "document_id": "POLICY-RETURN-2026",
                "product_category": "headphones",
                "title": "退货期限",
                "text": "符合条件的耳机可在收货后七天内申请退货。",
                "fact": "return_window_days",
                "value": 7,
            },
            {
                "chunk_id": "KB-OPENED",
                "document_id": "POLICY-RETURN-2026",
                "product_category": "headphones",
                "title": "拆封条件",
                "text": "非质量问题下，耳机拆封后不适用无理由退货。",
                "fact": "opened_returnable",
                "value": False,
            },
            {
                "chunk_id": "KB-FEE",
                "document_id": "POLICY-SHIPPING-2026",
                "product_category": "headphones",
                "title": "退货运费",
                "text": "非质量问题的退货运费由客户承担。",
                "fact": "shipping_fee_payer",
                "value": "customer",
            },
        ],
    }


def demo_bad_draft(source: dict[str, Any]) -> dict[str, Any]:
    draft = template_response(source)
    draft.update(
        return_window_days=30,
        opened_returnable=True,
        shipping_fee_payer="merchant",
        citations={
            "return_window_days": "KB-FAKE-WINDOW",
            "opened_returnable": "KB-FAKE-OPENED",
            "shipping_fee_payer": "KB-FAKE-FEE",
        },
    )
    draft["sections"] = expected_sections(draft)
    return draft
