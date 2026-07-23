from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from backend.services.utils import _extract_from_pdf, extract_text_from_file


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
    assert "Failed to process file" in exc.value.detail


def test_extract_from_pdf_error():
    with pytest.raises(Exception) as exc:
        _extract_from_pdf(b"not a pdf")
    assert "PDF parsing error" in str(exc.value)
