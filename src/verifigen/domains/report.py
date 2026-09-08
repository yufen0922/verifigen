"""Second domain: checked data-to-text, sharing the identical repair runtime."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from ..contract import Contract
from ..jsonutil import thaw
from ..types import Context
from ..verifiers import FactVerifier, FieldVerifier
from .support import StrictModel

Count = Annotated[int, Field(ge=0)]


class ReportSource(StrictModel):
    current: Count
    previous: Count


class ReportDraft(StrictModel):
    current: Count
    previous: Count
    delta: int
    direction: Literal["up", "down", "flat"]
    sentence: str


def direction(draft: dict[str, Any]) -> str:
    return "up" if draft["delta"] > 0 else "down" if draft["delta"] < 0 else "flat"


def sentence(draft: dict[str, Any]) -> str:
    movement = {"up": "增加", "down": "减少", "flat": "持平，差额"}[draft["direction"]]
    return f"本期订单{draft['current']}笔，上期{draft['previous']}笔，{movement}{abs(draft['delta'])}笔。"


def make_report_contract() -> Contract:
    def evidence(ctx: Context) -> None:
        ReportSource.model_validate(thaw(ctx.source))

    return Contract(
        ReportDraft,
        (
            FactVerifier.from_path("fact.current", "/current", "/current"),
            FactVerifier.from_path("fact.previous", "/previous", "/previous"),
            FieldVerifier(
                "derived.delta",
                "/delta",
                lambda d, _c: d["current"] - d["previous"],
                depends_on=("/current", "/previous"),
            ),
            FieldVerifier(
                "derived.direction",
                "/direction",
                lambda d, _c: direction(d),
                depends_on=("/delta",),
            ),
            FieldVerifier(
                "text.sentence",
                "/sentence",
                lambda d, _c: sentence(d),
                depends_on=("/current", "/previous", "/delta", "/direction"),
            ),
        ),
        lambda d: d["sentence"],
        version="report/0.1.0",
        preflight=evidence,
        fallback_text="数据尚未核实，暂不生成结论。",
    )
