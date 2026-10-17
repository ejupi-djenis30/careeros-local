"""Clause segmentation, markers and requirement status propagation."""

from __future__ import annotations

import re

from .clause_types import _ClauseSegment, _ConnectorKind, _MarkerDirection
from .constants import _FRAGMENT_SPLIT, _REQUIREMENT_STATUS_PATTERNS
from .grammar_patterns import (
    _CLASSIFICATION_CONTRACTIONS,
    _FORWARD_MODAL_MARKER,
    _PASSIVE_MODAL_MARKER,
    _REASSERTION_GRAMMARS,
    _STRUCTURAL_CONNECTOR_PATTERN,
    _STRUCTURED_EXCLUSION_GRAMMARS,
)
from .skill_terms import _skill_terms
from .value_patterns import _LANGUAGE_ALIAS_PATTERN, _QUALIFICATION_PATTERNS, _YEARS_PATTERN


def _classification_text(value: str) -> str:
    normalized = value.replace("’", "'").replace("‘", "'")
    for pattern, replacement in _CLASSIFICATION_CONTRACTIONS:
        normalized = pattern.sub(replacement, normalized)
    return normalized


def _connector_kind(match: re.Match[str]) -> _ConnectorKind:
    if match.lastgroup == "additive_correlative":
        return "additive"
    if match.lastgroup == "alternative":
        return "alternative"
    if match.lastgroup == "scoped_absence":
        return "scoped_absence"
    if match.lastgroup == "adversative":
        return "adversative"
    if match.lastgroup == "additive":
        return "additive"
    return "list"


def _raw_clause_segments(sentence: str) -> list[_ClauseSegment]:
    segments: list[_ClauseSegment] = []
    cursor = 0
    pending_connector: _ConnectorKind = "start"
    pending_text = ""
    for match in _STRUCTURAL_CONNECTOR_PATTERN.finditer(sentence):
        chunk = sentence[cursor : match.start()].strip(" ,-;/")
        if chunk:
            segments.append(
                _ClauseSegment(
                    text=chunk,
                    connector=pending_connector,
                    connector_text=pending_text,
                )
            )
        pending_connector = _connector_kind(match)
        pending_text = match.group(0).strip(" ,;/")
        cursor = match.end()
    tail = sentence[cursor:].strip(" ,-;/")
    if tail:
        segments.append(
            _ClauseSegment(
                text=tail,
                connector=pending_connector,
                connector_text=pending_text,
            )
        )
    return segments


def _has_requirement_subject(value: str) -> bool:
    return bool(
        _skill_terms(value)
        or _LANGUAGE_ALIAS_PATTERN.search(value)
        or _YEARS_PATTERN.search(value)
        or any(pattern.search(value) for _rank, pattern in _QUALIFICATION_PATTERNS)
    )


def _marker_direction(
    value: str,
    status: str,
    match: re.Match[str],
) -> _MarkerDirection:
    if status == "exclusion":
        return "local"
    marker = match.group(0)
    if status == "required" and _PASSIVE_MODAL_MARKER.fullmatch(marker):
        return "both"
    if status == "required" and _FORWARD_MODAL_MARKER.fullmatch(marker):
        return "forward"
    left_has_subject = _has_requirement_subject(value[: match.start()])
    right_has_subject = _has_requirement_subject(value[match.end() :])
    if right_has_subject and not left_has_subject:
        return "forward"
    if left_has_subject and not right_has_subject:
        return "backward"
    if match.start() <= len(value) - len(value.lstrip()) + 1 and right_has_subject:
        return "forward"
    return "local"


def _annotate_explicit_status(segment: _ClauseSegment) -> None:
    normalized = _classification_text(segment.text)
    structured_exclusion = next(
        (
            match
            for pattern in _STRUCTURED_EXCLUSION_GRAMMARS
            if (match := pattern.search(normalized)) is not None
        ),
        None,
    )
    if structured_exclusion is not None:
        segment.explicit_status = "exclusion"
        segment.marker_direction = "local"
        segment.marker_start = structured_exclusion.start()
        segment.marker_end = structured_exclusion.end()
        return
    for status, pattern in _REQUIREMENT_STATUS_PATTERNS:
        match = pattern.search(normalized)
        if match is None:
            continue
        segment.explicit_status = status
        segment.marker_direction = _marker_direction(normalized, status, match)
        segment.marker_start = match.start()
        segment.marker_end = match.end()
        return


def _classify_clause_commas(segments: list[_ClauseSegment]) -> None:
    for index in range(1, len(segments)):
        segment = segments[index]
        if segment.connector != "list":
            continue
        previous = segments[index - 1]
        if previous.explicit_status is not None and previous.marker_direction in {
            "backward",
            "local",
        }:
            segment.connector = "adversative"


def _apply_absence_scope(segments: list[_ClauseSegment]) -> None:
    absence_active = False
    for segment in segments:
        if segment.connector in {"start", "adversative"}:
            absence_active = False
        if segment.connector == "scoped_absence":
            absence_active = True
        segment.absence_scope = absence_active


def _apply_status_propagation(segments: list[_ClauseSegment]) -> None:
    group_start = 0
    for group_end in [
        *(
            index
            for index, segment in enumerate(segments)
            if index > 0 and segment.connector == "adversative"
        ),
        len(segments),
    ]:
        group = segments[group_start:group_end]
        explicit_statuses = [
            segment.explicit_status for segment in group if segment.explicit_status is not None
        ]
        for segment in group:
            if segment.explicit_status is not None or not explicit_statuses:
                continue
            unique_statuses = set(explicit_statuses)
            if len(unique_statuses) == 1:
                segment.inherited_status = explicit_statuses[0]
        group_start = group_end


def _structured_clauses(value: str) -> list[_ClauseSegment]:
    clauses: list[_ClauseSegment] = []
    for sentence in _FRAGMENT_SPLIT.split(value):
        normalized = " ".join(sentence.split())
        if not normalized:
            continue
        sentence_segments = _raw_clause_segments(normalized)
        for segment in sentence_segments:
            _annotate_explicit_status(segment)
        _classify_clause_commas(sentence_segments)
        _apply_absence_scope(sentence_segments)
        _apply_status_propagation(sentence_segments)
        clauses.extend(sentence_segments)
    return clauses


def _positive_reassertion(value: str) -> bool:
    normalized = _classification_text(value)
    return any(positive.search(normalized) for positive, _anaphoric in _REASSERTION_GRAMMARS)


def _anaphoric_reassertion(value: str) -> bool:
    normalized = _classification_text(value)
    return any(anaphoric.search(normalized) for _positive, anaphoric in _REASSERTION_GRAMMARS)
