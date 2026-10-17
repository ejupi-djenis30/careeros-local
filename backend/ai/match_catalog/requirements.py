"""Complete requirement summaries for candidate and job evidence."""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any

from .clause_types import _ClauseSegment
from .clauses import _anaphoric_reassertion, _positive_reassertion, _structured_clauses
from .grammar_patterns import _FORWARD_MODAL_MARKER, _PASSIVE_MODAL_MARKER
from .skill_terms import _skill_terms
from .value_patterns import (
    _CEFR_RANK,
    _LANGUAGE_ALIASES,
    _NUMBER_WORDS,
    _QUALIFICATION_PATTERNS,
    _YEARS_PATTERN,
)


def _years(value: str) -> list[int]:
    result: list[int] = []
    for match in _YEARS_PATTERN.finditer(value):
        raw = match.group("years").casefold()
        result.append(int(raw) if raw.isdigit() else _NUMBER_WORDS[raw])
    return result


def _languages(value: str) -> dict[str, int]:
    normalized = value.casefold()
    level_pattern = "|".join(
        re.escape(level) for level in sorted(_CEFR_RANK, key=len, reverse=True)
    )
    level_matches = list(re.finditer(rf"\b(?:{level_pattern})\b", normalized, re.IGNORECASE))
    result: dict[str, int] = {}
    for alias, canonical in _LANGUAGE_ALIASES.items():
        for language_match in re.finditer(rf"\b{re.escape(alias)}\b", normalized):
            nearest = min(
                level_matches,
                key=lambda level: min(
                    abs(level.start() - language_match.end()),
                    abs(language_match.start() - level.end()),
                ),
                default=None,
            )
            rank = _CEFR_RANK[nearest.group(0).casefold()] if nearest is not None else 0
            result[canonical] = max(result.get(canonical, 0), rank)
    return result


def _qualification_rank(value: str) -> int:
    return max(
        (rank for rank, pattern in _QUALIFICATION_PATTERNS if pattern.search(value)), default=0
    )


def _segment_skill_text(segment: _ClauseSegment) -> tuple[str, bool]:
    if segment.absence_scope:
        return segment.text, False
    if segment.explicit_status == "exclusion":
        return segment.text, True
    marker_start = segment.marker_start
    marker_end = segment.marker_end
    if segment.marker_direction == "forward" and marker_end is not None:
        scope = segment.text[marker_end:]
    elif segment.marker_direction == "backward" and marker_start is not None:
        scope = segment.text[:marker_start]
    else:
        scope = segment.text
    marker = (
        segment.text[marker_start:marker_end]
        if marker_start is not None and marker_end is not None
        else ""
    )
    modal_frame = bool(
        _FORWARD_MODAL_MARKER.fullmatch(marker) or _PASSIVE_MODAL_MARKER.fullmatch(marker)
    )
    modal_frame = modal_frame or segment.explicit_status == "exclusion"
    modal_frame = modal_frame or _positive_reassertion(segment.text)
    return scope, modal_frame


def _segment_skill_terms(segment: _ClauseSegment) -> set[str]:
    scope, modal_frame = _segment_skill_text(segment)
    return _skill_terms(scope, modal_frame=modal_frame)


def _required_value_groups(
    clauses: Sequence[_ClauseSegment],
    values_for: Callable[[_ClauseSegment], Collection[str]],
) -> list[list[str]]:
    all_groups: list[list[str]] = []
    group_start = 0
    boundaries = [
        *(
            index
            for index, clause in enumerate(clauses)
            if index > 0 and clause.connector == "adversative"
        ),
        len(clauses),
    ]
    for group_end in boundaries:
        local_groups: list[list[str]] = []
        chunk: list[str] = []
        chunk_has_alternative = False

        def flush_chunk() -> None:
            nonlocal chunk, chunk_has_alternative
            if not chunk:
                return
            unique = list(dict.fromkeys(chunk))
            if chunk_has_alternative:
                local_groups.append(sorted(unique))
            else:
                local_groups.extend([value] for value in unique)
            chunk = []
            chunk_has_alternative = False

        for clause in clauses[group_start:group_end]:
            if clause.status != "required" or clause.absence_scope:
                flush_chunk()
                continue
            values = sorted({str(value) for value in values_for(clause)})
            for value_index, value in enumerate(values):
                connector = clause.connector if value_index == 0 else "additive"
                if not chunk:
                    chunk = [value]
                    continue
                if connector == "alternative":
                    chunk.append(value)
                    chunk_has_alternative = True
                elif connector == "list":
                    chunk.append(value)
                else:
                    flush_chunk()
                    chunk = [value]
        flush_chunk()
        all_groups.extend(sorted(local_groups, key=lambda group: tuple(group)))
        group_start = group_end
    return all_groups


def _requirement_summary(
    dimensions: Mapping[str, str],
    *,
    source_kind: str,
    source_text: str | None = None,
) -> dict[str, Any]:
    clauses = _structured_clauses(
        source_text if source_text is not None else str(dimensions.get("skill") or "")
    )
    if source_kind == "candidate":
        observed_languages: dict[str, int] = {}
        for clause in clauses:
            if clause.status in {"explicit_not_required", "exclusion"}:
                continue
            for language, rank in _languages(clause.text).items():
                observed_languages[language] = max(observed_languages.get(language, 0), rank)
        skill_state: dict[str, bool] = {}
        pending_negative_terms: set[str] = set()
        for clause in clauses:
            status = clause.status
            terms = _segment_skill_terms(clause)
            if status in {"explicit_not_required", "exclusion"}:
                for term in terms:
                    skill_state[term] = False
                pending_negative_terms = terms
                continue
            if _positive_reassertion(clause.text):
                if _anaphoric_reassertion(clause.text):
                    terms = set(pending_negative_terms) if pending_negative_terms else set()
                if not terms and pending_negative_terms:
                    terms = set(pending_negative_terms)
            for term in terms:
                skill_state[term] = True
            pending_negative_terms = set()
        return {
            "observed_experience_years": max(
                (
                    year
                    for clause in clauses
                    if clause.status not in {"explicit_not_required", "exclusion"}
                    for year in _years(clause.text)
                ),
                default=None,
            ),
            "observed_languages": dict(sorted(observed_languages.items())),
            "observed_qualification_rank": max(
                (
                    _qualification_rank(clause.text)
                    for clause in clauses
                    if clause.status not in {"explicit_not_required", "exclusion"}
                ),
                default=0,
            ),
            "observed_skill_terms": sorted(
                term for term, positive in skill_state.items() if positive
            ),
            "negated_skill_terms": sorted(
                term for term, positive in skill_state.items() if not positive
            ),
        }

    required_skill_terms: set[str] = set()
    required_skill_groups: list[list[str]] = []
    preferred_skill_terms: set[str] = set()
    present_skill_terms: set[str] = set()
    excluded_skill_terms: set[str] = set()
    for clause in clauses:
        status = clause.status
        terms = _segment_skill_terms(clause)
        if status == "required":
            required_skill_terms.update(terms)
        elif status == "preferred":
            preferred_skill_terms.update(terms)
        elif status == "present":
            present_skill_terms.update(terms)
        elif status == "exclusion":
            excluded_skill_terms.update(terms)
    required_skill_groups.extend(_required_value_groups(clauses, _segment_skill_terms))
    required_languages: dict[str, int] = {}
    for clause in clauses:
        if clause.status != "required" or clause.absence_scope:
            continue
        for language, rank in _languages(clause.text).items():
            required_languages[language] = max(required_languages.get(language, 0), rank)
    required_language_groups = [
        {language: required_languages[language] for language in group}
        for group in _required_value_groups(
            clauses,
            lambda clause: _languages(clause.text),
        )
    ]
    required_years = [
        year
        for clause in clauses
        if clause.status == "required" and not clause.absence_scope
        for year in _years(clause.text)
    ]
    qualification_ranks = [
        _qualification_rank(clause.text)
        for clause in clauses
        if clause.status == "required" and not clause.absence_scope
    ]
    return {
        "excluded_skill_terms": sorted(excluded_skill_terms),
        "preferred_skill_terms": sorted(preferred_skill_terms),
        "present_skill_terms": sorted(present_skill_terms),
        "required_experience_years": max(required_years, default=None),
        "required_language_groups": required_language_groups,
        "required_languages": dict(sorted(required_languages.items())),
        "required_qualification_rank": max(qualification_ranks, default=0),
        "required_skill_groups": required_skill_groups,
        "required_skill_terms": sorted(required_skill_terms),
    }
