"""Rebuild synthetic fixtures from independent scenario annotations.

No imports from verifigen are allowed here. State labels below are assigned by
the scenario author; they are not inferred by the production refund resolver.
Review the resulting JSONL before using this corpus for claims about quality.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIME = "2026-09-07T12:00:00+00:00"
STATES = {
    "not_requested": ("submit_request", "如需售后，可提交申请，由平台审核。"),
    "requested": ("await_review", "请等待平台审核退款申请。"),
    "approved": ("await_payout", "请关注后续退款状态，以实际到账结果为准。"),
    "processing": ("await_payout", "请关注后续退款状态，以实际到账结果为准。"),
    "settled": ("none", "可核对原支付渠道的到账记录。"),
    "failed": ("contact_support", "请联系人工客服核实退款失败原因。"),
}
ORDER_TEXT = {
    "paid": "订单已支付，尚未发货。",
    "shipped": "订单已经发货。",
    "delivered": "订单已签收。",
    "cancelled": "订单已取消。",
}


def amount(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def annotated_sections(draft):
    state, value = draft["refund_state"], draft["refund_cents"]
    rendered = "待核实" if value is None else amount(value)
    refund_text = {
        "not_requested": "当前没有退款申请。",
        "requested": f"已申请退款{rendered}元，等待审核。",
        "approved": f"退款{rendered}元已审核通过，尚未到账。",
        "processing": f"退款{rendered}元正在处理中，尚未确认到账。",
        "settled": f"本次退款{rendered}元已到账。",
        "failed": f"本次退款{rendered}元处理失败，需人工核实。",
    }[state]
    next_text = {step: text for step, text in STATES.values()}[draft["next_step"]]
    return {
        "payment": f"订单{draft['order_id']}实付{amount(draft['paid_cents'])}元。",
        "fulfillment": ORDER_TEXT[draft["order_status"]],
        "refund": refund_text,
        "next_step": next_text,
    }


# family, split, order status, paid, previous refunds, request, approval, receipt, gold state, gold amount
SCENARIOS = [
    ("no_request", "dev", "shipped", 79900, 0, None, None, None, "not_requested", None),
    ("await_review", "dev", "delivered", 49900, 0, 19900, None, None, "requested", 19900),
    ("approval_only", "dev", "paid", 80000, 0, 40000, 30000, None, "approved", 30000),
    ("processing", "dev", "shipped", 129900, 0, 29900, 29900, "processing", "processing", 29900),
    ("settlement", "dev", "delivered", 39900, 0, 39900, 39900, "settled", "settled", 39900),
    ("payment_failure", "dev", "cancelled", 19900, 0, 19900, 19900, "failed", "failed", 19900),
    (
        "partial_after_prior",
        "test",
        "delivered",
        99900,
        20000,
        30000,
        25000,
        "settled",
        "settled",
        25000,
    ),
    (
        "fractional_cent_amount",
        "test",
        "shipped",
        79999,
        0,
        12345,
        12345,
        "processing",
        "processing",
        12345,
    ),
    ("cancelled_no_request", "test", "cancelled", 9900, 0, None, None, None, "not_requested", None),
    ("one_cent_approval", "test", "paid", 100, 0, 1, 1, None, "approved", 1),
    (
        "remaining_balance_request",
        "test",
        "delivered",
        50000,
        40000,
        10000,
        None,
        None,
        "requested",
        10000,
    ),
    ("partial_failure", "test", "delivered", 70000, 10000, 20000, 15000, "failed", "failed", 15000),
]


def scenario(spec, index):
    (
        family,
        split,
        order_status,
        paid,
        prior,
        requested,
        approved,
        receipt_status,
        state,
        refund_amount,
    ) = spec
    order_id, request_id = (
        f"ORDER-{index + 1000}",
        None if requested is None else f"REQ-{index + 2000}",
    )
    receipt = (
        None
        if receipt_status is None
        else {
            "order_id": order_id,
            "request_id": request_id,
            "status": receipt_status,
            "amount_cents": approved,
            "currency": "CNY",
        }
    )
    source = {
        "snapshot_id": "snapshot-" + family,
        "observed_at": TIME,
        "order": {
            "id": order_id,
            "status": order_status,
            "paid_cents": paid,
            "currency": "CNY",
            "refunded_before_cents": prior,
        },
        "refund": {
            "request_id": request_id,
            "requested_cents": requested,
            "approved_cents": approved,
            "receipt": receipt,
        },
    }
    gold = {
        "order_id": order_id,
        "paid_cents": paid,
        "order_status": order_status,
        "refund_state": state,
        "refund_cents": refund_amount,
        "next_step": STATES[state][0],
        "tone": "neutral",
    }
    gold["sections"] = annotated_sections(gold)
    return family, split, source, gold


def variants(gold):
    for mutation in (
        "clean",
        "paid_coherent",
        "status_coherent",
        "false_commitment",
        "amount_from_paid",
        "text_only",
        "entity_swap",
        "multi_error",
        "schema_missing",
    ):
        draft = copy.deepcopy(gold)
        draft["tone"] = "empathetic"
        if mutation in ("paid_coherent", "multi_error"):
            draft["paid_cents"] += 10000
        if mutation in ("status_coherent", "multi_error"):
            draft["order_status"] = (
                "cancelled" if gold["order_status"] != "cancelled" else "shipped"
            )
        if mutation in ("false_commitment", "multi_error"):
            draft["refund_state"] = (
                "settled" if gold["refund_state"] != "settled" else "not_requested"
            )
            draft["refund_cents"] = (
                draft["paid_cents"] if draft["refund_state"] == "settled" else None
            )
            draft["next_step"] = STATES[draft["refund_state"]][0]
        if mutation == "amount_from_paid":
            draft["refund_cents"] = (
                gold["paid_cents"]
                if gold["paid_cents"] != gold["refund_cents"]
                else gold["paid_cents"] + 100
            )
        if mutation == "entity_swap":
            draft["order_id"] = "WRONG-ORDER"
        draft["sections"] = annotated_sections(draft)
        if mutation == "text_only":
            draft["sections"]["refund"] += "我们保证今天到账，并额外赠送优惠券。"
        if mutation == "schema_missing":
            del draft["paid_cents"]
        yield mutation, draft


def main():
    splits = {"dev": [], "test": []}
    originals = []
    for index, spec in enumerate(SCENARIOS):
        family, split, source, gold = scenario(spec, index)
        originals.append((source, gold))
        for mutation, draft in variants(gold):
            splits[split].append(
                {
                    "id": family + "--" + mutation,
                    "family": family,
                    "mutation": mutation,
                    "evaluation_time": TIME,
                    "source": source,
                    "candidate": draft,
                    "gold": gold,
                }
            )
    for kind in (
        "stale",
        "future",
        "wrong_order_receipt",
        "wrong_request_receipt",
        "over_remaining",
        "missing_evidence",
    ):
        source, candidate = copy.deepcopy(originals[4])
        if kind == "stale":
            source["observed_at"] = "2026-09-06T12:00:00+00:00"
        elif kind == "future":
            source["observed_at"] = "2026-09-08T12:00:00+00:00"
        elif kind == "wrong_order_receipt":
            source["refund"]["receipt"]["order_id"] = "OTHER-ORDER"
        elif kind == "wrong_request_receipt":
            source["refund"]["receipt"]["request_id"] = "OTHER-REQUEST"
        elif kind == "over_remaining":
            source["order"]["refunded_before_cents"] = 100
        elif kind == "missing_evidence":
            del source["refund"]["receipt"]
        splits["test"].append(
            {
                "id": "invalid--" + kind,
                "family": "invalid_" + kind,
                "mutation": kind,
                "evaluation_time": TIME,
                "source": source,
                "candidate": candidate,
                "gold": None,
            }
        )
    folder = ROOT / "benchmarks" / "data"
    folder.mkdir(parents=True, exist_ok=True)
    for split, cases in splits.items():
        (folder / f"{split}.jsonl").write_text(
            "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases), encoding="utf-8"
        )
    print({split: len(cases) for split, cases in splits.items()})


if __name__ == "__main__":
    main()
