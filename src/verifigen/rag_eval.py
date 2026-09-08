"""Independent claim-level scoring for the RAG Judge/Repair evaluation set.

This module deliberately imports no runtime, model or domain code. It treats
each evaluation case's ``required_claims`` as the gold contract and checks a
final candidate with substring patterns and citation IDs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _answer(value: Any) -> str | None:
    if isinstance(value, Mapping) and isinstance(value.get("answer"), str):
        return value["answer"]
    return None


def _citations(value: Any) -> list[str] | None:
    if not isinstance(value, Mapping) or not isinstance(value.get("citations"), list):
        return None
    citations = value["citations"]
    if not all(isinstance(item, str) for item in citations):
        return None
    return citations


def _claim_ok(answer: str, claim: Mapping[str, Any]) -> bool:
    passes = claim.get("pass_terms")
    fails = claim.get("fail_terms")
    if not isinstance(passes, Sequence) or not isinstance(fails, Sequence):
        return False
    has_support = any(isinstance(term, str) and term in answer for term in passes)
    pass_all_terms = claim.get("pass_all_terms", [])
    if isinstance(pass_all_terms, Sequence):
        has_support = has_support or any(
            isinstance(group, Sequence)
            and not isinstance(group, (str, bytes))
            and bool(group)
            and all(isinstance(term, str) and term in answer for term in group)
            for group in pass_all_terms
        )
    has_conflict = any(isinstance(term, str) and term in answer for term in fails)
    return has_support and not has_conflict


def score_rag_output(output: Any, case: Mapping[str, Any]) -> bool:
    """Return True only when every required claim and citation boundary is met."""
    answer = _answer(output)
    citations = _citations(output)
    if answer is None or citations is None:
        return False

    required = case.get("required_claims")
    if required is None:
        # Legacy smoke-set shape used by the original six hand-written cases.
        legacy_terms = case.get("required_terms")
        if not isinstance(legacy_terms, list):
            return False
        required_chunk_ids = case.get("required_citations")
        has_legacy_chunks = isinstance(required_chunk_ids, list) and set(
            required_chunk_ids
        ).issubset(citations)
        forbidden = case.get("forbidden_terms")
        forbidden_ok = not isinstance(forbidden, list) or not any(
            isinstance(item, str) and item in answer for item in forbidden
        )
        return (
            has_legacy_chunks
            and forbidden_ok
            and all(isinstance(item, str) and item in answer for item in legacy_terms)
        )
    if not isinstance(required, list):
        return False

    required_chunk_ids = [
        claim.get("chunk_id") for claim in required if isinstance(claim.get("chunk_id"), str)
    ]
    if not required_chunk_ids or not set(required_chunk_ids).issubset(citations):
        return False

    forbidden_chunks = case.get("forbidden_chunks")
    if isinstance(forbidden_chunks, list) and any(
        isinstance(item, str) and item in citations or isinstance(item, str) and item in answer
        for item in forbidden_chunks
    ):
        return False

    forbidden_phrases = case.get("forbidden_phrases")
    if isinstance(forbidden_phrases, list) and any(
        isinstance(item, str) and item in answer for item in forbidden_phrases
    ):
        return False

    return all(_claim_ok(answer, claim) for claim in required)


def evaluate_case(output: Any, case: Mapping[str, Any], *, initial: Any = None) -> dict[str, Any]:
    """Return one labeled evaluation row with independent and judge-gold flags."""
    expected_pass = bool(case.get("initial_should_pass"))
    return {
        "id": case.get("id"),
        "category": case.get("category"),
        "gold_initial_pass": expected_pass,
        "judge_initial_correct": expected_pass == (initial is not None and initial is output),
        "oracle_final_correct": score_rag_output(output, case),
        "status": (output or {}).get("status") if isinstance(output, Mapping) else None,
        "reason": (output or {}).get("reason") if isinstance(output, Mapping) else None,
    }


__all__ = ["evaluate_case", "score_rag_output"]
