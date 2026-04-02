from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.providers.jobs.exceptions import ProviderError
from backend.providers.jobs.models import JobSearchRequest
from backend.providers.jobs.swissdevjobs.client import SwissDevJobsProvider

LIGHT_JOB = {
    "_id": "job-1",
    "jobUrl": "python-dev",
    "name": "Python Developer",
    "company": "Acme",
    "actualCity": "Zurich",
}

DETAIL_JOB = {
    "_id": "job-1",
    "jobUrl": "python-dev",
    "name": "Python Developer",
    "company": "Acme",
    "actualCity": "Zurich",
    "description": "Build APIs in Python.",
    "activeFrom": "2026-04-01T10:00:00Z",
}


def _mock_response(payload, status_code: int = 200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@pytest.mark.asyncio
async def test_swissdevjobs_light_parse_error():
    provider = SwissDevJobsProvider()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response({"not": "a list"})

        with pytest.raises(ProviderError) as exc:
            await provider.search(JobSearchRequest(query="test"))
        assert "Search failed" in str(exc.value)


@pytest.mark.asyncio
async def test_swissdevjobs_health_check_degraded():
    provider = SwissDevJobsProvider()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response({}, status_code=500)

        from backend.providers.jobs.models import ProviderStatus

        health = await provider.health_check()
        assert health.status == ProviderStatus.DEGRADED


@pytest.mark.asyncio
async def test_swissdevjobs_close():
    provider = SwissDevJobsProvider()

    # Needs to be an AsyncMock instance that returns something for aclose
    mock_client = AsyncMock()
    provider._client = mock_client
    await provider.close()
    mock_client.aclose.assert_called_once()
    assert provider._client is None


@pytest.mark.asyncio
async def test_swissdevjobs_search_reuses_cached_detail_response_across_calls():
    provider = SwissDevJobsProvider()

    async def fake_get(url, *args, **kwargs):
        if url.endswith("/jobsLight"):
            return _mock_response([LIGHT_JOB])
        if url.endswith("/jobWithUrl/python-dev"):
            return _mock_response(DETAIL_JOB)
        raise AssertionError(f"Unexpected URL: {url}")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = fake_get

        first = await provider.search(JobSearchRequest(query="Python"))
        second = await provider.search(JobSearchRequest(query="Python"))

    assert len(first.items) == 1
    assert len(second.items) == 1
    requested_urls = [call.args[0] for call in mock_get.await_args_list]
    assert requested_urls.count("https://swissdevjobs.ch/api/jobsLight") == 1
    assert requested_urls.count("https://swissdevjobs.ch/api/jobWithUrl/python-dev") == 1
