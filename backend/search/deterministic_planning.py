"""Deterministic search planning for the model-optional discovery workflow.

The planner deliberately uses only values the user has already entered or
confirmed on the local search profile.  It performs no inference, network
access or model lookup, which makes it safe to use as the primary recovery
path when the optional local runtime is unavailable.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from backend.services.search.query_contracts import (
    exact_query_fingerprint,
    normalize_domain,
    normalize_search_item,
)

_ROLE_SEPARATORS = re.compile(r"[,;/|\n]+")
_STRATEGY_SEPARATORS = re.compile(r"[,;/|\n]+")
_QUOTED_PHRASE = re.compile(r'["“”]([^"“”]{2,80})["“”]')
_WORD = re.compile(r"[\w+#.-]{2,}", flags=re.UNICODE)
_STRATEGY_STOPWORDS = {
    "about",
    "and",
    "avoid",
    "con",
    "cosa",
    "della",
    "delle",
    "focus",
    "focusing",
    "for",
    "für",
    "jobs",
    "looking",
    "mit",
    "on",
    "oder",
    "roles",
    "ruoli",
    "search",
    "senza",
    "the",
    "und",
    "with",
}


def _plain(value: Any, default: Any = None) -> Any:
    return value if isinstance(value, (str, int, bool, list, tuple, dict)) else default


def _clean_phrase(value: Any, *, maximum: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" \t.,;:|/")
    return text[:maximum].rstrip()


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        values: Iterable[Any] = _STRATEGY_SEPARATORS.split(value)
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        return []
    return [cleaned for item in values if (cleaned := _clean_phrase(item, maximum=80))]


def _role_candidates(profile_dict: dict[str, Any], profile: Any) -> list[str]:
    candidates: list[str] = []
    # ``role_description`` is entered directly by the user.  Do not fall back to
    # profile_normalized_* or profile_search_intent_*: both can be model-produced and
    # therefore are not confirmed search instructions.
    role_description = _clean_phrase(profile_dict.get("role_description"), maximum=500)
    if role_description:
        split_roles = [
            _clean_phrase(part)
            for part in _ROLE_SEPARATORS.split(role_description)
            if _clean_phrase(part)
        ]
        candidates.extend(split_roles or [role_description[:120].rstrip()])
    return candidates


def _keyword_candidates(profile_dict: dict[str, Any], profile: Any) -> list[str]:
    candidates: list[str] = []
    # The free-form strategy is also explicit user input.  In particular, never mine
    # normalized skills, transferable skills, CV text or model-derived intent here.
    strategy = _clean_phrase(profile_dict.get("search_strategy"), maximum=1000)
    candidates.extend(_clean_phrase(value, maximum=80) for value in _QUOTED_PHRASE.findall(strategy))
    for fragment in _STRATEGY_SEPARATORS.split(strategy):
        words = [word for word in _WORD.findall(fragment) if word.casefold() not in _STRATEGY_STOPWORDS]
        if 1 <= len(words) <= 3:
            candidates.append(" ".join(words))
    return [candidate for candidate in candidates if candidate]


def build_deterministic_search_plan(
    profile_dict: dict[str, Any],
    profile: Any,
    *,
    default_max_queries: int = 3,
    default_max_keywords: int = 2,
) -> list[dict[str, str]]:
    """Return a stable, executable plan without consulting a model.

    Only explicit, user-entered search instructions are used. Query limits are
    enforced independently for occupation and keyword searches and then by the
    overall profile limit. Invalid or duplicate candidates are discarded using
    the same canonical contract as model-generated plans.
    """

    raw_max = _plain(getattr(profile, "max_queries", None))
    max_queries = raw_max if isinstance(raw_max, int) and raw_max >= 0 else default_max_queries
    raw_occupation_max = _plain(getattr(profile, "max_occupation_queries", None))
    max_occupations = (
        raw_occupation_max
        if isinstance(raw_occupation_max, int) and raw_occupation_max >= 0
        else max_queries
    )
    raw_keyword_max = _plain(getattr(profile, "max_keyword_queries", None))
    max_keywords = (
        raw_keyword_max
        if isinstance(raw_keyword_max, int) and raw_keyword_max >= 0
        else default_max_keywords
    )
    if max_queries <= 0:
        return []

    preferred_domains = _plain(getattr(profile, "preferred_domains", None), []) or []
    domain = normalize_domain(preferred_domains[0] if preferred_domains else "")

    raw_candidates: list[dict[str, str]] = []
    raw_candidates.extend(
        {"query": value, "type": "occupation", "domain": domain, "language": "en"}
        for value in _role_candidates(profile_dict, profile)
    )
    raw_candidates.extend(
        {"query": value, "type": "keyword", "domain": domain, "language": "en"}
        for value in _keyword_candidates(profile_dict, profile)
    )

    result: list[dict[str, str]] = []
    seen: set[str] = set()
    occupation_count = 0
    keyword_count = 0
    for candidate in raw_candidates:
        normalized, _reason = normalize_search_item(candidate)
        if normalized is None:
            continue
        query_type = normalized.get("type")
        if query_type == "occupation" and occupation_count >= max_occupations:
            continue
        if query_type == "keyword" and keyword_count >= max_keywords:
            continue
        fingerprint = exact_query_fingerprint(normalized)
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(normalized)
        occupation_count += int(query_type == "occupation")
        keyword_count += int(query_type == "keyword")
        if len(result) >= max_queries:
            break
    return result
