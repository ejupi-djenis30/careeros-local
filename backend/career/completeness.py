from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProfileIssue(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    fact_ids: list[str] = Field(default_factory=list)
    goal_ids: list[str] = Field(default_factory=list)


class FactEvidenceState(BaseModel):
    fact_id: str
    state: Literal["documented", "linked", "confirmed", "traceable", "missing"]
    evidence_fact_ids: list[str] = Field(default_factory=list)


class ProfileAnalysis(BaseModel):
    completeness_score: int = Field(ge=0, le=100)
    section_scores: dict[str, int]
    missing_sections: list[str]
    evidence: list[FactEvidenceState]
    issues: list[ProfileIssue]


SECTION_WEIGHTS = {
    "identity": 15,
    "experience": 20,
    "skills": 15,
    "education": 10,
    "achievements": 10,
    "projects": 10,
    "credentials_activities": 5,
    "preferences": 5,
    "goals": 10,
}


def _value(item: Any, name: str, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _payload(item: Any) -> dict[str, Any]:
    value = _value(item, "payload", {})
    return value if isinstance(value, dict) else {}


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _fact_id(fact: Any, index: int) -> str:
    return str(_value(fact, "id") or f"unsaved-{index}")


def _fact_score(facts: list[Any], *, rich_fields: tuple[str, ...] = ()) -> int:
    if not facts:
        return 0
    confirmed = sum(1 for item in facts if _value(item, "verification_status") == "confirmed")
    rich = sum(1 for item in facts if any(_payload(item).get(field) for field in rich_fields))
    score = 50 + round(25 * confirmed / len(facts))
    if rich_fields:
        score += round(25 * rich / len(facts))
    else:
        score += 25
    return int(min(100, score))


def _identity_score(profile: Any) -> int:
    location = _value(profile, "location", {}) or {}
    checks = [
        _value(profile, "display_name"),
        _value(profile, "headline"),
        _value(profile, "summary"),
        _value(profile, "email") or _value(profile, "phone"),
        location.get("name") or location.get("city") or location.get("country"),
    ]
    return round(100 * sum(bool(item) for item in checks) / len(checks))


def _preference_score(profile: Any) -> int:
    preferences = _value(profile, "preferences", {}) or {}
    checks = [
        preferences.get("target_roles"),
        preferences.get("target_industries") or preferences.get("preferred_locations"),
        preferences.get("preferred_work_modes") or preferences.get("remote_only"),
        preferences.get("salary") or preferences.get("salary_min_chf"),
    ]
    return round(100 * sum(bool(item) for item in checks) / len(checks))


def _goal_score(goals: list[Any]) -> int:
    if not goals:
        return 0
    primary = next((goal for goal in goals if _value(goal, "is_primary", False)), goals[0])
    payload = _payload(primary)
    checks = [
        _value(primary, "is_primary", False),
        payload.get("target_roles"),
        payload.get("target_date"),
        payload.get("success_criteria"),
        payload.get("milestones"),
        payload.get("actions"),
    ]
    return round(100 * sum(bool(item) for item in checks) / len(checks))


def _evidence(facts: list[Any]) -> list[FactEvidenceState]:
    result: list[FactEvidenceState] = []
    for index, fact in enumerate(facts):
        payload = _payload(fact)
        linked = [str(item) for item in payload.get("evidence_fact_ids", [])]
        state: Literal["documented", "linked", "confirmed", "traceable", "missing"]
        if _value(fact, "source_document_id"):
            state = "documented"
        elif linked:
            state = "linked"
        elif _value(fact, "verification_status") == "confirmed":
            state = "confirmed"
        elif _value(fact, "source_locator"):
            state = "traceable"
        else:
            state = "missing"
        result.append(
            FactEvidenceState(
                fact_id=_fact_id(fact, index),
                state=state,
                evidence_fact_ids=linked,
            )
        )
    return result


def _overlap_issues(facts: list[Any]) -> list[ProfileIssue]:
    employment: list[tuple[str, date, date]] = []
    primary_types = {"permanent", "temporary", "internship", "apprenticeship"}
    for index, fact in enumerate(facts):
        if _value(fact, "fact_type") != "experience":
            continue
        payload = _payload(fact)
        if payload.get("employment_type") not in primary_types:
            continue
        start = _parse_date(payload.get("start_date"))
        if start is None:
            continue
        end = _parse_date(payload.get("end_date")) or date.max
        employment.append((_fact_id(fact, index), start, end))
    issues: list[ProfileIssue] = []
    for position, (left_id, left_start, left_end) in enumerate(employment):
        for right_id, right_start, right_end in employment[position + 1 :]:
            if max(left_start, right_start) <= min(left_end, right_end):
                issues.append(
                    ProfileIssue(
                        code="overlapping_primary_employment",
                        severity="warning",
                        message="Two primary employment periods overlap; verify the dates or contract type.",
                        fact_ids=[left_id, right_id],
                    )
                )
    return issues


def _future_date_issues(facts: list[Any], reference_date: date) -> list[ProfileIssue]:
    date_fields: dict[str, tuple[str, ...]] = {
        "achievement": ("achieved_on",),
        "award": ("awarded_on",),
        "certification": ("issued_on",),
        "publication": ("published_on",),
    }
    issues: list[ProfileIssue] = []
    for index, fact in enumerate(facts):
        for field in date_fields.get(str(_value(fact, "fact_type") or ""), ()):
            value = _parse_date(_payload(fact).get(field))
            if value and value > reference_date:
                issues.append(
                    ProfileIssue(
                        code="future_historical_date",
                        severity="warning",
                        message="A historical career event has a future date.",
                        fact_ids=[_fact_id(fact, index)],
                    )
                )
    return issues


def _duplicate_issues(facts: list[Any]) -> list[ProfileIssue]:
    seen: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    key_fields = {
        "experience": ("role", "organization"),
        "education": ("qualification", "institution"),
        "project": ("name", "organization"),
        "skill": ("name", "category"),
        "achievement": ("title", "context"),
    }
    for index, fact in enumerate(facts):
        fact_type = str(_value(fact, "fact_type", ""))
        fields = key_fields.get(fact_type)
        if not fields:
            continue
        payload = _payload(fact)
        values = tuple(str(payload.get(field, "")).strip().casefold() for field in fields)
        if values[0]:
            key = (fact_type, values[0], values[1])
            seen[key].append(_fact_id(fact, index))
    return [
        ProfileIssue(
            code="possible_duplicate_fact",
            severity="warning",
            message="Career facts appear to describe the same item.",
            fact_ids=fact_ids,
        )
        for fact_ids in seen.values()
        if len(fact_ids) > 1
    ]


def _section_scores(profile: Any) -> tuple[list[Any], dict[str, int]]:
    facts = list(_value(profile, "facts", []) or [])
    goals = list(_value(profile, "goals", []) or [])
    by_type: dict[str, list[Any]] = defaultdict(list)
    for fact in facts:
        by_type[str(_value(fact, "fact_type"))].append(fact)

    return facts, {
        "identity": _identity_score(profile),
        "experience": _fact_score(
            by_type["experience"], rich_fields=("achievements", "metrics", "description")
        ),
        "skills": _fact_score(by_type["skill"], rich_fields=("evidence_fact_ids",)),
        "education": _fact_score(by_type["education"], rich_fields=("field", "description")),
        "achievements": _fact_score(
            by_type["achievement"], rich_fields=("metric_value", "details", "description")
        ),
        "projects": _fact_score(
            by_type["project"], rich_fields=("achievements", "description", "url")
        ),
        "credentials_activities": _fact_score(
            [
                fact
                for kind in (
                    "certification",
                    "language",
                    "award",
                    "membership",
                    "volunteering",
                    "publication",
                    "portfolio",
                )
                for fact in by_type[kind]
            ]
        ),
        "preferences": _preference_score(profile),
        "goals": _goal_score(goals),
    }


def _weighted_completeness_score(sections: dict[str, int]) -> int:
    return round(sum(sections[name] * weight for name, weight in SECTION_WEIGHTS.items()) / 100)


def calculate_completeness_score(profile: Any) -> int:
    """Return the profile score without constructing evidence and issue models."""
    _facts, sections = _section_scores(profile)
    return _weighted_completeness_score(sections)


def analyze_profile(profile: Any, *, reference_date: date | None = None) -> ProfileAnalysis:
    facts, sections = _section_scores(profile)
    completeness_score = _weighted_completeness_score(sections)
    evidence = _evidence(facts)
    issues = _overlap_issues(facts)
    issues.extend(_future_date_issues(facts, reference_date or date.today()))
    issues.extend(_duplicate_issues(facts))
    for item in evidence:
        if item.state == "missing":
            issues.append(
                ProfileIssue(
                    code="missing_evidence",
                    severity="info",
                    message="A draft fact has no linked or documented evidence.",
                    fact_ids=[item.fact_id],
                )
            )
    issues.sort(key=lambda item: (item.severity, item.code, item.fact_ids))
    return ProfileAnalysis(
        completeness_score=completeness_score,
        section_scores=sections,
        missing_sections=[name for name, score in sections.items() if score == 0],
        evidence=evidence,
        issues=issues,
    )
