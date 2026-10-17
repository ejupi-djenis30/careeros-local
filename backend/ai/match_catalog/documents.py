"""Bounded candidate and job evidence document assembly."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.ai.retrieval import EvidenceDocument
from backend.services.search.prompt_compaction import compact_prompt_text
from backend.services.search.query_contracts import sanitize_prompt_text
from backend.services.utils import clean_html_tags

from .catalog import _atomic_quotes, _catalog_fingerprint, _coverage_complete, _source_fingerprint
from .constants import _CANDIDATE_EVIDENCE_CHARS, _JOB_EVIDENCE_CHARS
from .fragments import _matching_fragments, _skill_evidence
from .requirements import _requirement_summary


def candidate_evidence_document(
    profile: Mapping[str, Any],
    *,
    catalog_version: str,
) -> EvidenceDocument:
    role = sanitize_prompt_text(profile.get("role_description") or "", max_chars=1000)
    strategy = sanitize_prompt_text(profile.get("search_strategy") or "", max_chars=1000)
    raw_cv = clean_html_tags(str(profile.get("cv_content") or ""))
    cv = compact_prompt_text(raw_cv, 4000)
    location_filter = sanitize_prompt_text(profile.get("location_filter") or "", max_chars=500)
    language = _matching_fragments(cv, "language")
    location = _matching_fragments(cv, "location")
    qualification = _matching_fragments(cv, "qualification")
    dimensions = {
        "skill": _skill_evidence(cv, "No explicit skill evidence in raw candidate profile."),
        "experience": _matching_fragments(cv, "experience")
        or "No explicit experience evidence in raw candidate profile.",
        "intent": f"Expected Role: {role}. Search Strategy: {strategy}",
        "language": language or "No explicit language evidence in raw candidate profile.",
        "location": "\n".join(
            part
            for part in (
                f"Preferred Location: {location_filter}." if location_filter else "",
                location,
            )
            if part
        )
        or "No explicit location evidence in raw candidate profile.",
        "transferability": _skill_evidence(
            cv, "No explicit transferability evidence in raw candidate profile."
        ),
        "qualification": qualification
        or "No explicit qualification evidence in raw candidate profile.",
    }
    text, quotes = _atomic_quotes(
        "candidate:profile",
        dimensions,
        max_document_chars=_CANDIDATE_EVIDENCE_CHARS,
        source_kind="candidate",
    )
    summary_dimensions = {
        **dimensions,
        "skill": _skill_evidence(raw_cv, "No explicit skill evidence in raw candidate profile."),
        "experience": _matching_fragments(raw_cv, "experience")
        or "No explicit experience evidence in raw candidate profile.",
        "language": _matching_fragments(raw_cv, "language")
        or "No explicit language evidence in raw candidate profile.",
        "location": "\n".join(
            part
            for part in (
                f"Preferred Location: {location_filter}." if location_filter else "",
                _matching_fragments(raw_cv, "location"),
            )
            if part
        )
        or "No explicit location evidence in raw candidate profile.",
        "transferability": _skill_evidence(
            raw_cv, "No explicit transferability evidence in raw candidate profile."
        ),
        "qualification": _matching_fragments(raw_cv, "qualification")
        or "No explicit qualification evidence in raw candidate profile.",
    }
    # Keep the complete server-side catalog even when the prompt projection is
    # compact. The model proposes scores; it never selects these quote IDs.
    _, quotes = _atomic_quotes(
        "candidate:profile",
        summary_dimensions,
        max_document_chars=_CANDIDATE_EVIDENCE_CHARS,
        source_kind="candidate",
    )
    requirement_summary = _requirement_summary(
        summary_dimensions,
        source_kind="candidate",
        source_text=raw_cv,
    )
    coverage_complete = _coverage_complete(summary_dimensions, source_kind="candidate")
    if not cv:
        text += "\nSOURCE_STATUS: Candidate CV is empty."
    return EvidenceDocument(
        id="candidate:profile",
        kind="candidate",
        text=text,
        validation_metadata={
            "source_fingerprint": _source_fingerprint(
                {
                    "cv_content": str(profile.get("cv_content") or ""),
                    "role_description": str(profile.get("role_description") or ""),
                    "search_strategy": str(profile.get("search_strategy") or ""),
                    "location_filter": str(profile.get("location_filter") or ""),
                }
            ),
            "catalog_fingerprint": _catalog_fingerprint(
                quotes,
                catalog_version=catalog_version,
                requirement_summary=requirement_summary,
                coverage_complete=coverage_complete,
            ),
            "catalog_version": catalog_version,
            "coverage_complete": coverage_complete,
            "quotes": quotes,
            "requirement_summary": requirement_summary,
        },
    )


def job_evidence_document(
    job: Mapping[str, Any],
    row_index: int,
    *,
    description_limit: int,
    catalog_version: str,
    description_chars: int,
) -> EvidenceDocument:
    # The catalog is canonical and deliberately independent of runtime prompt tuning.
    # A model with a smaller context still receives the same bounded quote set, so a
    # persisted quote ID cannot silently change meaning when settings change.
    _ = description_limit
    raw_description = clean_html_tags(str(job.get("description") or ""))
    description = compact_prompt_text(raw_description, description_chars)
    language_evidence = (
        "\n".join(part for part in (_matching_fragments(description, "language"),) if part)
        or "No explicit language requirement in raw job evidence."
    )
    qualification_evidence = (
        "\n".join(part for part in (_matching_fragments(description, "qualification"),) if part)
        or "No explicit qualification requirement in raw job evidence."
    )
    title = sanitize_prompt_text(job.get("title") or "", max_chars=500)
    location = sanitize_prompt_text(job.get("location") or "", max_chars=500)
    dimensions = {
        "skill": _skill_evidence(description, "No explicit skill requirement in raw job evidence."),
        "experience": _matching_fragments(description, "experience")
        or "No explicit experience requirement in raw job evidence.",
        "intent": f"Title: {title}." if title else "No explicit intent evidence.",
        "language": language_evidence,
        "location": f"Location: {location}. {_matching_fragments(description, 'location')}",
        "transferability": _skill_evidence(
            description, "No explicit transferability requirement in raw job evidence."
        ),
        "qualification": qualification_evidence,
    }
    text, quotes = _atomic_quotes(
        f"job:{row_index}",
        dimensions,
        max_document_chars=_JOB_EVIDENCE_CHARS,
        source_kind="job",
    )
    summary_dimensions = {
        **dimensions,
        "skill": _skill_evidence(
            raw_description, "No explicit skill requirement in raw job evidence."
        ),
        "experience": _matching_fragments(raw_description, "experience")
        or "No explicit experience requirement in raw job evidence.",
        "intent": f"Title: {title}." if title else "No explicit intent evidence.",
        "language": _matching_fragments(raw_description, "language")
        or "No explicit language requirement in raw job evidence.",
        "location": f"Location: {location}. {_matching_fragments(raw_description, 'location')}",
        "transferability": _skill_evidence(
            raw_description, "No explicit transferability requirement in raw job evidence."
        ),
        "qualification": _matching_fragments(raw_description, "qualification")
        or "No explicit qualification requirement in raw job evidence.",
    }
    _, quotes = _atomic_quotes(
        f"job:{row_index}",
        summary_dimensions,
        max_document_chars=_JOB_EVIDENCE_CHARS,
        source_kind="job",
    )
    requirement_summary = _requirement_summary(
        summary_dimensions,
        source_kind="job",
        source_text=raw_description,
    )
    coverage_complete = _coverage_complete(summary_dimensions, source_kind="job")
    return EvidenceDocument(
        id=f"job:{row_index}",
        kind="job",
        text=text,
        validation_metadata={
            "source_fingerprint": _source_fingerprint(
                {
                    "company": str(job.get("company") or ""),
                    "description": clean_html_tags(str(job.get("description") or "")),
                    "location": str(job.get("location") or ""),
                    "title": clean_html_tags(str(job.get("title") or "")),
                    "workload": str(job.get("workload") or ""),
                }
            ),
            "catalog_fingerprint": _catalog_fingerprint(
                quotes,
                catalog_version=catalog_version,
                requirement_summary=requirement_summary,
                coverage_complete=coverage_complete,
            ),
            "catalog_version": catalog_version,
            "coverage_complete": coverage_complete,
            "quotes": quotes,
            "requirement_summary": requirement_summary,
        },
    )
