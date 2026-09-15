"""Pure output decisions, independent of model I/O and business scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .review import JudgeVerdict


@dataclass(frozen=True)
class LoopDecision:
    action: Literal["publish", "repair", "fallback"]
    reason: str


@dataclass(frozen=True)
class QualityPolicy:
    """An optional score plateau stop, in addition to mandatory release gates.

    Scores are model estimates, not calibrated probabilities. Plateau detection
    is disabled by default; enable it only after evaluating the chosen judge.
    """

    score_patience: int | None = None
    min_score_gain: float = 0.01

    def __post_init__(self) -> None:
        if self.score_patience is not None and (
            type(self.score_patience) is not int or self.score_patience < 1
        ):
            raise ValueError("score_patience must be a positive integer")
        if not 0 < self.min_score_gain <= 1:
            raise ValueError("min_score_gain must be in (0, 1]")

    def decide(
        self,
        verdict: JudgeVerdict,
        *,
        min_pass_score: float,
        repair_rounds: int,
        max_repair_rounds: int,
        history: tuple[JudgeVerdict, ...] = (),
    ) -> LoopDecision:
        """History contains earlier verdicts, excluding the current verdict."""
        if verdict.status == "unknown":
            return LoopDecision("fallback", "judge_unknown")
        if verdict.status == "pass":
            if verdict.score < min_pass_score:
                return LoopDecision("fallback", "score_below_threshold")
            return LoopDecision("publish", "judge_passed")
        if repair_rounds >= max_repair_rounds:
            return LoopDecision("fallback", "repair_budget")
        if self.score_patience is not None and len(history) >= self.score_patience:
            scores = [item.score for item in history] + [verdict.score]
            baseline = max(scores[: -self.score_patience])
            recent_best = max(scores[-self.score_patience :])
            if recent_best - baseline < self.min_score_gain:
                return LoopDecision("fallback", "score_plateau")
        return LoopDecision("repair", "issues_found")


__all__ = ["LoopDecision", "QualityPolicy"]
