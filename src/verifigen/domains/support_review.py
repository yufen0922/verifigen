"""Customer-support adapter for the generic Judge/Repair quality loop."""

from __future__ import annotations

from typing import Any  # noqa: TC003 - used by the runtime renderer annotation

from ..review import Criterion, QualityTask
from .support import FULFILLMENT, NEXT_ACTION, NEXT_TEXT, SupportDraft, SupportSource

SUPPORT_CRITERIA = (
    Criterion(
        "factual_grounding",
        "订单号、实付金额和履约状态必须与 source.order 完全一致，不得猜测未提供的状态。",
    ),
    Criterion(
        "refund_status",
        "退款状态和金额必须按证据优先级确定：回执、已批准金额、申请金额、无申请。不得把审核通过或处理中说成已到账。",
    ),
    Criterion(
        "next_action",
        "下一步只能根据当前退款状态给出等待审核、等待到账、提交申请、联系人工或无需操作。",
    ),
    Criterion(
        "consistency",
        "结构化字段与四段用户可见文本必须一致，金额使用人民币元并保留两位小数。",
    ),
    Criterion(
        "safety",
        "不得声称已经执行退款、承诺到账时限、赠送补偿，或泄露内部处理信息。",
    ),
)


def render_support(candidate: Any) -> str:
    parsed = SupportDraft.model_validate(candidate)
    opening = "理解您希望尽快确认处理进度。" if parsed.tone == "empathetic" else ""
    return opening + "".join(
        getattr(parsed.sections, key) for key in ("payment", "fulfillment", "refund", "next_step")
    )


def make_support_task(source: dict[str, Any]) -> QualityTask:
    SupportSource.model_validate(source)
    return QualityTask(
        source=source,
        prompt=(
            "根据订单快照生成中文售后回复计划。输出订单事实、退款状态、下一步动作、语气和四段回复文本；"
            "这是信息说明，不是退款执行指令。"
        ),
        criteria=SUPPORT_CRITERIA,
        output_schema=SupportDraft.model_json_schema(),
        instructions=(
            "金额字段使用人民币分。退款事实优先级为 receipt > approved_cents > requested_cents > "
            "not_requested。processing、approved 都不代表已经到账。"
            f"订单状态文本必须使用此映射：{FULFILLMENT}。"
            f"退款状态到 next_step 必须使用此映射：{NEXT_ACTION}。"
            f"next_step 文本必须使用此映射：{NEXT_TEXT}。"
            "not_requested 的退款文本为‘当前没有退款申请。’；requested、approved、processing、"
            "settled、failed 的文本必须分别准确表达等待审核、尚未到账、尚未确认到账、已到账和处理失败。"
            "只依据当前快照，不作到账时间、退款执行或补偿承诺。"
        ),
        fallback_text="当前订单或退款信息无法生成经过校验的答复，已转人工客服核实。",
        renderer=render_support,
    )


__all__ = ["SUPPORT_CRITERIA", "make_support_task", "render_support"]
