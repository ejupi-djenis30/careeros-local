"""Owner-scoped read models for the campaign HTTP API."""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.applications.models import Application
from backend.campaigns.models import Campaign, CampaignApplication, CampaignArtifact
from backend.campaigns.service_helpers import to_json_safe
from backend.career.models import CandidateProfile, CareerAsset
from backend.core.config import settings
from backend.storage.atomic import read_verified


class CampaignApiNotFound(LookupError):
    """A campaign resource is absent or belongs to another account."""


class CampaignApiIntegrityError(ValueError):
    """A persisted campaign asset failed fail-closed verification."""


def _campaign(db: Session, user_id: int, campaign_id: str) -> Campaign:
    row = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.user_id == user_id)
        .first()
    )
    if row is None:
        raise CampaignApiNotFound
    return row


def _summary(campaign: Campaign) -> dict[str, Any]:
    return {
        "id": campaign.id,
        "name": campaign.name,
        "source_fingerprint": campaign.source_fingerprint,
        "tracker_sha256": campaign.tracker_sha256,
        "summary": campaign.summary,
        "summary_scope": "import_snapshot",
        "created_at": campaign.created_at.isoformat(),
        "updated_at": campaign.updated_at.isoformat(),
    }


def list_campaigns(db: Session, user_id: int) -> list[dict[str, Any]]:
    """Return only owned aggregate campaign metadata."""
    rows = (
        db.query(Campaign)
        .filter(Campaign.user_id == user_id)
        .order_by(Campaign.created_at.desc(), Campaign.id.asc())
        .all()
    )
    return [_summary(row) for row in rows]


def _application_projection(link: CampaignApplication) -> dict[str, Any]:
    app = link.application
    return {
        "id": app.id,
        "source_application_id": link.source_application_id,
        "title": app.job_title,
        "company": app.job_company,
        "location": app.job_location,
        "revision": app.revision,
        "stage": app.current_stage,
        "priority": link.priority,
        "platform": link.platform,
        "category": link.category,
        "updated_at": app.updated_at.isoformat(),
    }


def campaign_detail(
    db: Session,
    user_id: int,
    campaign_id: str,
    *,
    query: str | None,
    stage: str | None,
    priority: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    campaign = _campaign(db, user_id, campaign_id)
    base = (
        db.query(CampaignApplication)
        .join(CampaignApplication.application)
        .filter(
            CampaignApplication.campaign_id == campaign.id,
            CampaignApplication.application.has(user_id=user_id),
        )
    )
    total = base.count()
    live_stage_counts = {
        stage: count
        for stage, count in (
            db.query(Application.current_stage, func.count(Application.id))
            .join(CampaignApplication, CampaignApplication.application_id == Application.id)
            .filter(
                CampaignApplication.campaign_id == campaign.id,
                Application.user_id == user_id,
            )
            .group_by(Application.current_stage)
            .all()
        )
    }
    if query:
        needle = f"%{query.strip().lower()}%"
        base = base.filter(
            or_(
                CampaignApplication.source_application_id.ilike(needle),
                Application.job_title.ilike(needle),
                Application.job_company.ilike(needle),
                CampaignApplication.platform.ilike(needle),
                CampaignApplication.category.ilike(needle),
            )
        )
    if stage:
        base = base.filter(CampaignApplication.application.has(current_stage=stage))
    if priority:
        base = base.filter(CampaignApplication.priority == priority)
    filtered = base.count()
    rows = (
        base.order_by(CampaignApplication.source_order.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        **_summary(campaign),
        "total_application_count": total,
        "live_stage_counts": live_stage_counts,
        "filtered_application_count": filtered,
        "offset": offset,
        "limit": limit,
        "applications": [_application_projection(row) for row in rows],
    }


def application_context(db: Session, user_id: int, application_id: str) -> dict[str, Any]:
    row = (
        db.query(CampaignApplication)
        .join(Campaign, Campaign.id == CampaignApplication.campaign_id)
        .join(Application, Application.id == CampaignApplication.application_id)
        .filter(
            Campaign.user_id == user_id,
            CampaignApplication.application_id == application_id,
            Application.user_id == user_id,
        )
        .first()
    )
    if row is None:
        raise CampaignApiNotFound
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    artifacts = (
        db.query(CampaignArtifact, CareerAsset)
        .join(CareerAsset, CareerAsset.id == CampaignArtifact.asset_id)
        .join(CandidateProfile, CandidateProfile.id == CareerAsset.profile_id)
        .filter(
            CampaignArtifact.campaign_id == row.campaign_id,
            or_(
                CampaignArtifact.application_id == application_id,
                CampaignArtifact.application_id.is_(None),
            ),
            CandidateProfile.user_id == user_id,
        )
        .order_by(CampaignArtifact.source_order.asc())
        .all()
    )
    for artifact, asset in artifacts:
        groups[artifact.category].append({
            "id": artifact.id,
            "display_name": artifact.display_name,
            "category": artifact.category,
            "media_type": asset.media_type,
            "byte_size": asset.byte_size,
            "download_url": f"/api/v1/campaigns/{row.campaign_id}/artifacts/{artifact.id}/download",
        })
    return {
        "campaign_id": row.campaign_id,
        "campaign_name": row.campaign.name,
        "application_id": row.application_id,
        "source_application_id": row.source_application_id,
        "source_status": row.source_status,
        "priority": row.priority,
        "platform": row.platform,
        "category": row.category,
        "outcome": row.outcome,
        "found_at": to_json_safe(row.found_at),
        "applied_at": to_json_safe(row.applied_at),
        "follow_up_at": to_json_safe(row.follow_up_at),
        "last_update_at": to_json_safe(row.last_update_at),
        "tracker_record": row.tracker_record,
        "provenance": row.provenance,
        "artifact_groups": dict(groups),
    }


def download_artifact(
    db: Session,
    user_id: int,
    campaign_id: str,
    artifact_id: str,
) -> tuple[bytes, str, str, str]:
    row = (
        db.query(CampaignArtifact, CareerAsset)
        .join(Campaign, Campaign.id == CampaignArtifact.campaign_id)
        .join(CareerAsset, CareerAsset.id == CampaignArtifact.asset_id)
        .join(CandidateProfile, CandidateProfile.id == CareerAsset.profile_id)
        .filter(
            Campaign.id == campaign_id,
            Campaign.user_id == user_id,
            CampaignArtifact.id == artifact_id,
            CandidateProfile.user_id == user_id,
        )
        .first()
    )
    if row is None:
        raise CampaignApiNotFound
    artifact, asset = row
    expected_path = f"assets/campaign/{asset.sha256[:2]}/{asset.sha256}"
    name = artifact.display_name
    rel_basename = PurePosixPath(artifact.relative_path).name
    if (
        asset.storage_path != expected_path
        or not isinstance(name, str)
        or not name
        or name != rel_basename
        or not unicodedata.is_normalized("NFC", name)
        or "/" in name
        or "\\" in name
        or ":" in name
        or any(unicodedata.category(c).startswith("C") for c in name)
        or Path(name).name != name
    ):
        raise CampaignApiIntegrityError
    try:
        content = read_verified(
            expected_path,
            asset.sha256,
            expected_size=asset.byte_size,
            maximum_size=settings.MAX_UPLOAD_FILE_SIZE,
        )
    except Exception as exc:
        raise CampaignApiIntegrityError from exc
    ascii_fallback = "".join(
        c if (c.isascii() and c.isprintable() and c not in ('"', "\\", "\r", "\n")) else "_"
        for c in name
    ).strip() or "artifact"
    encoded_name = quote(name, safe="")
    disposition = f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded_name}'
    return content, asset.media_type, asset.sha256, disposition
