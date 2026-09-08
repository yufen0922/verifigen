"""Data-to-text adapter for the generic Judge/Repair quality loop."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..review import Criterion, QualityTask


class MetricSource(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    metric_name: str = Field(min_length=1, max_length=64)
    current: int
    previous: int
    unit: str = Field(min_length=1, max_length=16)
    current_period: str = Field(min_length=1, max_length=32)
    previous_period: str = Field(min_length=1, max_length=32)


class MetricReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    metric_name: str = Field(min_length=1, max_length=64)
    current: int
    previous: int
    delta: int
    direction: Literal["up", "down", "flat"]
    change_rate_percent: float | None
    sentence: str = Field(min_length=1)


REPORT_CRITERIA = (
    Criterion(
        "numeric_fidelity",
        "指标名称、本期值和上期值必须逐字逐数来自 source，不得改写数值。",
    ),
    Criterion(
        "derivation",
        "delta 必须等于 current-previous；方向必须与 delta 符号一致；环比数值为 delta/previous*100 并按两位小数精度取值。JSON 数字 28.0 与 28.00 等价，但 sentence 中的百分比必须显示两位。上期为 0 时环比必须为 null。",
    ),
    Criterion(
        "unit_fidelity",
        "自然语言中的指标名称、期间和单位必须与 source 一致，不能混用元、笔、人、件等单位。",
    ),
    Criterion(
        "consistency",
        "sentence 必须与结构化字段中的本期值、上期值、差值、方向和环比完全一致。",
    ),
    Criterion(
        "restraint",
        "只能描述数据变化，不得凭空解释原因、预测趋势或给出业务归因。",
    ),
)


def expected_report(source: dict[str, Any]) -> dict[str, Any]:
    parsed = MetricSource.model_validate(source)
    delta = parsed.current - parsed.previous
    direction: Literal["up", "down", "flat"] = (
        "up" if delta > 0 else "down" if delta < 0 else "flat"
    )
    rate = None if parsed.previous == 0 else round(delta / parsed.previous * 100, 2)
    base = (
        f"{parsed.current_period}{parsed.metric_name}{parsed.current}{parsed.unit}，"
        f"{parsed.previous_period}{parsed.previous}{parsed.unit}"
    )
    if parsed.previous == 0:
        sentence = f"{base}，增加{abs(delta)}{parsed.unit}；由于上期为0，环比无法计算。"
    elif direction == "flat":
        sentence = f"{base}，持平，环比0.00%。"
    else:
        movement = "增加" if direction == "up" else "减少"
        trend = "上升" if direction == "up" else "下降"
        sentence = (
            f"{base}，{movement}{abs(delta)}{parsed.unit}，环比{trend}{abs(rate or 0):.2f}%。"
        )
    return {
        "metric_name": parsed.metric_name,
        "current": parsed.current,
        "previous": parsed.previous,
        "delta": delta,
        "direction": direction,
        "change_rate_percent": rate,
        "sentence": sentence,
    }


def render_report(candidate: Any) -> str:
    return MetricReport.model_validate(candidate).sentence


def make_report_task(source: dict[str, Any]) -> QualityTask:
    MetricSource.model_validate(source)
    return QualityTask(
        source=source,
        prompt="根据指标快照生成一条准确、克制的中文变化摘要，并返回结构化计算结果。",
        criteria=REPORT_CRITERIA,
        output_schema=MetricReport.model_json_schema(),
        instructions=(
            "只使用 source 中的数据。delta=current-previous；change_rate_percent="
            "delta/previous*100 并按两位小数精度取值；JSON 数字不要求保留末尾的 0，但 sentence 中"
            "百分比必须显示两位。previous 为 0 时写 null。不得推测变化原因。"
        ),
        fallback_text="数据尚未通过一致性校验，暂不发布指标结论。",
        renderer=render_report,
    )


__all__ = [
    "MetricReport",
    "MetricSource",
    "REPORT_CRITERIA",
    "expected_report",
    "make_report_task",
    "render_report",
]
