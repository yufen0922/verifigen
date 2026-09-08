"""VerifiGen: an LLM judge-and-repair quality loop."""

from .agents import (
    AgentResponseError,
    FunctionJudge,
    FunctionRepairer,
    LLMJudge,
    LLMRepairer,
    Qwen3Stack,
    ReplayJudge,
    ReplayRepairer,
    make_qwen3_8b_stack,
)
from .contract import Contract
from .generators import CompatibleChatGenerator, FunctionGenerator, ReplayGenerator
from .quality import QualityLoop, write_quality_trace
from .review import (
    Criterion,
    JudgeIssue,
    JudgeVerdict,
    QualityBudget,
    QualityResult,
    QualityTask,
)
from .runtime import Harness, write_trace
from .types import Budget, CheckResult, Context, RunResult, VerificationReport, Violation
from .verifiers import EvidenceUnavailable, FactVerifier, FieldVerifier, RuleVerifier, Verifier

__version__ = "0.2.0"
__all__ = [
    "AgentResponseError",
    "Budget",
    "CheckResult",
    "CompatibleChatGenerator",
    "Context",
    "Contract",
    "Criterion",
    "EvidenceUnavailable",
    "FactVerifier",
    "FieldVerifier",
    "FunctionJudge",
    "FunctionRepairer",
    "FunctionGenerator",
    "Harness",
    "JudgeIssue",
    "JudgeVerdict",
    "LLMJudge",
    "LLMRepairer",
    "QualityBudget",
    "QualityLoop",
    "QualityResult",
    "QualityTask",
    "Qwen3Stack",
    "ReplayGenerator",
    "ReplayJudge",
    "ReplayRepairer",
    "RuleVerifier",
    "RunResult",
    "VerificationReport",
    "Verifier",
    "Violation",
    "make_qwen3_8b_stack",
    "write_quality_trace",
    "write_trace",
]
