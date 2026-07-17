from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, cast

from backend.career.models import CandidateProfile, CareerFact, CareerGoal
from backend.career.schemas import FactType
from backend.resumes.canvas import SECTION_TITLES, build_canvas
from backend.resumes.canvas_schemas import GenerationContext, ResumeCanvasDocument
from backend.resumes.schemas import ResumeSectionConfig, TemplateKind

FACT_LIMITS: dict[str, int] = {
    "experience": 24,
    "education": 12,
    "project": 24,
    "skill": 40,
    "language": 12,
    "certification": 20,
    "achievement": 24,
    "volunteering": 12,
    "publication": 20,
    "link": 10,
}
CHRONOLOGY_RESERVE = {"experience": 5, "education": 3}


@dataclass(frozen=True)
class GeneratedResume:
    canvas: ResumeCanvasDocument
    selected_fact_ids: list[str]
    section_config: ResumeSectionConfig
    generation_context: GenerationContext


def _goal_terms(goal: CareerGoal | None, target_snapshot: Mapping[str, Any] | None) -> set[str]:
    values: list[Any] = []
    if goal:
        payload = goal.payload or {}
        for key in (
            "target_roles",
            "target_industries",
            "target_locations",
            "target_seniority",
            "must_haves",
        ):
            values.extend(payload.get(key, []))
    if target_snapshot:
        values.extend(target_snapshot.values())
    terms: set[str] = set()
    for value in values:
        for term in str(value).casefold().replace("/", " ").replace(",", " ").split():
            if len(term) >= 3:
                terms.add(term)
    return terms


def _latest_date(payload: Mapping[str, Any]) -> int:
    candidates = (
        payload.get("end_date"),
        payload.get("start_date"),
        payload.get("issued_on"),
        payload.get("published_on"),
        payload.get("achieved_on"),
        payload.get("last_used_date"),
    )
    if payload.get("current"):
        return date.max.toordinal()
    for value in candidates:
        if not value:
            continue
        try:
            return date.fromisoformat(str(value)).toordinal()
        except ValueError:
            continue
    return 0


def _rank(fact: CareerFact, terms: set[str]) -> tuple[int, int, int, str]:
    haystack = json.dumps(fact.payload, ensure_ascii=False, sort_keys=True).casefold()
    matches = sum(1 for term in terms if term in haystack)
    return (-matches, -_latest_date(fact.payload), fact.position, fact.id)


def _select_group(kind: str, facts: list[CareerFact], terms: set[str]) -> list[CareerFact]:
    ranked = sorted(facts, key=lambda item: _rank(item, terms))
    limit = FACT_LIMITS[kind]
    if len(ranked) <= limit:
        return ranked

    selected: dict[str, CareerFact] = {}
    reserve = min(CHRONOLOGY_RESERVE.get(kind, 0), limit)
    if reserve:
        chronological = sorted(
            facts,
            key=lambda item: (-_latest_date(item.payload), item.position, item.id),
        )
        selected.update((fact.id, fact) for fact in chronological[:reserve])
    for fact in ranked:
        if len(selected) >= limit:
            break
        selected.setdefault(fact.id, fact)
    return sorted(selected.values(), key=lambda item: _rank(item, terms))


def generate_resume(
    profile: CandidateProfile,
    facts: Iterable[CareerFact],
    *,
    template_kind: TemplateKind,
    goal: CareerGoal | None = None,
    target_job_id: int | None = None,
    target_snapshot: Mapping[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> GeneratedResume:
    publishable = [
        fact
        for fact in facts
        if fact.archived_at is None and fact.verification_status == "confirmed"
    ]
    if not publishable:
        raise ValueError("The career profile has no confirmed facts for a resume")

    terms = _goal_terms(goal, target_snapshot)
    grouped: dict[str, list[CareerFact]] = {}
    for fact in publishable:
        grouped.setdefault(fact.fact_type, []).append(fact)
    ordered: list[CareerFact] = []
    order: list[FactType] = [
        cast(FactType, kind) for kind in SECTION_TITLES if grouped.get(kind)
    ]
    for kind in order:
        ordered.extend(_select_group(kind, grouped[kind], terms))

    config = ResumeSectionConfig(order=order)
    canvas = build_canvas(
        profile=profile,
        facts=ordered,
        template_kind=template_kind,
        section_config=config,
    )
    reason_codes = ["confirmed-facts", "bounded-fact-selection", "canonical-section-order"]
    if goal:
        reason_codes.append("career-goal-ranking")
    if target_snapshot:
        reason_codes.append("target-job-ranking")
    context = GenerationContext(
        mode="deterministic",
        generated_at=(generated_at or datetime.now(timezone.utc)).isoformat(),
        source_profile_revision=profile.revision,
        career_goal_id=goal.id if goal else None,
        target_job_id=target_job_id,
        target_snapshot=dict(target_snapshot or {}),
        reason_codes=reason_codes,
    )
    return GeneratedResume(
        canvas=canvas,
        selected_fact_ids=[fact.id for fact in ordered],
        section_config=config,
        generation_context=context,
    )
