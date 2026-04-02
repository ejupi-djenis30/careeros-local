"""Tests for deterministic prompt compaction in LLMService."""

from unittest.mock import patch

import pytest

from backend.services.llm_service import LLMService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def llm_service():
    return LLMService()


async def test_compress_skips_when_under_limit(llm_service):
    """Short descriptions are returned unchanged without any provider call."""
    short = "This is a short description."
    with patch.object(llm_service, "_get_provider") as mock_get_provider:
        result = await llm_service._compress_description_if_needed(short, max_chars=1000)

    assert result == short
    mock_get_provider.assert_not_called()


async def test_compress_skips_on_empty_string(llm_service):
    result = await llm_service._compress_description_if_needed("", max_chars=100)
    assert result == ""


async def test_compress_prioritizes_requirement_fragments(llm_service):
    long_desc = (
        "Welcome to our company. We build amazing things for the future. " * 40
        + "Must have German C1 and valid Swiss work permit. "
        + "Forklift license required. "
        + "Salary 70000 CHF. "
    )

    with patch.object(llm_service, "_get_provider") as mock_get_provider:
        result = await llm_service._compress_description_if_needed(long_desc, max_chars=220)

    assert "German C1" in result
    assert "Swiss work permit" in result
    assert "Forklift license" in result
    mock_get_provider.assert_not_called()


async def test_compress_strips_html_and_respects_limit(llm_service):
    long_desc = "<p>Required: English B2.</p><p>Experience: 3 years.</p>" + (" filler" * 500)

    result = await llm_service._compress_description_if_needed(long_desc, max_chars=120)

    assert "<p>" not in result
    assert "English B2" in result
    assert len(result) <= 120


async def test_compress_keeps_short_text_without_trimming_keywords(llm_service):
    long_desc = "Required: Python. Required: SQL. Required: Docker."

    result = await llm_service._compress_description_if_needed(long_desc, max_chars=200)

    assert result == long_desc
