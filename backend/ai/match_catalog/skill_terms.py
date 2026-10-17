"""Deterministic extraction of meaningful skill terms."""

from __future__ import annotations

import re

from .grammar_patterns import _CLAUSE_GRAMMAR_PRONOUN_PATTERN, _MODAL_ACTION_WORD_PATTERN
from .stopwords import _SKILL_STOPWORDS


def _skill_parse_text(value: str, *, modal_frame: bool = False) -> str:
    if not modal_frame:
        return value
    masked = _MODAL_ACTION_WORD_PATTERN.sub(
        lambda match: " " * len(match.group(0)),
        value,
    )
    return _CLAUSE_GRAMMAR_PRONOUN_PATTERN.sub(
        lambda match: " " * len(match.group(0)),
        masked,
    )


def _skill_term_mentions(
    value: str,
    *,
    modal_frame: bool = False,
) -> list[tuple[int, int, str]]:
    mentions: list[tuple[int, int, str]] = []
    parsed = _skill_parse_text(value, modal_frame=modal_frame)
    for token_match in re.finditer(r"[\w+#.-]+", parsed, re.UNICODE):
        token = token_match.group(0).strip(".-").casefold()
        if len(token) < 2 or token.isdigit() or token in _SKILL_STOPWORDS:
            continue
        components = [
            component
            for component in token.split("-")
            if len(component) >= 2 and not component.isdigit() and component not in _SKILL_STOPWORDS
        ]
        if len(components) < len(token.split("-")):
            mentions.extend(
                (token_match.start(), token_match.end(), component) for component in components
            )
        else:
            mentions.append((token_match.start(), token_match.end(), token))
    return mentions


def _skill_terms(value: str, *, modal_frame: bool = False) -> set[str]:
    return {term for _start, _end, term in _skill_term_mentions(value, modal_frame=modal_frame)}
