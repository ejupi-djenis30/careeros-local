import hashlib
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from backend.career.asset_publication import (
    begin_asset_publication_write,
    remove_asset_publication_journal,
    write_asset_publication_journal,
)
from backend.career.models import CareerAsset, SourceDocument
from backend.career.repository import CareerProfileRepository
from backend.career.schemas import SourceDocumentResponse, SourceFactCandidate
from backend.career.source_parsing import (
    PreparedSourceDocument,
    SourceImportError,
    extract_text,
    fact_candidates,
    prepare_source_document,
)
from backend.core.config import settings
from backend.storage.atomic import atomic_write

_extract_text = extract_text
__all__ = [
    "SourceImportError",
    "_extract_text",
    "fact_candidates",
    "import_source_document",
    "persist_prepared_source_document",
    "prepare_source_document",
    "settings",
]


def _response(
    source: SourceDocument,
    *,
    candidates: list[SourceFactCandidate] | tuple[SourceFactCandidate, ...] | None = None,
) -> SourceDocumentResponse:
    return SourceDocumentResponse(
        id=source.id,
        asset_id=source.asset.id,
        original_name=source.asset.original_name,
        media_type=source.asset.media_type,
        sha256=source.asset.sha256,
        byte_size=source.asset.byte_size,
        document_type=source.document_type,
        extracted_characters=len(source.extracted_text),
        text_preview=source.extracted_text[:4000],
        candidates=list(candidates)
        if candidates is not None
        else fact_candidates(source.extracted_text),
        created_at=source.created_at,
    )


def persist_prepared_source_document(
    db: Session,
    *,
    user_id: int,
    prepared: PreparedSourceDocument,
) -> SourceDocumentResponse:
    # Database-free parsing happens before this call. End authentication's read
    # snapshot without committing unrelated request state, then serialize the
    # shared content-addressed path and its recovery journal.
    begin_asset_publication_write(db)
    profile = CareerProfileRepository(db).get_by_user(user_id)
    if profile is None:
        db.rollback()
        raise SourceImportError("Create the career profile before importing source documents")
    existing = (
        db.query(SourceDocument)
        .join(CareerAsset, SourceDocument.asset_id == CareerAsset.id)
        .filter(
            CareerAsset.profile_id == profile.id,
            CareerAsset.sha256 == prepared.sha256,
            CareerAsset.kind == "source_document",
        )
        .first()
    )
    if existing:
        response = _response(existing)
        db.rollback()
        return response

    profile_id = profile.id
    relative_path = Path("assets") / prepared.sha256[:2] / prepared.sha256
    relative_path_text = relative_path.as_posix()
    asset_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    journal_path: str | None = None
    try:
        journal_path = write_asset_publication_journal(
            operation_id=asset_id,
            profile_id=profile_id,
            kind="source_document",
            storage_path=relative_path_text,
            sha256=prepared.sha256,
            byte_size=len(prepared.data),
        )
        atomic_write(relative_path, prepared.data)
        asset = CareerAsset(
            id=asset_id,
            profile_id=profile_id,
            kind="source_document",
            original_name=prepared.original_name,
            media_type=prepared.media_type,
            sha256=prepared.sha256,
            byte_size=len(prepared.data),
            storage_path=relative_path_text,
            normalized=False,
        )
        db.add(asset)
        db.flush()
        source = SourceDocument(
            id=source_id,
            profile_id=profile_id,
            asset_id=asset.id,
            document_type=prepared.document_type,
            extracted_text=prepared.extracted_text,
            extracted_text_sha256=hashlib.sha256(
                prepared.extracted_text.encode("utf-8")
            ).hexdigest(),
        )
        db.add(source)
        db.flush()
        response = _response(source, candidates=prepared.candidates)
        db.commit()
    except Exception as persist_error:
        db.rollback()
        try:
            begin_asset_publication_write(db)
            committed = (
                db.query(SourceDocument)
                .join(CareerAsset, SourceDocument.asset_id == CareerAsset.id)
                .filter(
                    SourceDocument.id == source_id,
                    SourceDocument.profile_id == profile_id,
                    CareerAsset.id == asset_id,
                    CareerAsset.storage_path == relative_path_text,
                    CareerAsset.sha256 == prepared.sha256,
                    CareerAsset.byte_size == len(prepared.data),
                )
                .one_or_none()
            )
            if committed is not None:
                recovered = _response(committed, candidates=prepared.candidates)
                db.rollback()
                return recovered
        except Exception:
            db.rollback()
            raise persist_error
        db.rollback()
        raise persist_error
    else:
        if journal_path is not None:
            try:
                remove_asset_publication_journal(journal_path)
            except Exception:
                # The committed row owns the bytes; startup/next writer safely
                # removes a redundant recovery record.
                pass
        return response


def import_source_document(
    db: Session,
    *,
    user_id: int,
    filename: str,
    media_type: str,
    data: bytes,
) -> SourceDocumentResponse:
    prepared = prepare_source_document(filename=filename, media_type=media_type, data=data)
    return persist_prepared_source_document(db, user_id=user_id, prepared=prepared)
