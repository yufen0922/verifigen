"""Natural-language RAG quality task for the LLM judge-and-repair loop."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..review import Criterion, QualityTask


class RagAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    citations: list[str] = Field(min_length=1)


RAG_CRITERIA = (
    Criterion(
        "grounding",
        "答案中的每一项政策事实都必须能由 retrieved_chunks 的原文直接支持，不得补充常识或臆测。",
    ),
    Criterion(
        "citation",
        "每项关键政策结论后应使用 [chunk_id] 标注依据；citations 只能包含实际检索到且确实支持结论的片段 ID。",
    ),
    Criterion(
        "completeness",
        "必须完整回答用户问题的各个部分；如果材料不足，应明确说无法从当前材料确认。",
    ),
    Criterion(
        "consistency",
        "答案、行内引用和 citations 列表之间不得相互矛盾，也不得混用其他商品类别的政策。",
    ),
    Criterion("relevance", "回答应直接、简洁，不输出与用户问题无关的内容。"),
)


def make_rag_task(source: dict[str, Any]) -> QualityTask:
    return QualityTask(
        source=source,
        prompt=(
            "根据 retrieved_chunks 回答 question。输出 JSON：answer 为自然语言回答，关键结论后使用 "
            "[chunk_id] 行内引用；citations 为用到的片段 ID 列表。"
        ),
        criteria=RAG_CRITERIA,
        output_schema=RagAnswer.model_json_schema(),
        instructions=(
            "检索片段可能不完整或互相冲突。不要把检索排名当作事实正确性的证明；只能依据片段原文回答。"
        ),
        fallback_text="当前检索材料不足以生成经过校验的政策答复，请转人工确认。",
    )


__all__ = ["RAG_CRITERIA", "RagAnswer", "make_rag_task"]
