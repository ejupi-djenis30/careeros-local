from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.providers.jobs.exceptions import ProviderError
from backend.providers.jobs.swissdevjobs.client import SwissDevJobsProvider


@pytest.mark.asyncio
async def test_swissdevjobs_light_parse_error():
    provider = SwissDevJobsProvider()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"not": "a list"}
        mock_get.return_value = mock_resp

        from backend.providers.jobs.models import JobSearchRequest

        with pytest.raises(ProviderError) as exc:
            await provider.search(JobSearchRequest(query="test"))
        assert "Search failed" in str(exc.value)


@pytest.mark.asyncio
async def test_swissdevjobs_health_check_degraded():
    provider = SwissDevJobsProvider()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

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
