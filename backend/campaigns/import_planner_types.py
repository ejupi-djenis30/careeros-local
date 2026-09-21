"""Data types and preflight validation for campaign import planner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from backend.applications.schemas import (
    ApplicationTaskPriority,
)
from backend.campaigns.models import ALLOWED_ARTIFACT_CATEGORIES, XLSX_MAX_CELL_CHARS
from backend.campaigns.parser_types import (
    ParsedApplication,
    ParsedArtifact,
    ParsedCampaign,
)


class CampaignPlanError(ValueError):
    """Raised when campaign data violates planning validation or database constraints."""


def resolve_stage_path(app: ParsedApplication) -> list[str]:
    sources = set(app.provenance.get("sources", ()))
    if "tracker" not in sources:
        return ["saved", "preparing"]
    status = (app.source_status or "").strip().lower()
    if status == "saved":
        return ["saved"]
    if status == "preparing":
        return ["saved", "preparing"]
    if status == "applied":
        return ["saved", "preparing", "applied"]
    if status == "closed":
        return ["saved", "preparing", "applied", "archived"] if app.applied_at else ["saved", "archived"]
    return ["saved"]


def to_noon_utc(d: date | None) -> datetime | None:
    return datetime.combine(d, time(12, 0, 0), tzinfo=timezone.utc) if d else None


def build_stage_timeline(
    app: ParsedApplication,
    stages: list[str],
    imported_at: datetime,
    *,
    has_task: bool = False,
) -> list[datetime]:
    k = len(stages)
    max_instant = imported_at - timedelta(microseconds=1) if has_task else imported_at
    anchors: list[datetime | None] = []
    for s in stages:
        if s == "saved":
            anchors.append(to_noon_utc(app.found_at))
        elif s == "preparing":
            if "applied" in stages:
                anchors.append(None)
            else:
                anchors.append(to_noon_utc(app.last_update_at) or to_noon_utc(app.found_at))
        elif s == "applied":
            anchors.append(to_noon_utc(app.applied_at))
        elif s == "archived":
            anchors.append(
                to_noon_utc(app.last_update_at) or to_noon_utc(app.applied_at) or to_noon_utc(app.found_at)
            )
        else:
            anchors.append(None)

    capped: list[datetime | None] = [
        min(a, max_instant) if a is not None else None for a in anchors
    ]

    result = [max_instant] * k
    last_cand = capped[-1]
    result[-1] = last_cand if last_cand is not None else max_instant

    for i in range(k - 2, -1, -1):
        upper_bound = result[i + 1] - timedelta(microseconds=1)
        c = capped[i]
        result[i] = c if (c is not None and c <= upper_bound) else upper_bound

    return result


def validate_campaign_plan_lengths(parsed: ParsedCampaign, campaign_name: str) -> None:
    """Preflight check on max lengths before planning or writes; generic errors without echoing values."""
    if not campaign_name or not campaign_name.strip():
        raise CampaignPlanError("Preflight validation failed: campaign name must not be blank")
    if len(campaign_name) > 160:
        raise CampaignPlanError("Preflight validation failed: campaign name exceeds 160 characters")
    for app in parsed.applications:
        if not app.source_application_id or not app.source_application_id.strip():
            raise CampaignPlanError("Preflight validation failed: source ID must not be blank")
        if len(app.source_application_id) > 120:
            raise CampaignPlanError("Preflight validation failed: source ID exceeds 120 characters")
        if app.source_status and len(app.source_status) > 60:
            raise CampaignPlanError("Preflight validation failed: status exceeds 60 characters")
        if app.priority and len(app.priority) > 60:
            raise CampaignPlanError("Preflight validation failed: priority exceeds 60 characters")
        if app.platform and len(app.platform) > 120:
            raise CampaignPlanError("Preflight validation failed: platform exceeds 120 characters")
        if app.category and len(app.category) > 120:
            raise CampaignPlanError("Preflight validation failed: category exceeds 120 characters")
        if app.outcome and len(app.outcome) > 120:
            raise CampaignPlanError("Preflight validation failed: outcome exceeds 120 characters")
        if app.tracker_record:
            for val in app.tracker_record.values():
                if isinstance(val, str) and len(val) > XLSX_MAX_CELL_CHARS:
                    raise CampaignPlanError(
                        "Preflight validation failed: tracker record string value exceeds maximum length"
                    )
    for art in parsed.artifacts:
        if not art.relative_path or not art.relative_path.strip():
            raise CampaignPlanError("Preflight validation failed: relative_path must not be blank")
        if len(art.relative_path) > 500:
            raise CampaignPlanError("Preflight validation failed: relative_path exceeds 500 characters")
        if not art.display_name or not art.display_name.strip():
            raise CampaignPlanError("Preflight validation failed: display_name must not be blank")
        if len(art.display_name) > 255:
            raise CampaignPlanError("Preflight validation failed: display_name exceeds 255 characters")
        if not art.category or len(art.category) > 40 or art.category not in ALLOWED_ARTIFACT_CATEGORIES:
            raise CampaignPlanError("Preflight validation failed: invalid artifact category")


@dataclass(frozen=True, slots=True)
class PlannedEvent:
    id: str
    event_type: str
    stage: str | None
    occurred_at: datetime
    note: str | None
    payload: Mapping[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PlannedTask:
    id: str
    title: str
    status: str
    priority: ApplicationTaskPriority
    due_at: datetime | None
    reminder_at: datetime | None
    completed_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime
    response: Mapping[str, Any]
    event: PlannedEvent


@dataclass(frozen=True, slots=True)
class PlannedApplication:
    source_application_id: str
    source_order: int
    current_stage: str
    revision: int
    latest_event_at: datetime
    job_snapshot: Mapping[str, Any]
    job_title: str
    job_company: str
    job_location: str | None
    next_action_task_id: str | None
    next_action_title: str | None
    next_action_at: datetime | None
    next_action_priority: str | None
    events: tuple[PlannedEvent, ...]
    task: PlannedTask | None
    source: ParsedApplication


@dataclass(frozen=True, slots=True)
class PlannedCampaign:
    campaign_name: str
    imported_at: datetime
    identity_scope: str
    fingerprint: str
    tracker_sha256: str | None
    sanitized_tracker_bytes: bytes | None
    sanitized_tracker_sha256: str | None
    applications: tuple[PlannedApplication, ...]
    artifacts: tuple[ParsedArtifact, ...]
    status_counts: Mapping[str, int]
    credentials_count: int
    warnings: tuple[str, ...]
    suggested_profile_name: str | None
