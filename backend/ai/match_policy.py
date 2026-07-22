from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from backend.ai.retrieval import EvidenceDocument, tokenize

DIMENSION_SCORE_FIELDS = {
    "skill": "skill_match_score",
    "experience": "experience_match_score",
    "intent": "intent_match_score",
    "language": "language_match_score",
    "location": "location_match_score",
    "transferability": "transferability_score",
    "qualification": "qualification_gap_score",
}

DIMENSION_WEIGHTS = {
    "skill": 0.25,
    "experience": 0.20,
    "intent": 0.20,
    "language": 0.10,
    "location": 0.10,
    "transferability": 0.10,
    "qualification": 0.05,
}

RISK_SCORE_CAPS = {"intent": 20, "language": 30, "qualification": 40}

_GENERIC_MATCH_TERMS = {
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
    # Localized requirement scaffolding must not manufacture semantic support.
    "almeno",
    "anni",
    "ans",
    "années",
    "berufserfahrung",
    "erfahrung",
    "erforderlich",
    "esperienza",
    "expérience",
    "facoltativo",
    "facultatif",
    "jahre",
    "jahren",
    "mindestens",
    "obbligatorio",
    "obligatoire",
    "optional",
    "requis",
    "requise",
    "richiesto",
    "richiesta",
    "wünschenswert",
}

_MANDATORY_SCORE_CAPS = {
    "skill": 40,
    "experience": 40,
    "intent": 20,
    "language": 30,
    "location": 40,
    "transferability": 40,
    "qualification": 40,
}


def _semantic_terms(value: object) -> set[str]:
    return {
        token.strip(".-").casefold()
        for token in tokenize(str(value or ""))
        if len(token.strip(".-")) >= 2 and token.strip(".-").casefold() not in _GENERIC_MATCH_TERMS
    }


def _document_quotes(document: EvidenceDocument, dimension: str) -> list[tuple[str, dict]]:
    quotes = document.validation_metadata.get("quotes")
    if not isinstance(quotes, Mapping):
        return []
    return sorted(
        (
            (str(quote_id), dict(quote))
            for quote_id, quote in quotes.items()
            if isinstance(quote, Mapping) and quote.get("dimension") == dimension
        ),
        key=lambda item: tuple(
            int(part) if part.isdigit() else part for part in item[0].split(":")
        ),
    )


def _positive_quote(quote: Mapping[str, Any]) -> bool:
    return quote.get("has_positive_evidence") is True and str(
        quote.get("requirement_status") or "unknown"
    ) not in {"unknown", "explicit_not_required", "exclusion"}


def _dimension_has_support(
    dimension: str,
    candidate: EvidenceDocument,
    job: EvidenceDocument,
) -> bool:
    for _job_id, job_quote in _document_quotes(job, dimension):
        if not _positive_quote(job_quote):
            continue
        job_terms = _semantic_terms(job_quote.get("text"))
        for _candidate_id, candidate_quote in _document_quotes(candidate, dimension):
            if _positive_quote(candidate_quote) and job_terms & _semantic_terms(
                candidate_quote.get("text")
            ):
                return True
    return False


def _dimension_support_pairs(
    dimension: str,
    candidate: EvidenceDocument,
    job: EvidenceDocument,
) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for _job_id, job_quote in _document_quotes(job, dimension):
        if not _positive_quote(job_quote):
            continue
        job_terms = _semantic_terms(job_quote.get("text"))
        for _candidate_id, candidate_quote in _document_quotes(candidate, dimension):
            if not _positive_quote(candidate_quote):
                continue
            if job_terms & _semantic_terms(candidate_quote.get("text")):
                pairs.add(
                    (
                        " ".join(str(job_quote.get("text") or "").casefold().split()),
                        " ".join(str(candidate_quote.get("text") or "").casefold().split()),
                    )
                )
    return pairs


def _summary(document: EvidenceDocument) -> dict[str, Any]:
    value = document.validation_metadata.get("requirement_summary")
    return dict(value) if isinstance(value, Mapping) else {}


def _mandatory_mismatch_dimensions(
    candidate: EvidenceDocument,
    job: EvidenceDocument,
) -> set[str]:
    """Evaluate every server-extracted mandatory requirement, citation-free."""
    candidate_summary = _summary(candidate)
    job_summary = _summary(job)
    mismatches: set[str] = set()

    observed_skills = set(candidate_summary.get("observed_skill_terms") or [])
    negated_skills = set(candidate_summary.get("negated_skill_terms") or [])
    required_skills = set(job_summary.get("required_skill_terms") or [])
    raw_required_groups = job_summary.get("required_skill_groups")
    required_skill_groups = (
        [
            {str(term) for term in group if isinstance(term, str)}
            for group in raw_required_groups
            if isinstance(group, Sequence) and not isinstance(group, (str, bytes))
        ]
        if isinstance(raw_required_groups, Sequence)
        and not isinstance(raw_required_groups, (str, bytes))
        else [{term} for term in required_skills]
    )
    required_skill_groups = [group for group in required_skill_groups if group]
    excluded_skills = set(job_summary.get("excluded_skill_terms") or [])
    if any(not ((group & observed_skills) - negated_skills) for group in required_skill_groups):
        mismatches.update({"skill", "transferability"})
    if excluded_skills & observed_skills:
        mismatches.update({"skill", "transferability"})

    required_years = job_summary.get("required_experience_years")
    observed_years = candidate_summary.get("observed_experience_years")
    if isinstance(required_years, int) and (
        not isinstance(observed_years, int) or observed_years < required_years
    ):
        mismatches.add("experience")

    required_languages = job_summary.get("required_languages")
    observed_languages = candidate_summary.get("observed_languages")
    if isinstance(required_languages, Mapping) and isinstance(observed_languages, Mapping):
        if any(
            not isinstance(observed_languages.get(language), int)
            or int(observed_languages[language]) < int(required_rank)
            for language, required_rank in required_languages.items()
        ):
            mismatches.add("language")

    required_qualification = job_summary.get("required_qualification_rank")
    observed_qualification = candidate_summary.get("observed_qualification_rank")
    if (
        isinstance(required_qualification, int)
        and required_qualification > 0
        and (
            not isinstance(observed_qualification, int)
            or observed_qualification < required_qualification
        )
    ):
        mismatches.add("qualification")

    for dimension in ("location",):
        job_quotes = _document_quotes(job, dimension)
        has_required = any(
            str(quote.get("requirement_status") or "") == "required"
            for _quote_id, quote in job_quotes
        )
        if has_required and not _dimension_has_support(dimension, candidate, job):
            mismatches.add(dimension)
    return mismatches


def enforce_match_score_policy(
    payload: Mapping[str, Any],
    evidence: Iterable[EvidenceDocument],
) -> dict[str, Any]:
    """Apply deterministic evidence caps to local-model score proposals.

    The model is required to propose all seven scores. Requirement extraction,
    negative evidence, conservative caps and citations remain server-owned.
    """
    documents = tuple(evidence)
    candidate = next((item for item in documents if item.id == "candidate:profile"), None)
    jobs = {
        item.id: item for item in documents if item.kind == "job" and item.id.startswith("job:")
    }
    rows = payload.get("results")
    if candidate is None or not isinstance(rows, list):
        return dict(payload)

    enforced_rows: list[dict[str, int]] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            enforced_rows.append(dict(row))
            continue
        job = jobs.get(f"job:{row_index}")
        if job is None:
            enforced_rows.append(dict(row))
            continue
        mismatches = _mandatory_mismatch_dimensions(candidate, job)
        enforced: dict[str, int] = {}
        for dimension, field in DIMENSION_SCORE_FIELDS.items():
            raw = row.get(field, 50)
            score = int(raw) if isinstance(raw, int) and not isinstance(raw, bool) else 50
            score = max(0, min(100, score))
            job_quotes = _document_quotes(job, dimension)
            informative_job_quotes = [
                quote
                for _quote_id, quote in job_quotes
                if quote.get("has_positive_evidence") is True
                or str(quote.get("requirement_status") or "")
                in {"explicit_not_required", "exclusion"}
            ]
            positive_job_quotes = [
                quote for quote in informative_job_quotes if _positive_quote(quote)
            ]
            only_not_required = informative_job_quotes and all(
                str(quote.get("requirement_status") or "") == "explicit_not_required"
                for quote in informative_job_quotes
            )
            if not informative_job_quotes or only_not_required:
                score = 50
            elif dimension in mismatches:
                score = min(score, _MANDATORY_SCORE_CAPS[dimension])
            elif positive_job_quotes and not _dimension_has_support(dimension, candidate, job):
                # A descriptive attribute can justify a positive match even without
                # required/preferred boilerplate, but only with explicit overlap.
                score = min(score, 55)
            elif _dimension_has_support(dimension, candidate, job) and score < 45:
                score = 45
            enforced[field] = score
        weighted_score = round(
            sum(
                enforced[DIMENSION_SCORE_FIELDS[dimension]] * weight
                for dimension, weight in DIMENSION_WEIGHTS.items()
            )
        )
        support_pairs = {
            pair
            for dimension, field in DIMENSION_SCORE_FIELDS.items()
            if enforced[field] > 55
            for pair in _dimension_support_pairs(dimension, candidate, job)
        }
        if weighted_score >= 80 and len(support_pairs) < 2:
            enforced = {field: min(score, 79) for field, score in enforced.items()}
        enforced_rows.append(enforced)
    return {"results": enforced_rows}


def materialize_match_citations(
    *,
    candidate: EvidenceDocument,
    job: EvidenceDocument,
    dimension_scores: Mapping[str, int],
) -> list[dict[str, Any]]:
    """Select immutable evidence pairs for every dimension and explicit requirement."""
    materialized: list[dict[str, Any]] = []
    for dimension in DIMENSION_SCORE_FIELDS:
        job_quotes = _document_quotes(job, dimension)
        candidate_quotes = _document_quotes(candidate, dimension)
        explicit = [
            item
            for item in job_quotes
            if str(item[1].get("requirement_status") or "")
            in {"required", "preferred", "explicit_not_required", "exclusion"}
        ]
        selected_job_quotes = explicit or job_quotes[:1]
        for job_quote_id, job_quote in selected_job_quotes:
            job_terms = _semantic_terms(job_quote.get("text"))

            def candidate_rank(item: tuple[str, dict]) -> tuple[int, int, str]:
                quote_id, quote = item
                positive = int(_positive_quote(quote))
                overlap = len(job_terms & _semantic_terms(quote.get("text")))
                return (overlap, positive, quote_id)

            candidate_quote_id, candidate_quote = max(
                candidate_quotes,
                key=candidate_rank,
                default=(
                    f"candidate:profile:{dimension}:0",
                    {
                        "dimension": dimension,
                        "has_positive_evidence": False,
                        "requirement_status": "unknown",
                        "text": f"No explicit {dimension} evidence.",
                        "text_hash": "",
                    },
                ),
            )
            assessment = derive_citation_assessment(
                dimension=dimension,
                score=int(dimension_scores[dimension]),
                job_quote=job_quote,
                candidate_quote=candidate_quote,
            )
            materialized.append(
                {
                    "type": dimension,
                    "assessment": assessment,
                    "job_evidence_id": job.id,
                    "candidate_evidence_id": candidate.id,
                    "job_quote_id": job_quote_id,
                    "candidate_quote_id": candidate_quote_id,
                    "job_quote_hash": str(job_quote.get("text_hash") or ""),
                    "candidate_quote_hash": str(candidate_quote.get("text_hash") or ""),
                    "job_evidence": str(job_quote.get("text") or ""),
                    "candidate_evidence": str(candidate_quote.get("text") or ""),
                }
            )
    return materialized


def derive_citation_assessment(
    *,
    dimension: str,
    score: int,
    job_quote: Mapping[str, Any],
    candidate_quote: Mapping[str, Any],
) -> str:
    """Derive the only valid materialized assessment for an atomic quote pair."""
    job_positive = job_quote.get("has_positive_evidence") is True
    candidate_positive = candidate_quote.get("has_positive_evidence") is True
    job_status = str(job_quote.get("requirement_status") or "unknown")
    candidate_status = str(candidate_quote.get("requirement_status") or "unknown")
    if job_status == "explicit_not_required":
        return "insufficient_evidence"
    if candidate_status in {"explicit_not_required", "exclusion"}:
        candidate_positive = False
    shared_terms = (
        set(tokenize(str(job_quote.get("text") or "")))
        & set(tokenize(str(candidate_quote.get("text") or "")))
    ) - _GENERIC_MATCH_TERMS
    risk_cap = RISK_SCORE_CAPS.get(dimension)
    if not job_positive or score == 50:
        return "insufficient_evidence"
    if (
        risk_cap is not None
        and score <= risk_cap
        and (job_status == "required" or not candidate_positive or not shared_terms)
    ):
        return "risk"
    if not candidate_positive or score < 45:
        return "gap"
    if score >= 60:
        return "strength"
    return "weakness"


def derive_match_presentation(
    recommendation: str,
    citations: Sequence[Mapping[str, Any]],
) -> tuple[str, list[str] | None]:
    """Build the only display narrative and flags allowed for an attested row."""
    assessment_counts = {
        label: sum(1 for citation in citations if citation.get("assessment") == label)
        for label in ("strength", "weakness", "gap", "risk")
    }
    cited_dimensions = sorted(
        {str(citation.get("type")) for citation in citations if citation.get("type")}
    )
    summary = (
        f"Local evidence review: {recommendation.replace('_', ' ')}. "
        f"{assessment_counts['strength']} supported strength(s), "
        f"{assessment_counts['weakness'] + assessment_counts['gap']} supported gap(s), "
        f"{assessment_counts['risk']} risk signal(s). "
        f"Evidence dimensions: {', '.join(cited_dimensions)}."
    )
    flags = list(
        dict.fromkeys(
            f"evidence_risk:{citation['type']}"
            for citation in citations
            if citation.get("assessment") == "risk" and citation.get("type")
        )
    )
    return summary, flags or None


def derive_match_outcome(
    dimension_scores: Mapping[str, int],
    citations: Sequence[Mapping[str, Any]],
) -> tuple[int, str, bool]:
    """Derive the visible match outcome from validated dimensions and risk evidence."""
    score = round(
        sum(
            int(dimension_scores[dimension]) * weight
            for dimension, weight in DIMENSION_WEIGHTS.items()
        )
    )
    risk_types = {
        str(citation.get("type")) for citation in citations if citation.get("assessment") == "risk"
    }
    caps = [cap for dimension, cap in RISK_SCORE_CAPS.items() if dimension in risk_types]
    if caps:
        score = min(score, min(caps))

    insufficient_count = sum(
        1 for citation in citations if citation.get("assessment") == "insufficient_evidence"
    )
    if citations and insufficient_count == len(citations):
        recommendation = "insufficient_evidence"
    elif score >= 80:
        recommendation = "strong_fit"
    elif score >= 55:
        recommendation = "consider"
    else:
        recommendation = "weak_fit"
    worth_applying = score >= 65 and recommendation in {"strong_fit", "consider"}
    return score, recommendation, worth_applying


def persisted_outcome_is_consistent(
    *,
    affinity_score: object,
    worth_applying: object,
    recommendation: object,
    dimension_scores: Mapping[str, int],
    citations: Sequence[Mapping[str, Any]],
) -> bool:
    try:
        expected_score, expected_recommendation, expected_worth = derive_match_outcome(
            dimension_scores, citations
        )
        if isinstance(affinity_score, bool) or not isinstance(affinity_score, (int, float)):
            return False
        if not math.isfinite(float(affinity_score)) or float(affinity_score) != expected_score:
            return False
        return (
            type(worth_applying) is bool
            and worth_applying is expected_worth
            and isinstance(recommendation, str)
            and recommendation == expected_recommendation
        )
    except (KeyError, TypeError, ValueError):
        return False
