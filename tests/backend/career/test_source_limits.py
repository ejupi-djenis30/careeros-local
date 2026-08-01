from io import BytesIO
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from backend.career.sources import SourceImportError, _extract_text
from backend.core.config import settings


def _docx(entries: list[tuple[str, bytes]]) -> bytes:
    output = BytesIO()
    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    return output.getvalue()


def test_source_text_extraction_has_a_hard_character_limit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SOURCE_IMPORT_MAX_EXTRACTED_CHARS", 4)

    with pytest.raises(SourceImportError, match="safety limit"):
        _extract_text(b"12345", "text")


def test_source_pdf_rejects_excessive_page_count_before_extraction(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SOURCE_IMPORT_MAX_PAGES", 1)
    pages = [
        SimpleNamespace(extract_text=lambda: "one"),
        SimpleNamespace(extract_text=lambda: "two"),
    ]
    monkeypatch.setattr("pypdf.PdfReader", lambda _payload: SimpleNamespace(pages=pages))

    with pytest.raises(SourceImportError, match="page limit"):
        _extract_text(b"%PDF fake", "pdf")


def test_source_pdf_bounds_cumulative_extracted_text(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SOURCE_IMPORT_MAX_EXTRACTED_CHARS", 5)
    pages = [
        SimpleNamespace(extract_text=lambda: "123"),
        SimpleNamespace(extract_text=lambda: "456"),
    ]
    monkeypatch.setattr("pypdf.PdfReader", lambda _payload: SimpleNamespace(pages=pages))

    with pytest.raises(SourceImportError, match="safety limit"):
        _extract_text(b"%PDF fake", "pdf")


def test_docx_preflight_bounds_member_count(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SOURCE_IMPORT_MAX_ARCHIVE_MEMBERS", 1)
    data = _docx(
        [
            ("word/document.xml", b"<document />"),
            ("word/styles.xml", b"<styles />"),
        ]
    )

    with pytest.raises(SourceImportError, match="too many members"):
        _extract_text(data, "docx")


def test_docx_preflight_bounds_actual_uncompressed_bytes(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SOURCE_IMPORT_MAX_UNCOMPRESSED_BYTES", 8)
    data = _docx([("word/document.xml", b"123456789")])

    with pytest.raises(SourceImportError, match="expands beyond"):
        _extract_text(data, "docx")


def test_docx_preflight_rejects_ambiguous_duplicate_names() -> None:
    data = _docx(
        [
            ("word/document.xml", b"<document />"),
            ("WORD/DOCUMENT.XML", b"<different />"),
        ]
    )

    with pytest.raises(SourceImportError, match="structure is invalid"):
        _extract_text(data, "docx")


def test_docx_preflight_requires_the_document_body() -> None:
    data = _docx([("word/styles.xml", b"<styles />")])

    with pytest.raises(SourceImportError, match="no document body"):
        _extract_text(data, "docx")
