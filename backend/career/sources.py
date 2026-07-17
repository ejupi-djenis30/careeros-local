import hashlib
from io import BytesIO
from pathlib import Path

from sqlalchemy.orm import Session

from backend.career.models import CareerAsset, SourceDocument
from backend.career.repository import CareerProfileRepository
from backend.career.schemas import SourceDocumentResponse
from backend.core.config import settings
from backend.storage.atomic import atomic_write, resolve_data_path


class SourceImportError(ValueError):
    pass


def _document_type(filename: str, media_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"} and media_type in {
        "text/plain",
        "text/markdown",
        "application/octet-stream",
    }:
        return "text"
    if suffix == ".pdf" and media_type in {"application/pdf", "application/octet-stream"}:
        return "pdf"
    if suffix == ".docx" and media_type in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    }:
        return "docx"
    raise SourceImportError("Supported source formats are TXT, Markdown, PDF and DOCX")


def _extract_text(data: bytes, document_type: str) -> str:
    if document_type == "text":
        try:
            return data.decode("utf-8-sig").replace("\x00", "").strip()
        except UnicodeDecodeError as exc:
            raise SourceImportError("Text documents must use UTF-8 encoding") from exc
    if document_type == "pdf":
        if not data.startswith(b"%PDF"):
            raise SourceImportError("The uploaded file is not a valid PDF")
        import pymupdf

        try:
            with pymupdf.open(stream=data, filetype="pdf") as document:
                return "\n".join(page.get_text() for page in document).strip()
        except Exception as exc:
            raise SourceImportError("Unable to read the PDF") from exc
    if not data.startswith(b"PK"):
        raise SourceImportError("The uploaded file is not a valid DOCX")
    try:
        from docx import Document

        document = Document(BytesIO(data))
        return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
    except Exception as exc:
        raise SourceImportError("Unable to read the DOCX") from exc


def _response(source: SourceDocument) -> SourceDocumentResponse:
    return SourceDocumentResponse(
        id=source.id,
        asset_id=source.asset.id,
        original_name=source.asset.original_name,
        media_type=source.asset.media_type,
        sha256=source.asset.sha256,
        byte_size=source.asset.byte_size,
        document_type=source.document_type,
        extracted_characters=len(source.extracted_text),
        created_at=source.created_at,
    )


def import_source_document(
    db: Session,
    *,
    user_id: int,
    filename: str,
    media_type: str,
    data: bytes,
) -> SourceDocumentResponse:
    profile = CareerProfileRepository(db).get_by_user(user_id)
    if profile is None:
        raise SourceImportError("Create the career profile before importing source documents")
    if not data:
        raise SourceImportError("The source document is empty")
    if len(data) > settings.MAX_UPLOAD_FILE_SIZE:
        raise SourceImportError("The source document exceeds the configured size limit")

    safe_name = Path(filename or "source").name[:255]
    kind = _document_type(safe_name, media_type or "application/octet-stream")
    extracted = _extract_text(data, kind)
    digest = hashlib.sha256(data).hexdigest()
    existing = (
        db.query(SourceDocument)
        .join(CareerAsset, SourceDocument.asset_id == CareerAsset.id)
        .filter(
            CareerAsset.profile_id == profile.id,
            CareerAsset.sha256 == digest,
            CareerAsset.kind == "source_document",
        )
        .first()
    )
    if existing:
        return _response(existing)

    relative_path = Path("assets") / digest[:2] / digest
    absolute_path, created_file = atomic_write(relative_path, data)
    try:
        asset = CareerAsset(
            profile_id=profile.id,
            kind="source_document",
            original_name=safe_name,
            media_type=media_type or "application/octet-stream",
            sha256=digest,
            byte_size=len(data),
            storage_path=relative_path.as_posix(),
            normalized=False,
        )
        db.add(asset)
        db.flush()
        source = SourceDocument(
            profile_id=profile.id,
            asset_id=asset.id,
            document_type=kind,
            extracted_text=extracted,
            extracted_text_sha256=hashlib.sha256(extracted.encode("utf-8")).hexdigest(),
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        return _response(source)
    except Exception:
        db.rollback()
        if created_file:
            resolve_data_path(relative_path).unlink(missing_ok=True)
        raise
