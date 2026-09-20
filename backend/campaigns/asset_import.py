"""Content-addressed publication helpers for campaign imports."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy.orm import Session

from backend.campaigns.service_helpers import (
    CampaignImportError,
    get_safe_media_type,
    owner_scoped_uuid,
)
from backend.career.asset_publication import write_asset_publication_journal
from backend.career.models import CareerAsset, SourceDocument
from backend.career.source_parsing import PreparedSourceDocument
from backend.core.config import settings
from backend.storage.atomic import atomic_write, read_verified, resolve_data_path


def publish_or_reuse_campaign_asset(
    db: Session,
    *,
    profile_id: str,
    raw_bytes: bytes,
    sha256: str,
    byte_size: int,
    original_name: str,
    relative_path: str,
    new_files: set[str],
    new_journals: list[str],
) -> CareerAsset:
    """Publish a new campaign asset or verify and reuse an existing one."""
    storage_path = f"assets/campaign/{sha256[:2]}/{sha256}"
    existing_asset = (
        db.query(CareerAsset)
        .filter(
            CareerAsset.profile_id == profile_id,
            CareerAsset.sha256 == sha256,
            CareerAsset.kind == "campaign_document",
        )
        .first()
    )
    if existing_asset is not None:
        if existing_asset.byte_size != byte_size or existing_asset.storage_path != storage_path:
            raise CampaignImportError("Existing asset metadata does not match artifact", status_code=409)
        try:
            read_verified(storage_path, sha256, expected_size=byte_size, maximum_size=settings.MAX_UPLOAD_FILE_SIZE)
        except Exception as exc:
            raise CampaignImportError("Existing asset file failed integrity verification", status_code=409) from exc
        return existing_asset

    disk_path = resolve_data_path(storage_path, create_root=False)
    try:
        disk_path.lstat()
        file_on_disk = True
    except FileNotFoundError:
        file_on_disk = False
    if file_on_disk:
        try:
            read_verified(storage_path, sha256, expected_size=byte_size, maximum_size=settings.MAX_UPLOAD_FILE_SIZE)
        except Exception as exc:
            raise CampaignImportError("Shared asset file failed integrity verification", status_code=409) from exc
    else:
        journal_path = write_asset_publication_journal(
            operation_id=str(uuid.uuid4()),
            profile_id=profile_id,
            kind="campaign_document",
            storage_path=storage_path,
            sha256=sha256,
            byte_size=byte_size,
        )
        new_journals.append(journal_path)
        atomic_write(storage_path, raw_bytes)
        new_files.add(storage_path)

    new_asset = CareerAsset(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"urn:careeros:asset:{profile_id}:{sha256}")),
        profile_id=profile_id,
        kind="campaign_document",
        original_name=original_name[:255],
        media_type=get_safe_media_type(relative_path),
        sha256=sha256,
        byte_size=byte_size,
        storage_path=storage_path,
        normalized=False,
    )
    db.add(new_asset)
    db.flush()
    return new_asset


def publish_root_source_document(
    db: Session,
    *,
    profile_id: str,
    identity_scope: str,
    fingerprint: str,
    prep: PreparedSourceDocument,
    new_files: set[str],
    new_journals: list[str],
) -> None:
    """Publish a root source document asset and its reviewable source row."""
    asset = publish_or_reuse_campaign_asset(
        db,
        profile_id=profile_id,
        raw_bytes=prep.data,
        sha256=prep.sha256,
        byte_size=len(prep.data),
        original_name=prep.original_name,
        relative_path=prep.original_name,
        new_files=new_files,
        new_journals=new_journals,
    )
    existing_sdoc = db.query(SourceDocument).filter(SourceDocument.asset_id == asset.id).first()
    if existing_sdoc is not None:
        if existing_sdoc.source_role != prep.source_role:
            raise CampaignImportError("Conflicting root document role reuse", status_code=409)
        return
    db.add(SourceDocument(
        id=owner_scoped_uuid(identity_scope, fingerprint, "source_document", prep.original_name),
        profile_id=profile_id,
        asset_id=asset.id,
        document_type=prep.document_type,
        source_role=prep.source_role,
        extracted_text=prep.extracted_text,
        extracted_text_sha256=hashlib.sha256(prep.extracted_text.encode("utf-8")).hexdigest(),
    ))
