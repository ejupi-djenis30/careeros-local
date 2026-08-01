from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from backend.services.utils import (
    _extract_from_pdf,
    extract_text_from_file,
    safe_upload_filename,
)


@pytest.mark.asyncio
async def test_extract_text_txt():
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test.txt"
    mock_file.read = AsyncMock(return_value=b"Hello Text")

    text = await extract_text_from_file(mock_file)
    assert text == "Hello Text"


@pytest.mark.asyncio
async def test_extract_text_unsupported():
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test.exe"

    with pytest.raises(HTTPException) as exc:
        await extract_text_from_file(mock_file)
    assert exc.value.status_code == 400
    assert "Unsupported file type" in exc.value.detail


@pytest.mark.asyncio
async def test_extract_text_pdf_success():
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test.pdf"
    mock_file.read = AsyncMock(return_value=b"fake pdf content")

    with patch("backend.services.utils._extract_from_pdf", return_value="PDF Text"):
        text = await extract_text_from_file(mock_file)
        assert text == "PDF Text"


@pytest.mark.asyncio
async def test_extract_text_exception():
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test.txt"
    mock_file.read = AsyncMock(side_effect=Exception("Read Error"))

    with pytest.raises(HTTPException) as exc:
        await extract_text_from_file(mock_file)
    assert exc.value.status_code == 400
    assert exc.value.detail == "The uploaded file could not be processed."
    assert "Read Error" not in exc.value.detail


def test_extract_from_pdf_error():
    with pytest.raises(Exception) as exc:
        _extract_from_pdf(b"not a pdf")
    assert str(exc.value) == "PDF parsing failed"


def test_upload_filename_is_a_bounded_display_only_basename():
    assert safe_upload_filename("..\\private\\resume\n.txt") == "resume.txt"
    assert safe_upload_filename("/tmp/. ", fallback="cv") == "cv"
    assert len(safe_upload_filename("x" * 500 + ".txt")) == 255


@pytest.mark.asyncio
async def test_extract_text_rejects_oversize_stream_without_declared_size(monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_FILE_SIZE", 8)
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "resume.txt"
    mock_file.content_type = "text/plain"
    mock_file.read = AsyncMock(return_value=b"123456789")

    with pytest.raises(HTTPException) as exc:
        await extract_text_from_file(mock_file)

    assert exc.value.status_code == 413
    mock_file.read.assert_awaited_once_with(9)


@pytest.mark.asyncio
async def test_extract_text_rejects_excessive_decoded_text(monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "CV_IMPORT_MAX_EXTRACTED_CHARS", 4)
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "resume.txt"
    mock_file.content_type = "text/plain"
    mock_file.read = AsyncMock(return_value=b"12345")

    with pytest.raises(HTTPException) as exc:
        await extract_text_from_file(mock_file)

    assert exc.value.status_code == 400
    assert exc.value.detail == "The uploaded file could not be processed."


def test_extract_pdf_stops_before_processing_excessive_page_count(monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "CV_IMPORT_MAX_PAGES", 1)
    reader = MagicMock()
    reader.pages = [MagicMock(), MagicMock()]
    monkeypatch.setattr("backend.services.utils.PdfReader", lambda _payload: reader)

    with pytest.raises(ValueError, match="PDF parsing failed") as exc:
        _extract_from_pdf(b"%PDF")

    assert isinstance(exc.value.__cause__, ValueError)
