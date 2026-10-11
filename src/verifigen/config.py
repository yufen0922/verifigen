"""Explicit local configuration shared by live examples and the workbench."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from .agents import Qwen3Stack, make_qwen3_8b_stack


@dataclass(frozen=True)
class ModelSettings:
    api_key: str = field(repr=False)
    model: str = "qwen3.5-flash"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> ModelSettings:
        if env_file is not None:
            load_dotenv(env_file, override=False)
        return cls(
            api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
            model=os.environ.get("DASHSCOPE_MODEL", "qwen3.5-flash"),
            base_url=os.environ.get(
                "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
            ),
        )

    def stack(
        self,
        *,
        thinking_budget: int = 1024,
        enable_thinking: bool = False,
        validate_judge_quotes: bool = False,
        judge_model: str | None = None,
    ) -> Qwen3Stack:
        if not self.api_key:
            raise ValueError("Set DASHSCOPE_API_KEY or configure the ignored .env.local file")
        return make_qwen3_8b_stack(
            api_key=self.api_key,
            model=self.model,
            base_url=self.base_url,
            thinking_budget=thinking_budget,
            enable_thinking=enable_thinking,
            validate_judge_quotes=validate_judge_quotes,
            judge_model=judge_model,
        )
