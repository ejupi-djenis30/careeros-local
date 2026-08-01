import hashlib
import re
import zipfile
from io import BytesIO

from docx import Document
from pypdf import PdfReader

from backend.core.config import settings
from backend.resumes.artifact_policy import (
    MAX_RESUME_ARTIFACT_BYTES,
    MAX_RESUME_DOCX_ENTRIES,
    MAX_RESUME_DOCX_UNCOMPRESSED_BYTES,
)


class ResumeQualityError(ValueError):
    pass


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _in_order(text: str, values: list[str]) -> bool:
    cursor = 0
    for value in values:
        normalized = _normalized(value)
        if not normalized:
            continue
        position = text.find(normalized, cursor)
        if position < 0:
            return False
        cursor = position + len(normalized)
    return True


def validate_resume_artifacts(
    *,
    pdf: bytes,
    docx: bytes,
    required_headings: list[str],
    required_text: list[str],
    template_kind: str,
    expect_photo: bool,
    columns: int = 1,
) -> dict:
    if len(pdf) > MAX_RESUME_ARTIFACT_BYTES or len(docx) > MAX_RESUME_ARTIFACT_BYTES:
        raise ResumeQualityError(
            f"Generated resume artifacts cannot exceed {MAX_RESUME_ARTIFACT_BYTES} bytes"
        )
    try:
        pdf_document = PdfReader(BytesIO(pdf))
        page_count = len(pdf_document.pages)
    except Exception as exc:
        raise ResumeQualityError("Generated PDF could not be reopened") from exc
    if page_count < 1 or page_count > settings.RESUME_MAX_PAGES:
        raise ResumeQualityError(
            f"Generated PDF has {page_count} pages; the configured limit is "
            f"{settings.RESUME_MAX_PAGES}"
        )
    try:
        extracted_text = "\n".join(page.extract_text() or "" for page in pdf_document.pages)
        pdf_image_count = sum(len(page.images) for page in pdf_document.pages)
        metadata = pdf_document.metadata
        pdf_metadata = {
            "author": metadata.author if metadata else None,
            "creator": metadata.creator if metadata else None,
            "producer": metadata.producer if metadata else None,
            "subject": metadata.subject if metadata else None,
        }
    except Exception as exc:
        raise ResumeQualityError("Generated PDF could not be reopened") from exc
    normalized_pdf = _normalized(extracted_text)
    missing_pdf = [
        item
        for item in required_headings + required_text
        if _normalized(item) not in normalized_pdf
    ]
    if missing_pdf:
        raise ResumeQualityError(
            "Generated PDF failed text extraction for: " + ", ".join(missing_pdf)
        )
    if not _in_order(normalized_pdf, required_headings) or not _in_order(
        normalized_pdf, required_text
    ):
        raise ResumeQualityError("Generated PDF does not preserve the requested text order")
    if template_kind == "ats" and pdf_image_count:
        raise ResumeQualityError("ATS PDF unexpectedly contains an image")
    if expect_photo and pdf_image_count < 1:
        raise ResumeQualityError("Photo PDF does not contain the normalized photo")

    try:
        with zipfile.ZipFile(BytesIO(docx)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_RESUME_DOCX_ENTRIES:
                raise ResumeQualityError("Generated DOCX contains too many archive entries")
            if len({entry.filename for entry in entries}) != len(entries):
                raise ResumeQualityError("Generated DOCX contains duplicate archive entries")
            if any(entry.flag_bits & 0x1 for entry in entries):
                raise ResumeQualityError("Generated DOCX cannot contain encrypted entries")
            if sum(entry.file_size for entry in entries) > MAX_RESUME_DOCX_UNCOMPRESSED_BYTES:
                raise ResumeQualityError("Generated DOCX expands beyond the local artifact limit")
            names = {entry.filename for entry in entries}
            if not {"[Content_Types].xml", "word/document.xml"} <= names:
                raise ResumeQualityError("Generated DOCX is missing required package entries")
            docx_image_count = sum(1 for name in names if name.startswith("word/media/"))
        word_document = Document(BytesIO(docx))
        docx_text = "\n".join(paragraph.text for paragraph in word_document.paragraphs)
        docx_properties = word_document.core_properties
    except ResumeQualityError:
        raise
    except Exception as exc:
        raise ResumeQualityError("Generated DOCX could not be reopened") from exc
    normalized_docx = _normalized(docx_text)
    missing_docx = [
        item
        for item in required_headings + required_text
        if _normalized(item) not in normalized_docx
    ]
    if missing_docx:
        raise ResumeQualityError(
            "Generated DOCX is missing required content: " + ", ".join(missing_docx)
        )
    if not _in_order(normalized_docx, required_headings) or not _in_order(
        normalized_docx, required_text
    ):
        raise ResumeQualityError("Generated DOCX does not preserve the requested text order")
    if template_kind == "ats" and docx_image_count:
        raise ResumeQualityError("ATS DOCX unexpectedly contains an image")
    if expect_photo and docx_image_count < 1:
        raise ResumeQualityError("Photo DOCX does not contain the normalized photo")

    metadata_sanitized = (
        pdf_metadata.get("author") == "CareerOS Local"
        and pdf_metadata.get("creator") == "CareerOS Local"
        and pdf_metadata.get("producer") == "CareerOS Local"
        and pdf_metadata.get("subject") == "Resume"
        and docx_properties.author == "CareerOS Local"
        and docx_properties.comments == "Generated locally"
        and docx_properties.last_modified_by == "CareerOS Local"
    )
    if not metadata_sanitized:
        raise ResumeQualityError("Generated artifacts contain unexpected document metadata")

    return {
        "passed": True,
        "template_kind": template_kind,
        "layout": (
            "single-column"
            if template_kind == "ats"
            else f"{'two' if columns == 2 else 'single'}-column-photo"
        ),
        "page_count": page_count,
        "pdf_text_characters": len(extracted_text),
        "pdf_image_count": pdf_image_count,
        "docx_text_characters": len(docx_text),
        "docx_image_count": docx_image_count,
        "required_headings": required_headings,
        "text_order_verified": True,
        "metadata_sanitized": True,
        "within_page_limit": True,
        "max_pages": settings.RESUME_MAX_PAGES,
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "docx_sha256": hashlib.sha256(docx).hexdigest(),
    }
