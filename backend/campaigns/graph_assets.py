"""Read-only verification of campaign artifact assets and root source documents."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy.orm import Session

from backend.campaigns.import_planner_types import PlannedCampaign
from backend.campaigns.models import CampaignArtifact
from backend.campaigns.service_helpers import get_safe_media_type, owner_scoped_uuid
from backend.career.models import CandidateProfile, CareerAsset, SourceDocument
from backend.career.source_parsing import PreparedSourceDocument
from backend.core.config import settings
from backend.storage.atomic import read_verified


def _same(actual: Any, expected: Any) -> bool:
    return bool(actual == expected)


def _verify_asset(
    db: Session,
    *,
    asset_id: str,
    profile_id: str,
    expected: Any,
    expected_original_name: str,
    expected_media_type: str,
) -> bool:
    asset = db.query(CareerAsset).filter(CareerAsset.id == asset_id).first()
    if asset is None:
        return False
    storage_path = f"assets/campaign/{expected.sha256[:2]}/{expected.sha256}"
    fields: tuple[tuple[Any, Any], ...] = (
        (asset.id, str(uuid.uuid5(uuid.NAMESPACE_URL, f"urn:careeros:asset:{profile_id}:{expected.sha256}"))),
        (asset.profile_id, profile_id),
        (asset.kind, "campaign_document"),
        (asset.original_name, expected_original_name),
        (asset.media_type, expected_media_type),
        (asset.sha256, expected.sha256),
        (asset.byte_size, expected.byte_size),
        (asset.storage_path, storage_path),
        (asset.normalized, False),
    )
    if any(not _same(actual, want) for actual, want in fields):
        return False
    try:
        stored = read_verified(
            storage_path,
            expected.sha256,
            expected_size=expected.byte_size,
            maximum_size=settings.MAX_UPLOAD_FILE_SIZE,
        )
    except Exception:
        return False
    return bool(stored == expected.raw_bytes)


def verify_artifacts(
    db: Session,
    *,
    campaign_id: str,
    profile_id: str,
    identity_scope: str,
    fingerprint: str,
    planned: PlannedCampaign,
    prepared: list[PreparedSourceDocument],
) -> bool:
    """Verify exact artifact rows, bindings, asset metadata, and bytes."""
    descriptors: dict[str, tuple[str, str]] = {
        item.sha256: (item.display_name, get_safe_media_type(item.relative_path))
        for item in planned.artifacts
    }
    for item in prepared:
        descriptors.setdefault(item.sha256, (item.original_name, item.media_type))
    expected_ids = {
        owner_scoped_uuid(identity_scope, fingerprint, "artifact", item.relative_path)
        for item in planned.artifacts
    }
    actual_rows = db.query(CampaignArtifact).filter(CampaignArtifact.campaign_id == campaign_id).all()
    if {item.id for item in actual_rows} != expected_ids:
        return False
    for expected in planned.artifacts:
        item_id = owner_scoped_uuid(identity_scope, fingerprint, "artifact", expected.relative_path)
        artifact_row = db.query(CampaignArtifact).filter(CampaignArtifact.id == item_id).first()
        if artifact_row is None:
            return False
        expected_app_id = (
            owner_scoped_uuid(identity_scope, fingerprint, "application", expected.source_application_id)
            if expected.source_application_id
            else None
        )
        fields = (
            (artifact_row.campaign_id, campaign_id),
            (artifact_row.application_id, expected_app_id),
            (artifact_row.relative_path, expected.relative_path),
            (artifact_row.display_name, expected.display_name),
            (artifact_row.category, expected.category),
            (artifact_row.source_order, expected.source_order),
            (artifact_row.created_at, planned.imported_at),
        )
        if any(not _same(actual, want) for actual, want in fields):
            return False
        original_name, media_type = descriptors[expected.sha256]
        if not _verify_asset(
            db,
            asset_id=artifact_row.asset_id,
            profile_id=profile_id,
            expected=expected,
            expected_original_name=original_name,
            expected_media_type=media_type,
        ):
            return False
    return True


def verify_source_documents(
    db: Session,
    *,
    profile: CandidateProfile,
    identity_scope: str,
    fingerprint: str,
    prepared: list[PreparedSourceDocument],
    descriptors: dict[str, tuple[str, str]],
) -> bool:
    """Verify exact root SourceDocument rows, asset metadata, and bytes."""
    for expected in prepared:
        asset_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"urn:careeros:asset:{profile.id}:{expected.sha256}",
            )
        )
        item = db.query(SourceDocument).filter(SourceDocument.asset_id == asset_id).first()
        if item is None or item.profile_id != profile.id:
            return False
        if item.document_type != expected.document_type or item.source_role != expected.source_role:
            return False
        if item.extracted_text != expected.extracted_text:
            return False
        if item.extracted_text_sha256 != hashlib.sha256(expected.extracted_text.encode("utf-8")).hexdigest():
            return False
        asset = db.query(CareerAsset).filter(CareerAsset.id == item.asset_id).first()
        if asset is None or asset.profile_id != profile.id or asset.kind != "campaign_document":
            return False
        if asset.id != asset_id:
            return False
        original_name, media_type = descriptors[expected.sha256]
        if (
            asset.original_name != original_name
            or asset.media_type != media_type
            or asset.sha256 != expected.sha256
            or asset.normalized is not False
        ):
            return False
        if asset.byte_size != len(expected.data) or asset.storage_path != f"assets/campaign/{expected.sha256[:2]}/{expected.sha256}":
            return False
        try:
            stored = read_verified(
                asset.storage_path,
                expected.sha256,
                expected_size=len(expected.data),
                maximum_size=settings.MAX_UPLOAD_FILE_SIZE,
            )
        except Exception:
            return False
        if stored != expected.data:
            return False
    return True
