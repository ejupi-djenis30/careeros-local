import hashlib
import re
import zipfile
from io import BytesIO

import pymupdf
from docx import Document

from backend.core.config import settings


class ResumeQualityError(ValueError):
    pass


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


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
    try:
        with pymupdf.open(stream=pdf, filetype="pdf") as document:
            page_count = document.page_count
            extracted_text = "\n".join(page.get_text("text") for page in document)
            pdf_image_count = sum(len(page.get_images(full=True)) for page in document)
    except Exception as exc:
        raise ResumeQualityError("Generated PDF could not be reopened") from exc

    if page_count < 1 or page_count > settings.RESUME_MAX_PAGES:
        raise ResumeQualityError(
            f"Generated PDF has {page_count} pages; the configured limit is "
            f"{settings.RESUME_MAX_PAGES}"
        )
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
    if template_kind == "ats" and pdf_image_count:
        raise ResumeQualityError("ATS PDF unexpectedly contains an image")
    if expect_photo and pdf_image_count < 1:
        raise ResumeQualityError("Photo PDF does not contain the normalized photo")

    try:
        document = Document(BytesIO(docx))
        docx_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        with zipfile.ZipFile(BytesIO(docx)) as archive:
            docx_image_count = sum(
                1 for name in archive.namelist() if name.startswith("word/media/")
            )
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
    if template_kind == "ats" and docx_image_count:
        raise ResumeQualityError("ATS DOCX unexpectedly contains an image")
    if expect_photo and docx_image_count < 1:
        raise ResumeQualityError("Photo DOCX does not contain the normalized photo")

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
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "docx_sha256": hashlib.sha256(docx).hexdigest(),
    }
