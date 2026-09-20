"""Strict, read-only verification of an imported campaign graph."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from backend.applications.models import Application, ApplicationEvent
from backend.campaigns.graph_assets import verify_artifacts, verify_source_documents
from backend.campaigns.import_planner_types import PlannedCampaign
from backend.campaigns.models import Campaign, CampaignApplication
from backend.campaigns.service_helpers import get_safe_media_type, owner_scoped_uuid, to_json_safe
from backend.career.models import CandidateProfile
from backend.career.source_parsing import PreparedSourceDocument


def _same(actual: Any, expected: Any) -> bool:
    return bool(to_json_safe(actual) == to_json_safe(expected))


def _verify_application(
    db: Session,
    *,
    user_id: int,
    identity_scope: str,
    fingerprint: str,
    expected: Any,
) -> bool:
    app_id = owner_scoped_uuid(identity_scope, fingerprint, "application", expected.source_application_id)
    app = db.query(Application).filter(Application.id == app_id).first()
    if app is None:
        return False
    fields: tuple[tuple[Any, Any], ...] = (
        (app.user_id, user_id),
        (app.job_id, None),
        (app.scraped_job_id, None),
        (app.resume_version_id, None),
        (app.revision, expected.revision),
        (app.current_stage, expected.current_stage),
        (app.job_snapshot, expected.job_snapshot),
        (app.job_title, expected.job_title),
        (app.job_company, expected.job_company),
        (app.job_location, expected.job_location),
        (app.latest_event_at, expected.latest_event_at),
        (app.next_action_task_id, expected.next_action_task_id),
        (app.next_action_title, expected.next_action_title),
        (app.next_action_at, expected.next_action_at),
        (app.next_action_priority, expected.next_action_priority),
    )
    if any(not _same(actual, want) for actual, want in fields):
        return False

    expected_events = {event.id: event for event in expected.events}
    stored_events = {
        event.id: event
        for event in db.query(ApplicationEvent).filter(ApplicationEvent.application_id == app_id).all()
    }
    if set(stored_events) != set(expected_events):
        return False
    for event_id, expected_event in expected_events.items():
        actual = stored_events[event_id]
        event_fields: tuple[tuple[Any, Any], ...] = (
            (actual.application_id, app_id),
            (actual.event_type, expected_event.event_type),
            (actual.stage, expected_event.stage),
            (actual.occurred_at, expected_event.occurred_at),
            (actual.note, expected_event.note),
            (actual.payload, expected_event.payload),
            (actual.created_at, expected_event.created_at),
        )
        if any(not _same(value, want) for value, want in event_fields):
            return False
    return True


def _verify_link(
    db: Session,
    *,
    campaign_id: str,
    app_id: str,
    identity_scope: str,
    fingerprint: str,
    expected: Any,
) -> bool:
    link_id = owner_scoped_uuid(identity_scope, fingerprint, "campaign_app", expected.source_application_id)
    link = db.query(CampaignApplication).filter(CampaignApplication.id == link_id).first()
    if link is None:
        return False
    fields = (
        (link.campaign_id, campaign_id),
        (link.application_id, app_id),
        (link.source_application_id, expected.source_application_id),
        (link.source_order, expected.source_order),
        (link.source_status, expected.source.source_status),
        (link.priority, expected.source.priority),
        (link.platform, expected.source.platform),
        (link.category, expected.source.category),
        (link.outcome, expected.source.outcome),
        (link.found_at, expected.source.found_at),
        (link.applied_at, expected.source.applied_at),
        (link.follow_up_at, expected.source.follow_up_at),
        (link.last_update_at, expected.source.last_update_at),
        (link.tracker_record, expected.source.tracker_record),
        (link.provenance, expected.source.provenance),
    )
    return bool(not any(not _same(actual, want) for actual, want in fields))


def verify_campaign_graph(
    db: Session,
    campaign_id: str,
    user_id: int,
    identity_scope: str,
    fingerprint: str,
    planned: PlannedCampaign,
    summary_dict: dict[str, Any],
    prepared_source_docs: list[PreparedSourceDocument],
    *,
    campaign_name: str,
) -> bool:
    """Return true only when every expected owner-scoped graph value is intact."""
    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user_id).first()
        if campaign is None:
            return False
        fields = (
            (campaign.user_id, user_id),
            (campaign.name, campaign_name),
            (campaign.name_integrity, hashlib.sha256(campaign_name.encode("utf-8")).hexdigest()),
            (campaign.source_fingerprint, fingerprint),
            (campaign.tracker_sha256, planned.tracker_sha256),
            (campaign.summary, summary_dict),
            (campaign.created_at, planned.imported_at),
            (campaign.updated_at, planned.imported_at),
        )
        if any(not _same(actual, want) for actual, want in fields):
            return False
        profile = db.query(CandidateProfile).filter(CandidateProfile.user_id == user_id).first()
        if profile is None:
            return False
        expected_link_ids = {
            owner_scoped_uuid(identity_scope, fingerprint, "campaign_app", item.source_application_id)
            for item in planned.applications
        }
        actual_link_ids = {
            item.id
            for item in db.query(CampaignApplication).filter(CampaignApplication.campaign_id == campaign_id).all()
        }
        if actual_link_ids != expected_link_ids:
            return False
        for expected in planned.applications:
            app_id = owner_scoped_uuid(identity_scope, fingerprint, "application", expected.source_application_id)
            if not _verify_application(db, user_id=user_id, identity_scope=identity_scope, fingerprint=fingerprint, expected=expected):
                return False
            if not _verify_link(db, campaign_id=campaign_id, app_id=app_id, identity_scope=identity_scope, fingerprint=fingerprint, expected=expected):
                return False
        descriptors = {
            item.sha256: (item.display_name, get_safe_media_type(item.relative_path))
            for item in planned.artifacts
        }
        for item in prepared_source_docs:
            descriptors.setdefault(item.sha256, (item.original_name, item.media_type))
        if not verify_artifacts(db, campaign_id=campaign_id, profile_id=profile.id, identity_scope=identity_scope, fingerprint=fingerprint, planned=planned, prepared=prepared_source_docs):
            return False
        return verify_source_documents(
            db,
            profile=profile,
            identity_scope=identity_scope,
            fingerprint=fingerprint,
            prepared=prepared_source_docs,
            descriptors=descriptors,
        )
    except Exception:
        return False
