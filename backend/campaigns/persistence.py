"""Database and publication persistence for a planned campaign import."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.applications.models import Application, ApplicationEvent
from backend.campaigns.asset_import import (
    publish_or_reuse_campaign_asset,
    publish_root_source_document,
)
from backend.campaigns.import_planner_types import PlannedCampaign
from backend.campaigns.models import Campaign, CampaignApplication, CampaignArtifact
from backend.campaigns.service_helpers import (
    owner_scoped_uuid,
    to_json_safe,
)
from backend.career.models import CandidateProfile, CareerAsset
from backend.career.source_parsing import PreparedSourceDocument


def persist_entities(
    db: Session,
    *,
    profile: CandidateProfile,
    user_id: int,
    identity_scope: str,
    planned: PlannedCampaign,
    campaign: Campaign,
    prepared_source_docs: list[PreparedSourceDocument],
    new_files: set[str],
    new_journals: list[str],
) -> None:
    """Persist one fully planned graph while the caller owns the transaction."""
    assets_by_sha: dict[str, CareerAsset] = {}
    for sha, art in {a.sha256: a for a in planned.artifacts}.items():
        assets_by_sha[sha] = publish_or_reuse_campaign_asset(
            db,
            profile_id=profile.id,
            raw_bytes=art.raw_bytes,
            sha256=sha,
            byte_size=art.byte_size,
            original_name=art.display_name,
            relative_path=art.relative_path,
            new_files=new_files,
            new_journals=new_journals,
        )
    for prep in prepared_source_docs:
        publish_root_source_document(
            db,
            profile_id=profile.id,
            identity_scope=identity_scope,
            fingerprint=planned.fingerprint,
            prep=prep,
            new_files=new_files,
            new_journals=new_journals,
        )
    app_id_by_source: dict[str, str] = {}
    for p_app in planned.applications:
        app_id = owner_scoped_uuid(identity_scope, planned.fingerprint, "application", p_app.source_application_id)
        app_id_by_source[p_app.source_application_id] = app_id
        db.add(Application(
            id=app_id,
            user_id=user_id,
            job_id=None,
            scraped_job_id=None,
            resume_version_id=None,
            revision=p_app.revision,
            current_stage=p_app.current_stage,
            job_snapshot=to_json_safe(p_app.job_snapshot),
            job_title=p_app.job_title[:240],
            job_company=p_app.job_company[:240],
            job_location=p_app.job_location[:500] if p_app.job_location else None,
            latest_event_at=p_app.latest_event_at,
            next_action_task_id=p_app.next_action_task_id,
            next_action_title=p_app.next_action_title[:500] if p_app.next_action_title else None,
            next_action_at=p_app.next_action_at,
            next_action_priority=p_app.next_action_priority,
        ))
        for event in p_app.events:
            db.add(ApplicationEvent(
                id=event.id,
                application_id=app_id,
                event_type=event.event_type,
                stage=event.stage,
                occurred_at=event.occurred_at,
                note=event.note,
                payload=to_json_safe(event.payload),
                created_at=event.created_at,
            ))
        db.add(CampaignApplication(
            id=owner_scoped_uuid(identity_scope, planned.fingerprint, "campaign_app", p_app.source_application_id),
            campaign_id=campaign.id,
            application_id=app_id,
            source_application_id=p_app.source_application_id[:120],
            source_order=p_app.source_order,
            source_status=p_app.source.source_status[:60] if p_app.source.source_status else None,
            priority=p_app.source.priority[:60] if p_app.source.priority else None,
            platform=p_app.source.platform[:120] if p_app.source.platform else None,
            category=p_app.source.category[:120] if p_app.source.category else None,
            outcome=p_app.source.outcome[:120] if p_app.source.outcome else None,
            found_at=p_app.source.found_at,
            applied_at=p_app.source.applied_at,
            follow_up_at=p_app.source.follow_up_at,
            last_update_at=p_app.source.last_update_at,
            tracker_record=to_json_safe(p_app.source.tracker_record),
            provenance=to_json_safe(p_app.source.provenance),
        ))
    for p_art in planned.artifacts:
        bound = app_id_by_source.get(p_art.source_application_id) if p_art.source_application_id else None
        db.add(CampaignArtifact(
            id=owner_scoped_uuid(identity_scope, planned.fingerprint, "artifact", p_art.relative_path),
            campaign_id=campaign.id,
            application_id=bound,
            asset_id=assets_by_sha[p_art.sha256].id,
            relative_path=p_art.relative_path[:500],
            display_name=p_art.display_name[:255],
            category=p_art.category[:40],
            source_order=p_art.source_order,
            created_at=planned.imported_at,
        ))
