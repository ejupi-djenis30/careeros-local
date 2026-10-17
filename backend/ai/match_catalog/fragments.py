"""Dimension fragments and positive evidence classification."""

from __future__ import annotations

import re

from .clause_types import _ClauseSegment
from .clauses import _classification_text, _positive_reassertion, _structured_clauses
from .constants import _DIMENSION_PATTERNS, _FRAGMENT_SPLIT, _REQUIREMENT_STATUS_PATTERNS
from .skill_terms import _skill_terms


def _segment_fragment(segment: _ClauseSegment) -> str:
    fragment = segment.text
    if segment.connector == "scoped_absence" and segment.connector_text:
        fragment = f"{segment.connector_text} {fragment}"
    if segment.absence_scope and _skill_terms(segment.text):
        fragment = f"{fragment} prohibited"
    elif segment.explicit_status is None and segment.inherited_status is not None:
        marker = {
            "explicit_not_required": "optional",
            "exclusion": "prohibited",
            "preferred": "preferred",
            "required": "required",
        }.get(segment.inherited_status)
        if marker is not None:
            fragment = f"{fragment} {marker}"
    return fragment.strip()


def _matching_fragments(text: str, dimension: str) -> str:
    pattern = _DIMENSION_PATTERNS[dimension]
    return "\n".join(
        fragment
        for sentence in _FRAGMENT_SPLIT.split(text)
        for fragment in _all_fragments(sentence)
        if pattern.search(fragment)
    )


def _explicit_requirement_status(value: str) -> str | None:
    value = _classification_text(value)
    for status, pattern in _REQUIREMENT_STATUS_PATTERNS:
        if pattern.search(value):
            return status
    return None


def _is_missing_evidence(value: str) -> bool:
    normalized = " ".join(value.casefold().split())
    return (
        not normalized
        or normalized.startswith("no explicit ")
        or "no description provided" in normalized
        or normalized.endswith(" is empty.")
    )


def _requirement_status(value: str) -> str:
    # Synthetic catalog fallbacks deliberately contain words such as
    # "requirement". They must remain unknown rather than being promoted to a
    # real requirement by the marker parser below.
    if _is_missing_evidence(value):
        return "unknown"
    explicit = _explicit_requirement_status(value)
    if explicit is not None:
        return explicit
    return "present"


def _all_fragments(value: str) -> list[str]:
    """Project structured clauses into independently classifiable quote text."""
    return [_segment_fragment(segment) for segment in _structured_clauses(value)]


def _skill_evidence(value: str, fallback: str) -> str:
    """Keep skill clauses separate from language, degree and tenure requirements."""
    relevant = [
        fragment
        for fragment in _all_fragments(value)
        if _skill_terms(fragment) or _positive_reassertion(fragment)
    ]
    return "\n".join(relevant) or fallback


def _quote_fragments(value: str, fallback: str) -> list[str]:
    fragments = _all_fragments(value)
    if not fragments:
        fragments = [fallback]
    unique: list[str] = []
    seen: set[str] = set()
    for fragment in fragments:
        key = fragment.casefold()
        if fragment and key not in seen:
            seen.add(key)
            unique.append(fragment)
    return unique


def _has_positive_evidence(value: str, *, source_kind: str) -> bool:
    normalized = " ".join(value.casefold().split())
    if _is_missing_evidence(normalized):
        return False
    if source_kind == "candidate" and _requirement_status(value) in {
        "explicit_not_required",
        "exclusion",
    }:
        return False
    informative = set(re.findall(r"[\w+#.-]+", normalized)) - {
        "expected",
        "location",
        "role",
        "search",
        "strategy",
        "title",
    }
    return any(token.strip(".-") for token in informative)
