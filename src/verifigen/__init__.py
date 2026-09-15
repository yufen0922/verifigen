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
from .gates import CandidateGate, SchemaGate
from .generators import CompatibleChatGenerator, FunctionGenerator, ReplayGenerator
from .policy import LoopDecision, QualityPolicy
from .quality import QualityLoop, write_quality_trace
from .review import (
    Criterion,
    GateReport,
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
    "CandidateGate",
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
    "GateReport",
    "Harness",
    "JudgeIssue",
    "JudgeVerdict",
    "LLMJudge",
    "LLMRepairer",
    "LoopDecision",
    "QualityBudget",
    "QualityLoop",
    "QualityPolicy",
    "QualityResult",
    "QualityTask",
    "Qwen3Stack",
    "ReplayGenerator",
    "ReplayJudge",
    "ReplayRepairer",
    "RuleVerifier",
    "RunResult",
    "SchemaGate",
    "VerificationReport",
    "Verifier",
    "Violation",
    "make_qwen3_8b_stack",
    "write_quality_trace",
    "write_trace",
]
