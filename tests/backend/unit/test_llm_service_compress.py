"""Tests for LLMService._compress_description_if_needed."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.llm_service import LLMService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def llm_service():
    return LLMService()


async def test_compress_skips_when_under_limit(llm_service):
    """Short descriptions are returned unchanged without any LLM call."""
    short = "This is a short description."
    with patch.object(llm_service, "_get_provider") as mock_get_provider:
        result = await llm_service._compress_description_if_needed(short, max_chars=1000)

    assert result == short
    mock_get_provider.assert_not_called()


async def test_compress_skips_on_empty_string(llm_service):
    result = await llm_service._compress_description_if_needed("", max_chars=100)
    assert result == ""


async def test_compress_calls_llm_when_over_limit(llm_service):
    """When description exceeds max_chars, the LLM compressor is called."""
    long_desc = "A" * 9000  # exceeds 8000-char NORMALIZE limit
    compressed_output = "Compressed: " + "A" * 100

    mock_provider = MagicMock()
    mock_provider.generate_text_async = AsyncMock(return_value=compressed_output)

    with patch.object(llm_service, "_get_provider", return_value=mock_provider):
        result = await llm_service._compress_description_if_needed(long_desc, max_chars=8000)

    mock_provider.generate_text_async.assert_called_once()
    assert result == compressed_output
    # Original was 9000; compressed should be the LLM output
    assert result != long_desc


async def test_compress_falls_back_to_truncation_on_llm_failure(llm_service):
    """If the LLM call raises, we fall back to hard truncation (no crash)."""
    long_desc = "B" * 9000

    mock_provider = MagicMock()
    mock_provider.generate_text_async = AsyncMock(side_effect=RuntimeError("LLM timeout"))

    with patch.object(llm_service, "_get_provider", return_value=mock_provider):
        result = await llm_service._compress_description_if_needed(long_desc, max_chars=8000)

    # Falls back to exact truncation
    assert result == long_desc[:8000]
    assert len(result) == 8000


async def test_compress_falls_back_to_truncation_when_llm_returns_empty(llm_service):
    """If the LLM returns an empty / nonsense response, truncation is used."""
    long_desc = "C" * 9000

    mock_provider = MagicMock()
    mock_provider.generate_text_async = AsyncMock(return_value="  ")  # whitespace only

    with patch.object(llm_service, "_get_provider", return_value=mock_provider):
        result = await llm_service._compress_description_if_needed(long_desc, max_chars=8000)

    assert result == long_desc[:8000]


async def test_compress_uses_compress_step_provider(llm_service):
    """Verifies the 'compress' step is used so users can configure it separately."""
    long_desc = "D" * 9000
    mock_provider = MagicMock()
    mock_provider.generate_text_async = AsyncMock(return_value="Compressed output " + "D" * 60)

    with patch.object(llm_service, "_get_provider", return_value=mock_provider) as mock_get_provider:
        await llm_service._compress_description_if_needed(long_desc, max_chars=8000)

    mock_get_provider.assert_called_once_with("compress")
