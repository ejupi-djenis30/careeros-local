from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List

from backend.core.config import settings
from backend.services.search.query_contracts import sanitize_prompt_text
from backend.services.utils import clean_html_tags

_PROMPT_FRAGMENT_SPLIT_RE = re.compile(r"(?:\n+|(?<=[.!?;:])\s+)")
_PROMPT_BULLET_PREFIX_RE = re.compile(r"^(?:[-*•]|\d+[.)])\s*")
_PROMPT_PRIORITY_KEYWORDS = (
    "must",
    "required",
    "requirement",
    "experience",
    "language",
    "english",
    "german",
    "deutsch",
    "french",
    "italian",
    "cert",
    "license",
    "permit",
    "skill",
    "qualification",
    "degree",
    "education",
    "salary",
    "workload",
    "remote",
    "hybrid",
    "on-site",
    "onsite",
    "responsibil",
    "task",
    "contract",
)


def normalize_cache_text(value: Any, *, max_chars: int | None = None) -> str:
    text = sanitize_prompt_text(value, max_chars=max_chars)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_fingerprint_text(value: Any, *, max_chars: int | None = None) -> str:
    text = normalize_cache_text(value, max_chars=max_chars)
    return re.sub(r"\s+", " ", text).strip()


def _description_fragments(text: str) -> List[str]:
    fragments: List[str] = []
    for block in _PROMPT_FRAGMENT_SPLIT_RE.split(text):
        fragment = normalize_cache_text(_PROMPT_BULLET_PREFIX_RE.sub("", block))
        if len(fragment) < 16:
            continue
        fragments.append(fragment)
    return fragments


def _description_fragment_score(fragment: str) -> int:
    lowered = fragment.lower()
    score = 0
    for keyword in _PROMPT_PRIORITY_KEYWORDS:
        if keyword in lowered:
            score += 4
    if any(char.isdigit() for char in fragment):
        score += 2
    if _PROMPT_BULLET_PREFIX_RE.match(fragment):
        score += 1
    if 24 <= len(fragment) <= 220:
        score += 1
    return score


def compact_prompt_text(text: str, max_chars: int) -> str:
    cleaned = normalize_cache_text(
        clean_html_tags(text),
        max_chars=int(getattr(settings, "MAX_DESCRIPTION_CHARS", 64000) or 64000),
    )
    if not cleaned or len(cleaned) <= max_chars:
        return cleaned

    fragments = _description_fragments(cleaned)
    if not fragments:
        return cleaned[:max_chars].rstrip()

    max_fragments = max(4, int(getattr(settings, "PROMPT_COMPACTION_MAX_FRAGMENTS", 12) or 12))
    ranked = sorted(
        enumerate(fragments),
        key=lambda item: (-_description_fragment_score(item[1]), item[0]),
    )

    selected: List[str] = []
    selected_keys: set[str] = set()
    used_chars = 0

    def try_add(fragment: str) -> bool:
        nonlocal used_chars
        normalized = fragment.lower()
        if normalized in selected_keys:
            return False
        extra = len(fragment) + (1 if selected else 0)
        if selected and used_chars + extra > max_chars:
            return False
        if not selected and len(fragment) > max_chars:
            fragment = fragment[:max_chars].rstrip()
            extra = len(fragment)
        selected.append(fragment)
        selected_keys.add(normalized)
        used_chars += extra
        return True

    for _, fragment in ranked:
        if len(selected) >= max_fragments:
            break
        if _description_fragment_score(fragment) <= 0:
            continue
        try_add(fragment)

    for fragment in fragments:
        if len(selected) >= max_fragments or used_chars >= max_chars:
            break
        try_add(fragment)

    if not selected:
        return cleaned[:max_chars].rstrip()

    return "\n".join(selected)[:max_chars].rstrip()


def build_profile_normalization_fingerprint(
    cv_content: str,
    role_description: str,
    search_strategy: str,
) -> str:
    payload = {
        "cv": _normalize_fingerprint_text(cv_content, max_chars=12000),
        "role": _normalize_fingerprint_text(role_description, max_chars=4000),
        "strategy": _normalize_fingerprint_text(search_strategy, max_chars=1200),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def build_scraped_job_content_fingerprint(
    *,
    title: str,
    company: str,
    location: str,
    workload: str,
    description: str,
) -> str:
    payload = {
        "title": _normalize_fingerprint_text(title, max_chars=240),
        "company": _normalize_fingerprint_text(company, max_chars=160),
        "location": _normalize_fingerprint_text(location, max_chars=160),
        "workload": _normalize_fingerprint_text(workload, max_chars=80),
        "description": _normalize_fingerprint_text(description, max_chars=12000),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _render_list(values: Iterable[Any], *, limit: int) -> str:
    rendered: List[str] = []
    for value in values:
        text = normalize_cache_text(value, max_chars=80)
        if not text:
            continue
        rendered.append(text)
        if len(rendered) >= limit:
            break
    return ", ".join(rendered)


def build_profile_match_snapshot(
    *,
    role_description: str,
    search_strategy: str,
    cv_summary: str,
    profile_normalization: Dict[str, Any] | None,
    max_chars: int,
) -> str:
    profile_norm = profile_normalization or {}
    lines: List[str] = []

    role_line = normalize_cache_text(role_description, max_chars=220)
    if role_line:
        lines.append(f"Target role: {role_line}")

    strategy_line = normalize_cache_text(search_strategy, max_chars=220)
    if strategy_line:
        lines.append(f"Strategy: {strategy_line}")

    if profile_norm:
        candidate_bits = [
            f"CV domain={profile_norm.get('domain') or 'unknown'}",
            f"role={profile_norm.get('role_family') or 'unknown'}",
            f"role_type={profile_norm.get('role_type') or 'unknown'}",
            f"seniority={profile_norm.get('seniority') or 'unknown'}",
        ]
        if profile_norm.get("experience_years") is not None:
            candidate_bits.append(f"experience={profile_norm.get('experience_years')}y")
        if profile_norm.get("qualification_level"):
            candidate_bits.append(f"qualification={profile_norm.get('qualification_level')}")
        lines.append("Candidate: " + " | ".join(candidate_bits))

        languages = profile_norm.get("languages") or []
        rendered_languages = []
        for item in languages[:4]:
            if isinstance(item, dict):
                code = normalize_cache_text(item.get("code"), max_chars=10)
                level = normalize_cache_text(item.get("level"), max_chars=10)
                if code:
                    rendered_languages.append(f"{code}:{level}" if level else code)
        if rendered_languages:
            lines.append("Languages: " + ", ".join(rendered_languages))

        skills = _render_list(profile_norm.get("skills") or [], limit=10)
        if skills:
            lines.append(f"Skills: {skills}")

        transferable = _render_list(profile_norm.get("transferable_skills") or [], limit=6)
        if transferable:
            lines.append(f"Transferable: {transferable}")

        intent_bits = [
            f"domain={profile_norm.get('intent_domain') or profile_norm.get('domain') or 'unknown'}",
            f"role={profile_norm.get('intent_role_family') or profile_norm.get('role_family') or 'unknown'}",
            f"role_type={profile_norm.get('intent_role_type') or profile_norm.get('role_type') or 'unknown'}",
        ]
        seniority_min = profile_norm.get("intent_seniority_min") or profile_norm.get(
            "intent_seniority"
        )
        seniority_max = profile_norm.get("intent_seniority_max") or profile_norm.get(
            "intent_seniority"
        )
        if seniority_min or seniority_max:
            intent_bits.append(f"seniority={seniority_min or '?'}-{seniority_max or '?'}")
        if profile_norm.get("intent_qualification_level"):
            intent_bits.append(f"qualification={profile_norm.get('intent_qualification_level')}")
        intent_bits.append(
            "open_to_unrelated=" + ("yes" if profile_norm.get("open_to_unrelated") else "no")
        )
        lines.append("Intent: " + " | ".join(intent_bits))

        intent_skills = _render_list(profile_norm.get("intent_skills") or [], limit=8)
        if intent_skills:
            lines.append(f"Intent skills: {intent_skills}")

        dealbreakers = _render_list(profile_norm.get("dealbreakers") or [], limit=6)
        if dealbreakers:
            lines.append(f"Dealbreakers: {dealbreakers}")

    summary_budget = max(120, min(max_chars // 2, 420))
    summary_text = normalize_cache_text(cv_summary, max_chars=summary_budget)
    if summary_text:
        lines.append("CV summary:")
        lines.append(summary_text)

    snapshot = "\n".join(line for line in lines if line).strip()
    return normalize_cache_text(snapshot, max_chars=max_chars)
