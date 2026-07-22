from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError

from backend.ai.audit import fingerprint_output
from backend.ai.contracts import JobMatch
from backend.ai.match_policy import (
    DIMENSION_SCORE_FIELDS,
    derive_citation_assessment,
    derive_match_presentation,
    persisted_outcome_is_consistent,
)


class MatchAttestationError(ValueError):
    """Raised when a persisted match cannot be linked to an accepted model result."""


def _value(source: object, key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)


def _mapping(value: object) -> dict[str, Any] | None:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _score(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MatchAttestationError(f"{field} must be a finite whole number")
    numeric = float(value)
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise MatchAttestationError(f"{field} must be a finite whole number")
    result = int(numeric)
    if not 0 <= result <= 100:
        raise MatchAttestationError(f"{field} is outside the contract range")
    return result


def canonical_contract_row(analysis: object) -> dict[str, Any]:
    """Rebuild the exact audited score row, excluding server-derived display data."""
    payload = {
        field: _score(_value(analysis, field), field) for field in DIMENSION_SCORE_FIELDS.values()
    }
    try:
        return JobMatch.model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        raise MatchAttestationError("analysis does not satisfy the job-match contract") from exc


def validate_persisted_match_payload(analysis: object) -> dict[str, Any]:
    """Validate row fingerprint and deterministic outcome without trusting metadata."""
    canonical = canonical_contract_row(analysis)
    row_fingerprint = _value(analysis, "analysis_row_fingerprint")
    if not isinstance(row_fingerprint, str) or fingerprint_output(canonical) != row_fingerprint:
        raise MatchAttestationError("analysis row fingerprint does not match its contract payload")

    structured = _mapping(_value(analysis, "analysis_structured")) or {}
    citations = structured.get("evidence_citations")
    dimension_scores = {
        dimension: canonical[field] for dimension, field in DIMENSION_SCORE_FIELDS.items()
    }
    if not isinstance(citations, list) or not persisted_outcome_is_consistent(
        affinity_score=_value(analysis, "affinity_score"),
        worth_applying=_value(analysis, "worth_applying"),
        recommendation=structured.get("recommendation"),
        dimension_scores=dimension_scores,
        citations=citations,
    ):
        raise MatchAttestationError("visible match outcome is inconsistent with cited dimensions")
    expected_summary, expected_flags = derive_match_presentation(
        str(structured.get("recommendation")), citations
    )
    if _value(analysis, "affinity_analysis") != expected_summary:
        raise MatchAttestationError("visible match summary is not deterministically derived")
    if _value(analysis, "red_flags") != expected_flags:
        raise MatchAttestationError("visible match flags are not deterministically derived")
    return canonical


def validate_match_attestation(
    analysis: object,
    execution: object | None,
    *,
    expected_user_id: int | None,
    expected_input_fingerprint: str,
    expected_quote_bindings: Mapping[str, Mapping[str, Any]],
    expected_citations: Sequence[Mapping[str, Any]],
) -> None:
    """Verify a persisted row against its exact accepted AIExecution receipt."""
    canonical = validate_persisted_match_payload(analysis)
    if _value(analysis, "analysis_provenance") != "local_model_validated":
        raise MatchAttestationError("analysis provenance is not model-validated")
    model_id = _value(analysis, "analysis_model_id")
    if not isinstance(model_id, str) or not model_id.strip():
        raise MatchAttestationError("analysis model identity is missing")
    if _value(analysis, "analysis_contract_version") != "1.1.0":
        raise MatchAttestationError("analysis contract version is unsupported")
    if _value(analysis, "analysis_validated_at") is None:
        raise MatchAttestationError("analysis validation time is missing")
    if execution is None:
        raise MatchAttestationError("analysis execution receipt is missing")

    execution_id = _value(analysis, "analysis_execution_id")
    try:
        if not isinstance(execution_id, str) or str(UUID(execution_id)) != execution_id:
            raise ValueError
    except ValueError as exc:
        raise MatchAttestationError("analysis execution identity is invalid") from exc
    if _value(execution, "id") != execution_id:
        raise MatchAttestationError("analysis references a different execution")
    if _value(execution, "accepted") is not True or _value(execution, "task") != "job_match":
        raise MatchAttestationError("analysis execution was not an accepted job match")
    if (
        _value(execution, "model_id") != model_id
        or _value(execution, "contract_version") != "1.1.0"
    ):
        raise MatchAttestationError("analysis model receipt does not match its metadata")
    if expected_user_id is not None and _value(execution, "user_id") != expected_user_id:
        raise MatchAttestationError("analysis execution belongs to a different user")

    output_fingerprint = _value(analysis, "analysis_output_fingerprint")
    if (
        not isinstance(output_fingerprint, str)
        or len(output_fingerprint) != 64
        or _value(execution, "output_fingerprint") != output_fingerprint
    ):
        raise MatchAttestationError("analysis batch fingerprint does not match its execution")
    row_index = _value(analysis, "analysis_execution_row_index")
    rows = _value(execution, "row_fingerprints")
    input_rows = _value(execution, "row_input_fingerprints")
    if (
        isinstance(row_index, bool)
        or not isinstance(row_index, int)
        or not isinstance(rows, list)
        or not 0 <= row_index < len(rows)
        or rows[row_index] != _value(analysis, "analysis_row_fingerprint")
    ):
        raise MatchAttestationError("analysis row is not present in its execution receipt")
    input_fingerprint = _value(analysis, "analysis_input_fingerprint")
    if (
        not isinstance(input_fingerprint, str)
        or input_fingerprint != expected_input_fingerprint
        or not isinstance(input_rows, list)
        or row_index >= len(input_rows)
        or input_rows[row_index] != input_fingerprint
    ):
        raise MatchAttestationError("analysis input does not match its current job evidence")

    structured = _mapping(_value(analysis, "analysis_structured")) or {}
    citations = structured.get("evidence_citations")
    if not isinstance(citations, list):
        raise MatchAttestationError("analysis citations are unavailable")
    citation_fields = (
        "type",
        "assessment",
        "job_evidence_id",
        "candidate_evidence_id",
        "job_quote_id",
        "candidate_quote_id",
        "job_quote_hash",
        "candidate_quote_hash",
        "job_evidence",
        "candidate_evidence",
    )

    mapped_citations = [_mapping(item) for item in citations]
    mapped_expected = [_mapping(item) for item in expected_citations]
    if (
        len(mapped_citations) != len(mapped_expected)
        or any(item is None for item in (*mapped_citations, *mapped_expected))
        or any(
            actual.get(field) != expected.get(field)
            for actual, expected in zip(mapped_citations, mapped_expected, strict=True)
            if actual is not None and expected is not None
            for field in citation_fields
        )
    ):
        raise MatchAttestationError("analysis citations are not server-materialized")
    dimension_scores = {
        dimension: canonical[field] for dimension, field in DIMENSION_SCORE_FIELDS.items()
    }
    for citation in citations:
        mapped = _mapping(citation)
        if mapped is None:
            raise MatchAttestationError("analysis citation is not an object")
        dimension = mapped.get("type")
        quote_bindings: dict[str, Mapping[str, Any]] = {}
        for side in ("job", "candidate"):
            quote_id = mapped.get(f"{side}_quote_id")
            binding = expected_quote_bindings.get(str(quote_id))
            if (
                not isinstance(binding, Mapping)
                or binding.get("dimension") != dimension
                or binding.get("text_hash") != mapped.get(f"{side}_quote_hash")
                or binding.get("text") != mapped.get(f"{side}_evidence")
            ):
                raise MatchAttestationError(
                    "analysis citation does not match its current atomic evidence"
                )
            quote_bindings[side] = binding
        expected_assessment = derive_citation_assessment(
            dimension=str(dimension),
            score=dimension_scores[str(dimension)],
            job_quote=quote_bindings["job"],
            candidate_quote=quote_bindings["candidate"],
        )
        if mapped.get("assessment") != expected_assessment:
            raise MatchAttestationError(
                "analysis citation assessment is not deterministically materialized"
            )


def is_persisted_match_payload_valid(analysis: object) -> bool:
    try:
        validate_persisted_match_payload(analysis)
    except MatchAttestationError:
        return False
    return True
