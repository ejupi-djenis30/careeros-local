"""Verify existing owned source records before acknowledging duplicate imports."""

from __future__ import annotations

import hashlib

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.career.models import CareerAsset, SourceDocument
from backend.career.schemas import VALID_SOURCE_ROLES
from backend.career.source_parsing import (
    PreparedSourceDocument,
    SourceImportError,
    _document_type,
)
from backend.core.config import settings
from backend.storage.atomic import read_verified

_INTEGRITY_ERROR = "The stored source document failed its integrity check"


def _verify_source(
    source: SourceDocument | None,
    asset: CareerAsset,
    *,
    profile_id: str,
    prepared: PreparedSourceDocument,
    storage_path: str,
) -> SourceDocument:
    try:
        if source is None:
            raise ValueError("Missing source relationship")
        if (
            source.profile_id != profile_id
            or asset.profile_id != profile_id
            or source.asset_id != asset.id
            or asset.kind != "source_document"
            or asset.normalized is not False
            or asset.sha256 != prepared.sha256
            or asset.storage_path != storage_path
            or asset.byte_size != len(prepared.data)
            or source.source_role not in VALID_SOURCE_ROLES
            or not asset.original_name
            or "/" in asset.original_name
            or "\\" in asset.original_name
            or _document_type(asset.original_name, asset.media_type) != source.document_type
            or source.document_type != prepared.document_type
            or len(source.extracted_text) > settings.SOURCE_IMPORT_MAX_EXTRACTED_CHARS
            or hashlib.sha256(source.extracted_text.encode("utf-8")).hexdigest()
            != source.extracted_text_sha256
        ):
            raise ValueError("Invalid stored source metadata")
        read_verified(
            asset.storage_path,
            asset.sha256,
            expected_size=asset.byte_size,
            maximum_size=settings.MAX_UPLOAD_FILE_SIZE,
        )
    except (OSError, ValueError) as exc:
        raise SourceImportError(_INTEGRITY_ERROR) from exc
    return source


def find_reusable_source_document(
    db: Session, *, profile_id: str, prepared: PreparedSourceDocument
) -> SourceDocument | None:
    storage_path = f"assets/{prepared.sha256[:2]}/{prepared.sha256}"
    # Look from either owned side so a broken cross-profile link cannot be
    # mistaken for a new import. The canonical path also detects a changed hash.
    candidates = (
        db.query(SourceDocument, CareerAsset)
        .select_from(CareerAsset)
        .outerjoin(SourceDocument, SourceDocument.asset_id == CareerAsset.id)
        .filter(
            or_(CareerAsset.profile_id == profile_id, SourceDocument.profile_id == profile_id),
            or_(CareerAsset.sha256 == prepared.sha256, CareerAsset.storage_path == storage_path),
            or_(CareerAsset.kind == "source_document", SourceDocument.id.is_not(None)),
        )
        .limit(2)
        .all()
    )
    if not candidates:
        return None
    if len(candidates) != 1:
        raise SourceImportError(_INTEGRITY_ERROR)
    source, asset = candidates[0]
    return _verify_source(
        source, asset, profile_id=profile_id, prepared=prepared, storage_path=storage_path
    )
