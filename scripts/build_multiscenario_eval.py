"""Build 120 deterministic customer-support and data-to-text evaluation cases."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SUPPORT_OUTPUT = ROOT / "examples" / "customer_support" / "eval_cases.jsonl"
REPORT_OUTPUT = ROOT / "examples" / "data_to_text" / "eval_cases.jsonl"

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
SUPPORT_MUTATIONS = (
    "clean",
    "wrong_order_id",
    "wrong_paid_amount",
    "wrong_order_status",
    "wrong_refund_state",
    "wrong_refund_amount",
    "wrong_next_step",
    "stale_sections",
    "unsupported_promise",
    "missing_section",
)
REPORT_MUTATIONS = (
    "clean",
    "wrong_current",
    "wrong_previous",
    "wrong_delta",
    "wrong_direction",
    "wrong_rate",
    "wrong_unit",
    "stale_sentence",
    "unsupported_cause",
    "missing_sentence",
)


def money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def support_expected(source: dict[str, Any]) -> dict[str, Any]:
    refund = source["refund"]
    receipt = refund["receipt"]
    if receipt is not None:
        state, amount = receipt["status"], receipt["amount_cents"]
    elif refund["approved_cents"] is not None:
        state, amount = "approved", refund["approved_cents"]
    elif refund["requested_cents"] is not None:
        state, amount = "requested", refund["requested_cents"]
    else:
        state, amount = "not_requested", None
    if state == "not_requested":
        refund_text = "当前没有退款申请。"
    else:
        amount_text = money(amount)
        refund_text = {
            "requested": f"已申请退款{amount_text}元，等待审核。",
            "approved": f"退款{amount_text}元已审核通过，尚未到账。",
            "processing": f"退款{amount_text}元正在处理中，尚未确认到账。",
            "settled": f"本次退款{amount_text}元已到账。",
            "failed": f"本次退款{amount_text}元处理失败，需人工核实。",
        }[state]
    order = source["order"]
    next_step = NEXT_ACTION[state]
    return {
        "order_id": order["id"],
        "paid_cents": order["paid_cents"],
        "order_status": order["status"],
        "refund_state": state,
        "refund_cents": amount,
        "next_step": next_step,
        "tone": "empathetic",
        "sections": {
            "payment": f"订单{order['id']}实付{money(order['paid_cents'])}元。",
            "fulfillment": FULFILLMENT[order["status"]],
            "refund": refund_text,
            "next_step": NEXT_TEXT[next_step],
        },
    }


def support_sources() -> list[tuple[str, dict[str, Any]]]:
    specs = (
        ("not_requested", "paid", 25900, None, None, None),
        ("requested", "shipped", 79900, 12000, None, None),
        ("approved", "delivered", 129900, 18000, 15000, None),
        ("processing", "cancelled", 45900, 22000, 20000, "processing"),
        ("settled", "delivered", 219900, 34000, 30000, "settled"),
        ("failed", "shipped", 99900, 8000, 8000, "failed"),
    )
    rows = []
    for index, (name, status, paid, requested, approved, receipt_status) in enumerate(specs, 1):
        request_id = None if requested is None else f"REQ-{index:04d}"
        receipt = None
        if receipt_status is not None:
            receipt = {
                "order_id": f"ORDER-{index:04d}",
                "request_id": request_id,
                "status": receipt_status,
                "amount_cents": approved,
                "currency": "CNY",
            }
        rows.append(
            (
                name,
                {
                    "snapshot_id": f"SNAPSHOT-{index:04d}",
                    "observed_at": f"2026-08-{index + 10:02d}T09:30:00+08:00",
                    "order": {
                        "id": f"ORDER-{index:04d}",
                        "status": status,
                        "paid_cents": paid,
                        "currency": "CNY",
                        "refunded_before_cents": 0,
                    },
                    "refund": {
                        "request_id": request_id,
                        "requested_cents": requested,
                        "approved_cents": approved,
                        "receipt": receipt,
                    },
                },
            )
        )
    return rows


def mutate_support(expected: dict[str, Any], mutation: str) -> dict[str, Any]:
    draft = copy.deepcopy(expected)
    if mutation == "clean":
        return draft
    if mutation == "wrong_order_id":
        draft["order_id"] = "ORDER-9999"
    elif mutation == "wrong_paid_amount":
        draft["paid_cents"] += 10000
    elif mutation == "wrong_order_status":
        draft["order_status"] = "cancelled" if draft["order_status"] != "cancelled" else "paid"
    elif mutation == "wrong_refund_state":
        draft["refund_state"] = "settled" if draft["refund_state"] != "settled" else "requested"
    elif mutation == "wrong_refund_amount":
        draft["refund_cents"] = (
            9900 if draft["refund_cents"] is None else draft["refund_cents"] + 9900
        )
    elif mutation == "wrong_next_step":
        draft["next_step"] = "none" if draft["next_step"] != "none" else "await_review"
    elif mutation == "stale_sections":
        draft["sections"]["payment"] = "订单ORDER-OLD实付1.00元。"
        draft["sections"]["refund"] = "本次退款1.00元已到账。"
    elif mutation == "unsupported_promise":
        draft["sections"]["next_step"] += "我们已经为您退款，保证24小时内到账并赠送优惠券。"
    elif mutation == "missing_section":
        del draft["sections"]["next_step"]
    else:
        raise ValueError(f"unknown support mutation: {mutation}")
    return draft


def build_support_cases() -> list[dict[str, Any]]:
    cases = []
    forbidden = ["已经为您退款", "保证24小时内到账", "赠送优惠券"]
    for scenario, source in support_sources():
        expected = support_expected(source)
        for mutation in SUPPORT_MUTATIONS:
            cases.append(
                {
                    "id": f"support--{scenario}--{mutation}",
                    "category": "customer_support",
                    "scenario": scenario,
                    "source": source,
                    "initial": mutate_support(expected, mutation),
                    "expected": expected,
                    "initial_should_pass": mutation == "clean",
                    "forbidden_phrases": forbidden,
                }
            )
    return cases


REPORT_SOURCES = (
    ("orders_up", "支付订单", 1280, 1000, "笔", "本周", "上周"),
    ("refunds_down", "退款申请", 72, 96, "件", "本月", "上月"),
    ("users_flat", "活跃用户", 52000, 52000, "人", "今日", "昨日"),
    ("revenue_up", "成交金额", 985000, 910000, "元", "本季度", "上季度"),
    ("late_zero", "超时配送", 0, 18, "单", "本周", "上周"),
    ("new_from_zero", "新增投诉", 13, 0, "件", "本月", "上月"),
)


def report_expected(source: dict[str, Any]) -> dict[str, Any]:
    delta = source["current"] - source["previous"]
    direction = "up" if delta > 0 else "down" if delta < 0 else "flat"
    rate = None if source["previous"] == 0 else round(delta / source["previous"] * 100, 2)
    base = (
        f"{source['current_period']}{source['metric_name']}{source['current']}{source['unit']}，"
        f"{source['previous_period']}{source['previous']}{source['unit']}"
    )
    if source["previous"] == 0:
        sentence = f"{base}，增加{abs(delta)}{source['unit']}；由于上期为0，环比无法计算。"
    elif direction == "flat":
        sentence = f"{base}，持平，环比0.00%。"
    else:
        movement = "增加" if direction == "up" else "减少"
        trend = "上升" if direction == "up" else "下降"
        sentence = f"{base}，{movement}{abs(delta)}{source['unit']}，环比{trend}{abs(rate):.2f}%。"
    return {
        "metric_name": source["metric_name"],
        "current": source["current"],
        "previous": source["previous"],
        "delta": delta,
        "direction": direction,
        "change_rate_percent": rate,
        "sentence": sentence,
    }


def mutate_report(
    expected: dict[str, Any], source: dict[str, Any], mutation: str
) -> dict[str, Any]:
    draft = copy.deepcopy(expected)
    if mutation == "clean":
        return draft
    if mutation == "wrong_current":
        draft["current"] += 17
    elif mutation == "wrong_previous":
        draft["previous"] += 11
    elif mutation == "wrong_delta":
        draft["delta"] = draft["delta"] + 10 if draft["delta"] >= 0 else draft["delta"] - 10
    elif mutation == "wrong_direction":
        draft["direction"] = "down" if draft["direction"] != "down" else "up"
    elif mutation == "wrong_rate":
        draft["change_rate_percent"] = (
            100.0
            if draft["change_rate_percent"] is None
            else round(draft["change_rate_percent"] + 8.5, 2)
        )
    elif mutation == "wrong_unit":
        draft["sentence"] = draft["sentence"].replace(source["unit"], "万元")
    elif mutation == "stale_sentence":
        draft["sentence"] = "本期支付订单80笔，上期100笔，减少20笔，环比下降20.00%。"
    elif mutation == "unsupported_cause":
        draft["sentence"] += "变化主要由营销活动和市场需求导致，预计下期继续增长。"
    elif mutation == "missing_sentence":
        del draft["sentence"]
    else:
        raise ValueError(f"unknown report mutation: {mutation}")
    return draft


def build_report_cases() -> list[dict[str, Any]]:
    cases = []
    forbidden = ["营销活动", "市场需求导致", "预计下期"]
    for (
        scenario,
        metric,
        current,
        previous,
        unit,
        current_period,
        previous_period,
    ) in REPORT_SOURCES:
        source = {
            "metric_name": metric,
            "current": current,
            "previous": previous,
            "unit": unit,
            "current_period": current_period,
            "previous_period": previous_period,
        }
        expected = report_expected(source)
        for mutation in REPORT_MUTATIONS:
            cases.append(
                {
                    "id": f"report--{scenario}--{mutation}",
                    "category": "data_to_text",
                    "scenario": scenario,
                    "source": source,
                    "initial": mutate_report(expected, source, mutation),
                    "expected": expected,
                    "initial_should_pass": mutation == "clean",
                    "forbidden_phrases": forbidden,
                }
            )
    return cases


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build multi-scenario evaluation fixtures")
    parser.add_argument("--support-output", type=Path, default=SUPPORT_OUTPUT)
    parser.add_argument("--report-output", type=Path, default=REPORT_OUTPUT)
    args = parser.parse_args()
    support_cases = build_support_cases()
    report_cases = build_report_cases()
    write_jsonl(args.support_output.resolve(), support_cases)
    write_jsonl(args.report_output.resolve(), report_cases)
    print(f"wrote {len(support_cases)} support and {len(report_cases)} report cases")


if __name__ == "__main__":
    main()
