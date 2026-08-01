import asyncio
from typing import Any

import pytest

from backend.providers.jobs.exceptions import ProviderError, ResponseParseError
from backend.providers.jobs.jobroom import client as jobroom_client
from backend.providers.jobs.jobroom.client import JobRoomProvider
from backend.providers.jobs.models import JobSearchRequest


class _JsonResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _ReadySession:
    def __init__(self, payload: Any = None) -> None:
        self.payload = payload
        self.request_urls: list[str] = []

    async def with_retry_csrf(self, *, url: str, **_: Any) -> _JsonResponse:
        self.request_urls.append(url)
        return _JsonResponse(self.payload)

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_jobroom_session_initialization_is_single_flight(monkeypatch) -> None:
    instances = []

    class FakeSession:
        def __init__(self, **_: Any) -> None:
            self.start_calls = 0
            self.refresh_calls = 0
            self.close_calls = 0
            instances.append(self)

        async def start(self) -> None:
            self.start_calls += 1
            await asyncio.sleep(0)

        async def refresh_csrf_token(self, _url: str) -> None:
            self.refresh_calls += 1
            await asyncio.sleep(0)

        async def close(self) -> None:
            self.close_calls += 1

    monkeypatch.setattr(jobroom_client, "ScraperSession", FakeSession)
    provider = JobRoomProvider()

    await asyncio.gather(*(provider._init_session() for _ in range(8)))

    assert len(instances) == 1
    assert instances[0].start_calls == 1
    assert instances[0].refresh_calls == 1
    assert provider._session is instances[0]
    assert provider._csrf_initialized is True

    await provider.close()
    assert instances[0].close_calls == 1


@pytest.mark.asyncio
async def test_jobroom_failed_csrf_bootstrap_closes_partial_session(monkeypatch) -> None:
    instances = []

    class FailingSession:
        def __init__(self, **_: Any) -> None:
            self.close_calls = 0
            instances.append(self)

        async def start(self) -> None:
            return None

        async def refresh_csrf_token(self, _url: str) -> None:
            raise RuntimeError("csrf bootstrap failed")

        async def close(self) -> None:
            self.close_calls += 1

    monkeypatch.setattr(jobroom_client, "ScraperSession", FailingSession)
    provider = JobRoomProvider()

    with pytest.raises(RuntimeError, match="csrf bootstrap failed"):
        await provider._init_session()

    assert len(instances) == 1
    assert instances[0].close_calls == 1
    assert provider._session is None
    assert provider._csrf_initialized is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"content": "not-a-list", "totalElements": 1},
        {"content": [{}], "totalElements": True},
        {"content": [{}], "totalElements": 0},
        [{"id": index} for index in range(21)],
        ["not-a-job"],
    ],
)
async def test_jobroom_search_rejects_malformed_provider_envelopes(payload: Any) -> None:
    provider = JobRoomProvider()
    provider._session = _ReadySession(payload)
    provider._csrf_initialized = True

    with pytest.raises(ProviderError) as exc_info:
        await provider.search(JobSearchRequest(page_size=20))

    assert isinstance(exc_info.value.__cause__, ResponseParseError)
    assert exc_info.value.message == "Search failed"


@pytest.mark.asyncio
async def test_jobroom_detail_identifier_is_encoded_as_one_path_segment(monkeypatch) -> None:
    provider = JobRoomProvider()
    session = _ReadySession({"title": "Safe"})
    provider._session = session
    provider._csrf_initialized = True
    expected_listing = object()
    monkeypatch.setattr(jobroom_client, "transform_job_data", lambda *_args: expected_listing)

    result = await provider.get_details("  ../sensitive?view=raw  ")

    assert result is expected_listing
    assert len(session.request_urls) == 1
    assert "/..%2Fsensitive%3Fview%3Draw?_ng=" in session.request_urls[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("job_id", ["", "   ", "x" * 257, None])
async def test_jobroom_invalid_detail_identifier_does_not_open_session(job_id: Any) -> None:
    provider = JobRoomProvider()

    with pytest.raises(ProviderError, match="Provider request failed"):
        await provider.get_details(job_id)

    assert provider._session is None
