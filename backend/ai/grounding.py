from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import BaseModel

from backend.ai.contracts import ValidationCode
from backend.ai.retrieval import EvidenceDocument, tokenize


@dataclass(frozen=True, slots=True)
class GroundingIssue:
    code: ValidationCode
    message: str


def validate_grounding(
    payload: BaseModel | dict[str, Any],
    evidence: Iterable[EvidenceDocument],
) -> list[GroundingIssue]:
    value = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    by_id = {item.id: item for item in evidence}
    issues: list[GroundingIssue] = []
    claims = value.get("claims", []) if isinstance(value, dict) else []
    aggregate_facts = set(value.get("fact_citations", [])) if isinstance(value, dict) else set()
    aggregate_jobs = {str(item) for item in value.get("job_citations", [])} if isinstance(value, dict) else set()
    for claim in claims:
        reference_ids = [*claim.get("fact_ids", []), *(str(item) for item in claim.get("job_ids", []))]
        unknown = [reference_id for reference_id in reference_ids if reference_id not in by_id]
        if unknown:
            issues.append(
                GroundingIssue(
                    ValidationCode.EVIDENCE_UNKNOWN,
                    "Claim references unavailable evidence: " + ", ".join(sorted(unknown)),
                )
            )
            continue
        claim_terms = set(tokenize(str(claim.get("text", ""))))
        evidence_terms = {
            token
            for reference_id in reference_ids
            for token in tokenize(by_id[reference_id].text)
        }
        meaningful = {token for token in claim_terms if len(token) >= 4}
        if meaningful and not meaningful.intersection(evidence_terms):
            issues.append(
                GroundingIssue(
                    ValidationCode.UNSUPPORTED_CLAIM,
                    "Claim language is not supported by its cited evidence.",
                )
            )
    if claims and not (aggregate_facts or aggregate_jobs):
        issues.append(
            GroundingIssue(
                ValidationCode.EVIDENCE_MISSING,
                "Grounded claims require aggregate evidence citations.",
            )
        )
    return issues


def validate_semantics(
    task_id: str,
    payload: BaseModel,
    *,
    expected_rows: int | None = None,
) -> list[GroundingIssue]:
    value = payload.model_dump(mode="json")
    issues: list[GroundingIssue] = []
    if expected_rows is not None and task_id in {
        "job_normalize",
        "job_match",
        "job_critique",
        "job_rerank",
    }:
        if len(value.get("results", [])) != expected_rows:
            issues.append(
                GroundingIssue(
                    ValidationCode.ROW_COUNT_MISMATCH,
                    f"Expected {expected_rows} result rows in source order.",
                )
            )
    for result in value.get("results", []):
        for minimum, maximum in (
            ("experience_min_years", "experience_max_years"),
            ("workload_min", "workload_max"),
            ("salary_min_chf", "salary_max_chf"),
        ):
            left, right = result.get(minimum), result.get(maximum)
            if left is not None and right is not None and left > right:
                issues.append(
                    GroundingIssue(
                        ValidationCode.SEMANTIC_INVALID,
                        f"{minimum} cannot exceed {maximum}.",
                    )
                )
    return issues
