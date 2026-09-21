"""Pure, side-effect-free import planner for campaign workspace."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, cast

from backend.applications.schemas import (
    ApplicationTaskPriority,
    ApplicationTaskResponse,
    normalize_application_email,
)
from backend.applications.snapshots import sanitize_application_snapshot
from backend.campaigns.import_planner_types import (
    CampaignPlanError,
    PlannedApplication,
    PlannedCampaign,
    PlannedEvent,
    PlannedTask,
    build_stage_timeline,
    resolve_stage_path,
    to_noon_utc,
    validate_campaign_plan_lengths,
)
from backend.campaigns.parser_types import (
    ParsedApplication,
    ParsedCampaign,
    freeze_value,
)
from backend.campaigns.xlsx_cells import find_field
from backend.jobs.urls import UnsafeJobUrlError, normalize_job_url

__all__ = [
    "CampaignPlanError",
    "PlannedApplication",
    "PlannedCampaign",
    "PlannedEvent",
    "PlannedTask",
    "build_stage_timeline",
    "plan_campaign_import",
    "resolve_stage_path",
    "to_noon_utc",
    "validate_campaign_plan_lengths",
]


def _build_task(
    app: ParsedApplication, fingerprint: str, imported_at: datetime, identity_scope: str
) -> PlannedTask | None:
    sources = set(app.provenance.get("sources", ()))
    is_closed = (app.source_status or "").strip().lower() == "closed"
    is_dossier_only = "tracker" not in sources
    has_action = bool(app.next_action and app.next_action.strip())

    if is_closed or is_dossier_only or not has_action:
        return None

    action_text = app.next_action.strip()[:500] if app.next_action else ""
    priority_map: dict[str, ApplicationTaskPriority] = {
        "urgent": "urgent",
        "high": "high",
        "medium": "normal",
        "low": "low",
    }
    raw_p = (app.priority or "").strip().lower()
    task_priority = priority_map.get(raw_p, "normal")
    task_due = to_noon_utc(app.follow_up_at)
    task_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"urn:careeros:campaign:{identity_scope}:{fingerprint}:{app.source_application_id}:task"))

    task_response = ApplicationTaskResponse(
        id=task_id,
        title=action_text,
        status="pending",
        priority=task_priority,
        due_at=task_due,
        reminder_at=None,
        completed_at=None,
        revision=1,
        created_at=imported_at,
        updated_at=imported_at,
    )
    frozen_response = freeze_value(task_response.model_dump(mode="json"))

    task_event = PlannedEvent(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"urn:careeros:campaign:{identity_scope}:{fingerprint}:{app.source_application_id}:task_created")),
        event_type="task_created",
        stage=None,
        occurred_at=imported_at,
        note=action_text,
        payload=freeze_value({"schema_version": "1.0", "task": frozen_response}),
        created_at=imported_at,
    )

    return PlannedTask(
        id=task_id,
        title=action_text,
        status="pending",
        priority=task_priority,
        due_at=task_due,
        reminder_at=None,
        completed_at=None,
        revision=1,
        created_at=imported_at,
        updated_at=imported_at,
        response=frozen_response,
        event=task_event,
    )


def _build_snapshot(
    app: ParsedApplication,
    vacancies_by_id: Mapping[str, bytes],
) -> Mapping[str, Any]:
    clean_title = (app.title or "").strip()
    job_title = clean_title[:240] if clean_title else "Untitled role"

    clean_company = (app.company or "").strip()
    job_company = clean_company[:240] if clean_company else "Unknown company"
    job_loc = app.location.strip()[:500] if app.location and app.location.strip() else None

    # Description: dossier vacancy.md decoded as UTF-8 first, else Requirements Summary
    desc_raw: str | None = None
    if app.source_application_id in vacancies_by_id:
        try:
            desc_raw = vacancies_by_id[app.source_application_id].decode("utf-8")
        except UnicodeDecodeError:
            desc_raw = None
    if not desc_raw:
        req = app.tracker_record.get("Requirements Summary")
        desc_raw = str(req) if req is not None else None
    desc = desc_raw.strip()[:100000] if desc_raw and desc_raw.strip() else None

    # external_url prefers Job Posting URL, then generic URL
    ext_url: str | None = None
    for cand in (app.job_posting_url, app.url):
        if cand:
            try:
                ext_url = normalize_job_url(cand, required=False)
                if ext_url:
                    break
            except UnsafeJobUrlError:
                pass

    # application_url prefers Platform URL, then generic URL
    app_url: str | None = None
    for cand in (app.platform_url, app.url):
        if cand:
            try:
                app_url = normalize_job_url(cand, required=False)
                if app_url:
                    break
            except UnsafeJobUrlError:
                pass

    raw_email = find_field(app.tracker_record, ("contact email", "email"))
    app_email: str | None = None
    if raw_email:
        try:
            app_email = normalize_application_email(str(raw_email))
        except ValueError:
            app_email = None

    raw_workload = find_field(app.tracker_record, ("workplace type", "contract type", "workload"))
    workload = str(raw_workload).strip()[:120] if raw_workload and str(raw_workload).strip() else None

    pub_date = app.found_at.isoformat() if app.found_at else None
    platform = app.platform[:40] if app.platform else None
    job_id = app.source_application_id[:120]

    raw_snapshot: dict[str, Any] = {
        "title": job_title,
        "company": job_company,
        "platform_job_id": job_id,
    }
    if desc:
        raw_snapshot["description"] = desc
    if job_loc:
        raw_snapshot["location"] = job_loc
    if ext_url:
        raw_snapshot["external_url"] = ext_url
    if app_url:
        raw_snapshot["application_url"] = app_url
    if app_email:
        raw_snapshot["application_email"] = app_email
    if workload:
        raw_snapshot["workload"] = workload
    if pub_date:
        raw_snapshot["publication_date"] = pub_date
    if platform:
        raw_snapshot["platform"] = platform

    sanitized = sanitize_application_snapshot(
        raw_snapshot,
        quarantine_reason="manual_snapshot_has_no_model_analysis",
    )
    return cast(Mapping[str, Any], freeze_value(sanitized))


def plan_campaign_import(
    parsed: ParsedCampaign,
    imported_at: datetime,
    *,
    identity_scope: str,
    campaign_name: str = "Legacy application campaign",
) -> PlannedCampaign:
    """Plan campaign application imports without database or filesystem side effects."""
    if imported_at.tzinfo is None:
        raise CampaignPlanError("imported_at must be timezone-aware")
    if not identity_scope or not identity_scope.strip():
        raise CampaignPlanError("identity_scope must be a non-empty string")
    clean_scope = identity_scope.strip()
    imported_at_utc = imported_at.astimezone(timezone.utc)

    validate_campaign_plan_lengths(parsed, campaign_name)

    # Index vacancy artifacts by application ID
    vacancies_by_id: dict[str, bytes] = {}
    for art in parsed.artifacts:
        if art.source_application_id and (art.category == "vacancy" or art.relative_path.endswith("/vacancy.md")):
            vacancies_by_id[art.source_application_id] = art.raw_bytes

    planned_apps: list[PlannedApplication] = []
    for app in parsed.applications:
        task = _build_task(app, parsed.fingerprint, imported_at_utc, clean_scope)
        stage_path = resolve_stage_path(app)
        timeline = build_stage_timeline(
            app, stage_path, imported_at_utc, has_task=(task is not None)
        )

        events: list[PlannedEvent] = []
        for s, inst in zip(stage_path, timeline):
            ev_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"urn:careeros:campaign:{clean_scope}:{parsed.fingerprint}:{app.source_application_id}:stage:{s}"))
            events.append(
                PlannedEvent(
                    id=ev_id,
                    event_type="stage",
                    stage=s,
                    occurred_at=inst,
                    note=None,
                    payload=freeze_value({"import": True, "source_application_id": app.source_application_id}),
                    created_at=imported_at_utc,
                )
            )

        if task:
            events.append(task.event)

        rev = len(events)
        latest_at = events[-1].occurred_at
        curr_stage = stage_path[-1]

        snapshot = _build_snapshot(app, vacancies_by_id)

        planned_apps.append(
            PlannedApplication(
                source_application_id=app.source_application_id,
                source_order=app.source_order,
                current_stage=curr_stage,
                revision=rev,
                latest_event_at=latest_at,
                job_snapshot=snapshot,
                job_title=str(snapshot.get("title") or "Untitled role"),
                job_company=str(snapshot.get("company") or "Unknown company"),
                job_location=snapshot.get("location"),
                next_action_task_id=task.id if task else None,
                next_action_title=task.title if task else None,
                next_action_at=task.due_at if task else None,
                next_action_priority=task.priority if task else None,
                events=tuple(events),
                task=task,
                source=app,
            )
        )

    return PlannedCampaign(
        campaign_name=campaign_name,
        imported_at=imported_at_utc,
        identity_scope=clean_scope,
        fingerprint=parsed.fingerprint,
        tracker_sha256=parsed.tracker_sha256,
        sanitized_tracker_bytes=parsed.sanitized_tracker_bytes,
        sanitized_tracker_sha256=parsed.sanitized_tracker_sha256,
        applications=tuple(planned_apps),
        artifacts=parsed.artifacts,
        status_counts=parsed.status_counts,
        credentials_count=parsed.credentials_count,
        warnings=parsed.warnings,
        suggested_profile_name=parsed.suggested_profile_name,
    )
