"""Two-reviewer agreement and explicit adjudication for anonymous output packets."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .comparison import OutputReview
from .jsonutil import digest


class HumanAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str = Field(min_length=1)
    packet_sha256: str = Field(min_length=64, max_length=64)
    reviewer_id: str = Field(min_length=1, max_length=100)
    review: OutputReview


def annotation_template(
    packets: Sequence[dict[str, Any]], reviewer_id: str
) -> list[dict[str, Any]]:
    if not reviewer_id.strip():
        raise ValueError("Use a non-empty anonymous reviewer handle")
    return [
        {
            "review_id": p["review_id"],
            "packet_sha256": digest(p),
            "reviewer_id": reviewer_id,
            "review": None,
        }
        for p in packets
    ]


def reconcile(
    packets: Sequence[dict[str, Any]],
    annotations: Sequence[dict[str, Any]],
    adjudications: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    indexed = {p["review_id"]: p for p in packets}
    if len(indexed) != len(packets):
        raise ValueError("Duplicate packets")
    groups: dict[str, dict[str, HumanAnnotation]] = {key: {} for key in indexed}

    def validate(row: dict[str, Any]) -> HumanAnnotation:
        annotation = HumanAnnotation.model_validate(row)
        packet = indexed.get(annotation.review_id)
        if packet is None or digest(packet) != annotation.packet_sha256:
            raise ValueError("Annotation references unknown or modified evidence/candidate")
        return annotation

    for row in annotations:
        annotation = validate(row)
        group = groups[annotation.review_id]
        if annotation.reviewer_id in group:
            raise ValueError("A reviewer cannot vote twice on one packet")
        group[annotation.reviewer_id] = annotation
    arbitrated: dict[str, HumanAnnotation] = {}
    for row in adjudications:
        annotation = validate(row)
        if annotation.review_id in arbitrated:
            raise ValueError("Duplicate adjudication")
        if annotation.reviewer_id in groups[annotation.review_id]:
            raise ValueError("Adjudicator must differ from the original reviewers")
        arbitrated[annotation.review_id] = annotation
    results: list[dict[str, Any]] = []
    agreements = eligible = conflicts = pending = 0
    for identifier, group in groups.items():
        votes = list(group.values())
        if len(votes) < 2:
            if identifier in arbitrated:
                raise ValueError("Adjudication cannot replace missing independent reviews")
            pending += 1
            results.append({"review_id": identifier, "status": "pending", "review": None})
            continue
        eligible += 1
        dimensions = {(v.review.grounding, v.review.fulfillment) for v in votes}
        status, resolved = "agreed", votes[0].review
        if len(dimensions) == 1:
            agreements += 1
            if identifier in arbitrated:
                raise ValueError("Adjudication supplied for an agreed packet")
        else:
            conflicts += 1
            if identifier not in arbitrated:
                results.append({"review_id": identifier, "status": "disagreement", "review": None})
                continue
            status, resolved = "adjudicated", arbitrated[identifier].review
        results.append({"review_id": identifier, "status": status, "review": resolved.model_dump()})
    return {
        "label_kind": "human_dual_review_with_explicit_adjudication",
        "packets": len(packets),
        "dual_reviewed": eligible,
        "pending": pending,
        "initial_disagreements": conflicts,
        "dimension_agreement": agreements / eligible if eligible else None,
        "unresolved_disagreements": sum(r["status"] == "disagreement" for r in results),
        "resolved": sum(r["status"] in ("agreed", "adjudicated") for r in results),
        "results": results,
    }


def score_outputs(
    records: Sequence[dict[str, Any]],
    mapping: Sequence[dict[str, Any]],
    reconciliation: dict[str, Any],
    samples: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Publish human effect rates only after all released outputs are resolved."""
    links = {(r["id"], r["arm"]): r["review_id"] for r in mapping}
    labels = {r["review_id"]: r for r in reconciliation["results"]}
    original = {s["id"]: s for s in samples}
    if len(links) != len(mapping) or len(labels) != len(reconciliation["results"]):
        raise ValueError("Duplicate scoring mappings or labels")
    results = {}
    arms = {r.get("arm", "quality_loop") for r in records}
    for arm in sorted(arms):
        rows = [r for r in records if r.get("arm", "quality_loop") == arm]
        if len({r["id"] for r in rows}) != len(rows):
            raise ValueError("Duplicate output records")
        released = [r for r in rows if r["status"] == "passed" and r["output"] is not None]
        resolved = usable = rescued = wrong = 0
        for row in released:
            expected_id = digest({"sample": row["id"], "candidate": row["output"]})
            if links.get((row["id"], arm)) != expected_id:
                raise ValueError("Output/mapping differs from the blind packet candidate")
            label = labels.get(links.get((row["id"], arm), ""), {})
            if label.get("status") not in ("agreed", "adjudicated"):
                continue
            verdict = label["review"]
            if "unknown" in (verdict["grounding"], verdict["fulfillment"]):
                continue
            resolved += 1
            wrong += verdict["grounding"] == "fail"
            good = verdict["grounding"] == verdict["fulfillment"] == "pass"
            usable += good
            sample = original[row["id"]]
            changed = row["output"] != {"answer": sample["response"]}
            rescued += good and changed and sample["has_hallucination"]
        complete = resolved == len(released)
        bad_count = sum(original[r["id"]]["has_hallucination"] for r in rows)
        results[arm] = {
            "cases": len(rows),
            "released": len(released),
            "resolved_known_labels": resolved,
            "review_coverage": resolved / len(released) if released else 1.0,
            "usable_resolved_count": usable,
            "wrong_resolved_count": wrong,
            "effect_rates_ready": complete,
            "human_usable_yield": usable / len(rows) if complete else None,
            "human_wrong_release_rate": wrong / len(released) if complete and released else None,
            "human_bad_initial_rescue_rate": rescued / bad_count
            if complete and bad_count
            else None,
        }
    return {"label_kind": reconciliation["label_kind"], "arms": results}
