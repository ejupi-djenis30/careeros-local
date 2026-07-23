from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import BaseModel

from backend.ai.contracts import ValidationCode
from backend.ai.match_policy import (
    DIMENSION_SCORE_FIELDS,
    derive_match_outcome,
    enforce_match_score_policy,
)
from backend.ai.retrieval import EvidenceDocument, tokenize


@dataclass(frozen=True, slots=True)
class GroundingIssue:
    code: ValidationCode
    message: str


def _normalized_excerpt(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


PLACEHOLDER_TOKENS = {
    "candidate",
    "company",
    "description",
    "evidence",
    "experience",
    "field",
    "fact_type",
    "location",
    "none",
    "profile",
    "payload",
    "required",
    "role",
    "specified",
    "title",
    "unknown",
    "verified",
}
ANSWER_CONNECTIVE_TOKENS = {
    "also",
    "because",
    "emphasize",
    "highlight",
    "lead",
    "with",
    "your",
    "verified",
}
CLAIM_ADVICE_TOKENS = ANSWER_CONNECTIVE_TOKENS | {
    "consider",
    "describe",
    "evidenzia",
    "emphasized",
    "emphasize",
    "focus",
    "mention",
    "metti",
    "supported",
}
CLAIM_FUNCTION_TOKENS = {
    "an",
    "are",
    "as",
    "at",
    "been",
    "by",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "she",
    "that",
    "the",
    "they",
    "this",
    "to",
    "was",
    "we",
    "were",
    "you",
}
GENERIC_MATCH_TOKENS = {
    "application",
    "applications",
    "delivery",
    "engineer",
    "evidence",
    "production",
    "required",
    "service",
    "services",
    "software",
    "systems",
    "work",
}


def _meaningful_excerpt_tokens(value: object) -> list[str]:
    return [
        token.strip(".-")
        for token in tokenize(_normalized_excerpt(value))
        if len(token.strip(".-")) >= 3 and token.strip(".-") not in PLACEHOLDER_TOKENS
    ]


def _lexical_tokens(value: object) -> set[str]:
    return {normalized for token in tokenize(str(value)) if (normalized := token.strip(".-"))}


def _is_missing_quote(value: object) -> bool:
    normalized = _normalized_excerpt(value)
    return normalized.startswith("no explicit ") or normalized.endswith(" is empty.")


def _boundary_tokens(value: object) -> list[str]:
    return [
        token.strip(".-") for token in tokenize(_normalized_excerpt(value)) if token.strip(".-")
    ]


def _is_token_subsequence(excerpt: object, document: str) -> bool:
    """Require a whole-token, contiguous excerpt instead of substring containment."""
    excerpt_tokens = _boundary_tokens(excerpt)
    document_tokens = _boundary_tokens(document)
    if not excerpt_tokens or len(excerpt_tokens) > len(document_tokens):
        return False
    width = len(excerpt_tokens)
    return any(
        document_tokens[index : index + width] == excerpt_tokens
        for index in range(len(document_tokens) - width + 1)
    )


def validate_grounding(
    payload: BaseModel | dict[str, Any],
    evidence: Iterable[EvidenceDocument],
) -> list[GroundingIssue]:
    value = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    by_id = {item.id: item for item in evidence}
    issues: list[GroundingIssue] = []
    claims = value.get("claims", []) if isinstance(value, dict) else []
    aggregate_facts = set(value.get("fact_citations", [])) if isinstance(value, dict) else set()
    aggregate_jobs = (
        {str(item) for item in value.get("job_citations", [])} if isinstance(value, dict) else set()
    )
    for claim in claims:
        reference_ids = [
            *claim.get("fact_ids", []),
            *(str(item) for item in claim.get("job_ids", [])),
        ]
        unknown = [reference_id for reference_id in reference_ids if reference_id not in by_id]
        if unknown:
            issues.append(
                GroundingIssue(
                    ValidationCode.EVIDENCE_UNKNOWN,
                    "Claim references unavailable evidence: " + ", ".join(sorted(unknown)),
                )
            )
            continue
        claim_terms = _lexical_tokens(claim.get("text", ""))
        meaningful = {
            token
            for token in claim_terms
            if (len(token) >= 2 or token.isdigit())
            and token not in PLACEHOLDER_TOKENS
            and token not in CLAIM_ADVICE_TOKENS
            and token not in CLAIM_FUNCTION_TOKENS
        }
        # A proposition must be supported by one cited record. Taking the union of
        # unrelated records lets a model assemble a claim that no source actually makes.
        supported_by_one_source = bool(meaningful) and any(
            not (meaningful - _lexical_tokens(by_id[reference_id].text))
            for reference_id in reference_ids
        )
        if not supported_by_one_source:
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
    answer = str(value.get("answer", "")) if isinstance(value, dict) else ""
    if answer.strip() and not claims:
        issues.append(
            GroundingIssue(
                ValidationCode.EVIDENCE_MISSING,
                "A substantive coach answer requires at least one grounded claim.",
            )
        )
    if answer and claims:
        supported_terms = {
            token
            for claim in claims
            for token in _lexical_tokens(claim.get("text", ""))
            if len(token) >= 4
        }
        for sentence in re.split(r"(?<=[.!?])\s+", answer):
            answer_terms = {
                token
                for token in _lexical_tokens(sentence)
                if len(token) >= 4 and token not in ANSWER_CONNECTIVE_TOKENS
            }
            if answer_terms - supported_terms:
                issues.append(
                    GroundingIssue(
                        ValidationCode.UNSUPPORTED_CLAIM,
                        "Coach answer language is not covered by its grounded claims.",
                    )
                )
    results = value.get("results", []) if isinstance(value, dict) else []
    if results and all(
        isinstance(result, dict)
        and all(field in result for field in DIMENSION_SCORE_FIELDS.values())
        for result in results
    ):
        enforced = enforce_match_score_policy({"results": results}, by_id.values()).get(
            "results", []
        )
        for index, (result, expected) in enumerate(zip(results, enforced, strict=False)):
            changed = [
                field
                for field in DIMENSION_SCORE_FIELDS.values()
                if result.get(field) != expected.get(field)
            ]
            if changed:
                issues.append(
                    GroundingIssue(
                        ValidationCode.SEMANTIC_INVALID,
                        f"Match row {index} violates server-owned evidence policy: "
                        + ", ".join(changed),
                    )
                )
    for index, result in enumerate(results):
        structured = result.get("analysis_structured") if isinstance(result, dict) else None
        if not isinstance(structured, dict):
            continue
        citations = structured.get("evidence_citations", [])
        dimension_scores = {
            dimension: int(result.get(field, 0))
            for dimension, field in DIMENSION_SCORE_FIELDS.items()
        }
        derived_score, _recommendation, _worth_applying = derive_match_outcome(
            dimension_scores, citations
        )
        cited_dimensions = {
            str(citation.get("type") or "") for citation in citations if isinstance(citation, dict)
        }
        missing_dimensions = sorted(
            dimension
            for dimension, score in dimension_scores.items()
            if (score < 45 or score > 55) and dimension not in cited_dimensions
        )
        if missing_dimensions:
            issues.append(
                GroundingIssue(
                    ValidationCode.EVIDENCE_MISSING,
                    "Non-neutral match scores require same-dimension citations: "
                    + ", ".join(missing_dimensions),
                )
            )
        expected_job_id = f"job:{index}"
        seen_citations: set[tuple[str, str]] = set()
        seen_dimensions: set[str] = set()
        independent_strength_pairs: set[tuple[str, str]] = set()
        for citation in citations:
            if not isinstance(citation, dict):
                continue
            job_id = str(citation.get("job_evidence_id") or "")
            candidate_id = str(citation.get("candidate_evidence_id") or "")
            if job_id != expected_job_id or candidate_id != "candidate:profile":
                issues.append(
                    GroundingIssue(
                        ValidationCode.EVIDENCE_UNKNOWN,
                        "Match citation references evidence outside its result row.",
                    )
                )
                continue
            job_document = by_id.get(job_id)
            candidate_document = by_id.get(candidate_id)
            if (
                job_document is None
                or job_document.kind != "job"
                or candidate_document is None
                or candidate_document.kind != "candidate"
            ):
                issues.append(
                    GroundingIssue(
                        ValidationCode.EVIDENCE_UNKNOWN,
                        "Match citation references unavailable evidence.",
                    )
                )
                continue
            job_quote_id = str(citation.get("job_quote_id") or "")
            candidate_quote_id = str(citation.get("candidate_quote_id") or "")
            citation_key = (job_quote_id, candidate_quote_id)
            if citation_key in seen_citations:
                issues.append(
                    GroundingIssue(
                        ValidationCode.SEMANTIC_INVALID,
                        "Duplicate match citations cannot increase evidence coverage.",
                    )
                )
            seen_citations.add(citation_key)
            dimension = str(citation.get("type") or "")
            if dimension in seen_dimensions:
                issues.append(
                    GroundingIssue(
                        ValidationCode.SEMANTIC_INVALID,
                        "Each match dimension may contribute at most one citation.",
                    )
                )
            seen_dimensions.add(dimension)
            job_quotes = job_document.validation_metadata.get("quotes")
            candidate_quotes = candidate_document.validation_metadata.get("quotes")
            job_quote = job_quotes.get(job_quote_id) if isinstance(job_quotes, dict) else None
            candidate_quote = (
                candidate_quotes.get(candidate_quote_id)
                if isinstance(candidate_quotes, dict)
                else None
            )
            if (
                not isinstance(job_quote, dict)
                or not isinstance(candidate_quote, dict)
                or job_quote.get("dimension") != dimension
                or candidate_quote.get("dimension") != dimension
                or job_quote_id not in job_document.text
                or candidate_quote_id not in candidate_document.text
            ):
                issues.append(
                    GroundingIssue(
                        ValidationCode.EVIDENCE_UNKNOWN,
                        "Match citation quote IDs are unavailable for their declared dimension.",
                    )
                )
                continue
            job_excerpt = str(job_quote.get("text") or "")
            candidate_excerpt = str(candidate_quote.get("text") or "")
            job_terms = set(_meaningful_excerpt_tokens(job_excerpt))
            candidate_terms = set(_meaningful_excerpt_tokens(candidate_excerpt))
            source_pair = (
                _normalized_excerpt(job_excerpt),
                _normalized_excerpt(candidate_excerpt),
            )
            job_positive = job_quote.get("has_positive_evidence") is True
            candidate_positive = candidate_quote.get("has_positive_evidence") is True
            shared_terms = job_terms.intersection(candidate_terms) - GENERIC_MATCH_TOKENS
            if not (job_positive and candidate_positive):
                shared_terms = set()
            score = dimension_scores.get(dimension, 50)
            job_status = str(job_quote.get("requirement_status") or "unknown")
            candidate_status = str(candidate_quote.get("requirement_status") or "unknown")
            job_coverage = job_document.validation_metadata.get("coverage_complete")
            candidate_coverage = candidate_document.validation_metadata.get("coverage_complete")
            coverage_complete = (
                isinstance(job_coverage, dict)
                and job_coverage.get(dimension) is True
                and isinstance(candidate_coverage, dict)
                and candidate_coverage.get(dimension) is True
            )
            if not coverage_complete and score != 50:
                issues.append(
                    GroundingIssue(
                        ValidationCode.SEMANTIC_INVALID,
                        "An incomplete atomic evidence catalog requires the neutral score 50.",
                    )
                )
            if job_status == "explicit_not_required" and score != 50:
                issues.append(
                    GroundingIssue(
                        ValidationCode.SEMANTIC_INVALID,
                        "An explicitly non-required job attribute requires the neutral score 50.",
                    )
                )
            elif job_status == "exclusion":
                expected_exclusion_score = score < 45 if shared_terms else score == 50
                if not expected_exclusion_score:
                    issues.append(
                        GroundingIssue(
                            ValidationCode.SEMANTIC_INVALID,
                            "A prohibited or excluded job attribute cannot support a positive score.",
                        )
                    )
            elif job_status == "unknown" and score > 55:
                issues.append(
                    GroundingIssue(
                        ValidationCode.SEMANTIC_INVALID,
                        "A positive score requires an explicit required or preferred job attribute.",
                    )
                )

            job_summary = job_document.validation_metadata.get("requirement_summary")
            candidate_summary = candidate_document.validation_metadata.get("requirement_summary")
            if isinstance(job_summary, dict) and isinstance(candidate_summary, dict):
                if dimension == "skill":
                    required = set(job_summary.get("required_skill_terms") or [])
                    excluded = set(job_summary.get("excluded_skill_terms") or [])
                    observed = set(candidate_summary.get("observed_skill_terms") or [])
                    if required - observed and score > 55:
                        issues.append(
                            GroundingIssue(
                                ValidationCode.SEMANTIC_INVALID,
                                "A positive skill score requires complete required-skill coverage.",
                            )
                        )
                    if excluded & observed and score >= 45:
                        issues.append(
                            GroundingIssue(
                                ValidationCode.SEMANTIC_INVALID,
                                "Candidate evidence conflicts with an explicit skill exclusion.",
                            )
                        )
                elif dimension == "experience":
                    required_years = job_summary.get("required_experience_years")
                    observed_years = candidate_summary.get("observed_experience_years")
                    if (
                        isinstance(required_years, int)
                        and (not isinstance(observed_years, int) or observed_years < required_years)
                        and score > 40
                    ):
                        issues.append(
                            GroundingIssue(
                                ValidationCode.SEMANTIC_INVALID,
                                "Experience below the explicit minimum is capped at 40.",
                            )
                        )
                elif dimension == "language":
                    required_languages = job_summary.get("required_languages")
                    observed_languages = candidate_summary.get("observed_languages")
                    if isinstance(required_languages, dict) and isinstance(
                        observed_languages, dict
                    ):
                        missing_or_lower = {
                            language
                            for language, required_rank in required_languages.items()
                            if not isinstance(observed_languages.get(language), int)
                            or int(observed_languages[language]) < int(required_rank)
                        }
                        if missing_or_lower and score > 55:
                            issues.append(
                                GroundingIssue(
                                    ValidationCode.SEMANTIC_INVALID,
                                    "A positive language score requires every language and CEFR minimum.",
                                )
                            )
                elif dimension == "qualification":
                    required_rank = job_summary.get("required_qualification_rank")
                    observed_rank = candidate_summary.get("observed_qualification_rank")
                    if (
                        isinstance(required_rank, int)
                        and required_rank > 0
                        and (not isinstance(observed_rank, int) or observed_rank < required_rank)
                        and score > 40
                    ):
                        issues.append(
                            GroundingIssue(
                                ValidationCode.SEMANTIC_INVALID,
                                "Qualification below the explicit minimum is capped at 40.",
                            )
                        )
            job_missing = not job_positive or _is_missing_quote(job_excerpt)
            candidate_missing = (
                not candidate_positive
                or candidate_status in {"explicit_not_required", "exclusion"}
                or _is_missing_quote(candidate_excerpt)
            )
            if job_missing and candidate_missing and score != 50:
                issues.append(
                    GroundingIssue(
                        ValidationCode.SEMANTIC_INVALID,
                        "Two missing-evidence quotes require the neutral score 50.",
                    )
                )
            elif job_missing and score != 50:
                issues.append(
                    GroundingIssue(
                        ValidationCode.SEMANTIC_INVALID,
                        "A job dimension with no explicit requirement requires the neutral score 50.",
                    )
                )
            elif candidate_missing and score >= 45:
                issues.append(
                    GroundingIssue(
                        ValidationCode.SEMANTIC_INVALID,
                        "Missing candidate evidence cannot support a neutral-or-positive match score.",
                    )
                )
            elif shared_terms and score < 45:
                issues.append(
                    GroundingIssue(
                        ValidationCode.SEMANTIC_INVALID,
                        "Matching evidence cannot support an opposite-extreme match score.",
                    )
                )
            elif not shared_terms and score > 55:
                issues.append(
                    GroundingIssue(
                        ValidationCode.UNSUPPORTED_CLAIM,
                        "A positive match score requires meaningful whole-token overlap.",
                    )
                )
            if score >= 60 and shared_terms and not (job_missing or candidate_missing):
                independent_strength_pairs.add(source_pair)
            if not job_terms or not candidate_terms:
                issues.append(
                    GroundingIssue(
                        ValidationCode.UNSUPPORTED_CLAIM,
                        "Match citation quotes do not contain meaningful evidence.",
                    )
                )
        if derived_score >= 80 and len(independent_strength_pairs) < 2:
            issues.append(
                GroundingIssue(
                    ValidationCode.SEMANTIC_INVALID,
                    "A high match score requires two independent supported strengths.",
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
