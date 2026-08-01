import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.providers.jobs.exceptions import ProviderError, ResponseParseError
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
async def test_swissdevjobs_health_check_overrides_existing_client_timeout():
    provider = SwissDevJobsProvider()
    client = MagicMock()
    client.is_closed = False
    client.get = AsyncMock(return_value=_mock_response({}, status_code=200))
    provider._client = client

    health = await provider.health_check()

    assert health.status.value == "healthy"
    client.get.assert_awaited_once_with(
        "https://swissdevjobs.ch/api/jobsLight",
        timeout=10.0,
    )


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


@pytest.mark.asyncio
async def test_swissdevjobs_detail_cache_is_bounded_and_evicts_lru_entry():
    provider = SwissDevJobsProvider()
    provider._DETAIL_JOBS_CACHE_MAX_ENTRIES = 2
    provider._fetch_job_details_with_retry = AsyncMock(
        side_effect=lambda slug: {"jobUrl": slug},
    )

    assert await provider._get_job_details("first") == {"jobUrl": "first"}
    assert await provider._get_job_details("second") == {"jobUrl": "second"}
    # A cache hit makes `first` the most recently used entry.
    assert await provider._get_job_details("first") == {"jobUrl": "first"}
    assert await provider._get_job_details("third") == {"jobUrl": "third"}

    assert list(provider._detail_jobs_cache) == ["first", "third"]
    assert provider._fetch_job_details_with_retry.await_count == 3


def test_swissdevjobs_transport_ignores_ambient_proxies_and_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = {}
    client = MagicMock()

    def fake_client(**kwargs):
        options.update(kwargs)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    provider = SwissDevJobsProvider()

    assert provider._ensure_client() is client
    assert options["trust_env"] is False
    assert options["follow_redirects"] is False
    assert options["headers"]["Accept-Encoding"] == "identity"
    assert len(options["event_hooks"]["response"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("size_source", ["declared", "buffered"])
async def test_swissdevjobs_oversize_is_not_retried(size_source: str) -> None:
    calls = 0

    def oversized(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if size_source == "declared":
            return httpx.Response(200, headers={"content-length": "5"}, content=b"")
        return httpx.Response(
            200,
            headers={"transfer-encoding": "chunked"},
            content=b"12345",
        )

    provider = SwissDevJobsProvider()
    provider._MAX_RESPONSE_BYTES = 4
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(oversized),
        follow_redirects=False,
        trust_env=False,
    )
    try:
        with pytest.raises(ResponseParseError):
            await provider._fetch_light_jobs_with_retry()
    finally:
        await provider.close()

    assert calls == 1


@pytest.mark.asyncio
async def test_swissdevjobs_rejects_excessive_light_job_count_before_caching() -> None:
    provider = SwissDevJobsProvider()
    provider._LIGHT_JOBS_MAX_ENTRIES = 2
    provider._fetch_light_jobs_with_retry = AsyncMock(return_value=[{}, {}, {}])

    with pytest.raises(ResponseParseError):
        await provider._get_light_jobs()

    assert provider._light_jobs_cache is None
    provider._fetch_light_jobs_with_retry.assert_awaited_once()


@pytest.mark.asyncio
async def test_swissdevjobs_single_flight_survives_one_waiter_cancellation() -> None:
    provider = SwissDevJobsProvider()
    started = asyncio.Event()
    release = asyncio.Event()

    async def fetch_detail(slug: str):
        started.set()
        await release.wait()
        return {"jobUrl": slug}

    provider._fetch_job_details_with_retry = AsyncMock(side_effect=fetch_detail)
    cancelled_waiter = asyncio.create_task(provider._get_job_details("shared"))
    await started.wait()
    surviving_waiter = asyncio.create_task(provider._get_job_details("shared"))

    cancelled_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_waiter
    release.set()

    assert await surviving_waiter == {"jobUrl": "shared"}
    assert provider._fetch_job_details_with_retry.await_count == 1
    assert provider._detail_jobs_inflight == {}
    assert list(provider._detail_jobs_cache) == ["shared"]
