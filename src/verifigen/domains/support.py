"""After-sales evidence -> controlled response plan.

This example reports existing state. It does not decide refund eligibility,
compute a new approved amount, execute a refund, or claim general text entailment.
Money is stored as integer CNY cents. One snapshot describes one current request.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..contract import Contract
from ..jsonutil import thaw
from ..types import Context
from ..verifiers import EvidenceUnavailable, FactVerifier, FieldVerifier, RuleVerifier

Money = Annotated[int, Field(ge=0, le=10**12)]
PositiveMoney = Annotated[int, Field(gt=0, le=10**12)]
Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
OrderStatus = Literal["paid", "shipped", "delivered", "cancelled"]
RefundState = Literal["not_requested", "requested", "approved", "processing", "settled", "failed"]
NextStep = Literal["submit_request", "await_review", "await_payout", "contact_support", "none"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Order(StrictModel):
    id: Identifier
    status: OrderStatus
    paid_cents: PositiveMoney
    currency: Literal["CNY"]
    refunded_before_cents: Money


class Receipt(StrictModel):
    order_id: Identifier
    request_id: Identifier
    status: Literal["processing", "settled", "failed"]
    amount_cents: PositiveMoney
    currency: Literal["CNY"]


class Refund(StrictModel):
    request_id: Identifier | None
    requested_cents: PositiveMoney | None
    approved_cents: PositiveMoney | None
    receipt: Receipt | None


class SupportSource(StrictModel):
    snapshot_id: Identifier
    observed_at: str
    order: Order
    refund: Refund

    @model_validator(mode="after")
    def coherent(self) -> SupportSource:
        order, refund = self.order, self.refund
        if order.refunded_before_cents > order.paid_cents:
            raise ValueError("Refund history exceeds paid amount")
        remaining = order.paid_cents - order.refunded_before_cents
        if (refund.request_id is None) != (refund.requested_cents is None):
            raise ValueError("A request requires both identity and amount")
        if refund.requested_cents is not None and refund.requested_cents > remaining:
            raise ValueError("This example accepts requests only within the remaining amount")
        if refund.approved_cents is not None:
            if refund.requested_cents is None or refund.approved_cents > refund.requested_cents:
                raise ValueError("Approval is unsupported by the request")
        if refund.receipt is not None:
            receipt = refund.receipt
            if receipt.order_id != order.id or receipt.request_id != refund.request_id:
                raise ValueError("Receipt belongs to another order/request")
            if receipt.currency != order.currency or receipt.amount_cents != refund.approved_cents:
                raise ValueError("Receipt and approval conflict")
        moment = datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            raise ValueError("Evidence time must include a timezone")
        return self


class Sections(StrictModel):
    payment: str
    fulfillment: str
    refund: str
    next_step: str


class SupportDraft(StrictModel):
    order_id: Identifier
    paid_cents: PositiveMoney
    order_status: OrderStatus
    refund_state: RefundState
    refund_cents: PositiveMoney | None
    next_step: NextStep
    tone: Literal["neutral", "empathetic"]
    sections: Sections


FULFILLMENT = {
    "paid": "订单已支付，尚未发货。",
    "shipped": "订单已经发货。",
    "delivered": "订单已签收。",
    "cancelled": "订单已取消。",
}
NEXT_ACTION = {
    "not_requested": "submit_request",
    "requested": "await_review",
    "approved": "await_payout",
    "processing": "await_payout",
    "settled": "none",
    "failed": "contact_support",
}
NEXT_TEXT = {
    "submit_request": "如需售后，可提交申请，由平台审核。",
    "await_review": "请等待平台审核退款申请。",
    "await_payout": "请关注后续退款状态，以实际到账结果为准。",
    "none": "可核对原支付渠道的到账记录。",
    "contact_support": "请联系人工客服核实退款失败原因。",
}


def money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def refund_facts(ctx: Context) -> tuple[str, int | None]:
    refund = ctx.source["refund"]
    receipt = refund["receipt"]
    if receipt is not None:
        return receipt["status"], receipt["amount_cents"]
    if refund["approved_cents"] is not None:
        return "approved", refund["approved_cents"]
    if refund["requested_cents"] is not None:
        return "requested", refund["requested_cents"]
    return "not_requested", None


def refund_sentence(draft: dict[str, Any]) -> str:
    state, cents = draft["refund_state"], draft["refund_cents"]
    if state == "not_requested":
        return "当前没有退款申请。"
    # A structurally valid but internally inconsistent draft is repairable. Keep a
    # placeholder in the intermediate expectation; the cross-field rule rejects it.
    amount = "待核实" if cents is None else money(cents)
    return {
        "requested": f"已申请退款{amount}元，等待审核。",
        "approved": f"退款{amount}元已审核通过，尚未到账。",
        "processing": f"退款{amount}元正在处理中，尚未确认到账。",
        "settled": f"本次退款{amount}元已到账。",
        "failed": f"本次退款{amount}元处理失败，需人工核实。",
    }[state]


def expected_sections(draft: dict[str, Any]) -> dict[str, str]:
    return {
        "payment": f"订单{draft['order_id']}实付{money(draft['paid_cents'])}元。",
        "fulfillment": FULFILLMENT[draft["order_status"]],
        "refund": refund_sentence(draft),
        "next_step": NEXT_TEXT[draft["next_step"]],
    }


def template_response(source: dict[str, Any], tone: str = "neutral") -> dict[str, Any]:
    """A deliberately strong zero-model-call baseline, also the SDK quick start."""
    ctx = Context.create(source)
    SupportSource.model_validate(source)
    state, amount = refund_facts(ctx)
    draft = {
        "order_id": source["order"]["id"],
        "paid_cents": source["order"]["paid_cents"],
        "order_status": source["order"]["status"],
        "refund_state": state,
        "refund_cents": amount,
        "next_step": NEXT_ACTION[state],
        "tone": tone,
    }
    draft["sections"] = expected_sections(draft)
    return draft


def make_support_contract(max_age_seconds: float = 300) -> Contract:
    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")

    def evidence(ctx: Context) -> None:
        parsed = SupportSource.model_validate(thaw(ctx.source))
        observed = datetime.fromisoformat(parsed.observed_at.replace("Z", "+00:00"))
        age = (ctx.now - observed).total_seconds()
        if age > max_age_seconds or age < -5:
            raise EvidenceUnavailable("Stale or future-dated evidence")

    def render(draft: dict[str, Any]) -> str:
        opening = "理解您希望尽快确认处理进度。" if draft["tone"] == "empathetic" else ""
        return opening + "".join(
            draft["sections"][key] for key in ("payment", "fulfillment", "refund", "next_step")
        )

    fields = [
        FactVerifier.from_path("fact.order_id", "/order_id", "/order/id"),
        FactVerifier.from_path("fact.paid_cents", "/paid_cents", "/order/paid_cents"),
        FactVerifier.from_path("fact.order_status", "/order_status", "/order/status"),
        FieldVerifier(
            "fact.refund_state",
            "/refund_state",
            lambda _draft, ctx: refund_facts(ctx)[0],
            ("/refund/requested_cents", "/refund/approved_cents", "/refund/receipt"),
        ),
        FieldVerifier(
            "fact.refund_cents",
            "/refund_cents",
            lambda _draft, ctx: refund_facts(ctx)[1],
            ("/refund/requested_cents", "/refund/approved_cents", "/refund/receipt"),
        ),
        FieldVerifier(
            "derived.next_step",
            "/next_step",
            lambda draft, _ctx: NEXT_ACTION[draft["refund_state"]],
            depends_on=("/refund_state",),
        ),
        FieldVerifier(
            "text.payment",
            "/sections/payment",
            lambda draft, _ctx: expected_sections(draft)["payment"],
            depends_on=("/order_id", "/paid_cents"),
        ),
        FieldVerifier(
            "text.fulfillment",
            "/sections/fulfillment",
            lambda draft, _ctx: FULFILLMENT[draft["order_status"]],
            depends_on=("/order_status",),
        ),
        FieldVerifier(
            "text.refund",
            "/sections/refund",
            lambda draft, _ctx: refund_sentence(draft),
            depends_on=("/refund_state", "/refund_cents"),
        ),
        FieldVerifier(
            "text.next_step",
            "/sections/next_step",
            lambda draft, _ctx: NEXT_TEXT[draft["next_step"]],
            depends_on=("/next_step",),
        ),
    ]
    rule = RuleVerifier(
        "rule.refund_amount_state",
        lambda draft, _ctx: (
            (draft["refund_state"] == "not_requested") == (draft["refund_cents"] is None)
        ),
        "/refund_cents",
        "A stated refund amount must agree with the request state",
    )
    instructions = (
        """Generate a Chinese after-sales response PLAN, not an action. Money is integer cents.
Copy order facts. Never use paid_cents as a refund amount. Refund state and amount:
receipt -> its status and amount; otherwise approved_cents -> approved; otherwise
requested_cents -> requested; otherwise not_requested and null. A receipt must
match the order and request. Do not infer到账 from approval or processing.
tone can be neutral or empathetic. next_step mapping: """
        + str(NEXT_ACTION)
        + """.
Use these exact controlled sentences in sections (money must have two decimals):
payment: 订单{order_id}实付{paid_cents/100}元。
fulfillment: """
        + str(FULFILLMENT)
        + """
refund: not_requested=当前没有退款申请。; requested=已申请退款{amount}元，等待审核。;
approved=退款{amount}元已审核通过，尚未到账。;
processing=退款{amount}元正在处理中，尚未确认到账。;
settled=本次退款{amount}元已到账。; failed=本次退款{amount}元处理失败，需人工核实。
next_step text: """
        + str(NEXT_TEXT)
        + """.
Do not add unverified free text or delivery promises. Return all schema fields."""
    )
    return Contract(SupportDraft, (*fields, rule), render, "support/0.1.0", instructions, evidence)


def demo_source() -> dict[str, Any]:
    return {
        "snapshot_id": "demo-v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "order": {
            "id": "ORDER-1001",
            "status": "shipped",
            "paid_cents": 79900,
            "currency": "CNY",
            "refunded_before_cents": 0,
        },
        "refund": {
            "request_id": None,
            "requested_cents": None,
            "approved_cents": None,
            "receipt": None,
        },
    }


def demo_bad_draft(source: dict[str, Any]) -> dict[str, Any]:
    draft = template_response(source, "empathetic")
    draft.update(
        paid_cents=89900,
        order_status="cancelled",
        refund_state="settled",
        refund_cents=89900,
        next_step="none",
    )
    draft["sections"] = expected_sections(draft)
    return draft
