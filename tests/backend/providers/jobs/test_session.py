from __future__ import annotations

from typing import Any

import httpx
import pytest

from backend.providers.jobs.exceptions import ResponseParseError
from backend.providers.jobs.session import ScraperSession


class _FakeClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        self.is_closed = False

    async def get(self, url: str) -> httpx.Response:
        self.requests.append(("GET", url))
        return httpx.Response(
            200,
            content=b"{}",
            request=httpx.Request("GET", url),
        )

    async def aclose(self) -> None:
        self.is_closed = True


@pytest.mark.asyncio
async def test_scraper_transport_disables_redirects_and_ambient_proxies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options: dict[str, Any] = {}

    def fake_client(**kwargs: Any) -> _FakeClient:
        options.update(kwargs)
        return _FakeClient()

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    session = ScraperSession(base_url="https://www.job-room.ch")

    await session.start()

    assert options["follow_redirects"] is False
    assert options["trust_env"] is False
    assert options["verify"] is True
    assert options["headers"]["Accept-Encoding"] == "identity"
    assert len(options["event_hooks"]["response"]) == 1


@pytest.mark.asyncio
async def test_scraper_session_start_is_idempotent_and_reopens_only_after_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clients: list[_FakeClient] = []

    def fake_client(**_kwargs: Any) -> _FakeClient:
        client = _FakeClient()
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    session = ScraperSession(base_url="https://www.job-room.ch")

    await session.start()
    await session.start()
    assert len(clients) == 1

    await session.close()
    assert clients[0].is_closed is True
    await session.start()
    assert len(clients) == 2
    await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    (
        "http://www.job-room.ch/jobadservice/api/jobAdvertisements",
        "https://job-room.ch/jobadservice/api/jobAdvertisements",
        "https://www.job-room.ch.evil.test/jobadservice/api/jobAdvertisements",
        "https://127.0.0.1:8443/admin",
        "https://user:secret@www.job-room.ch/",
    ),
)
async def test_scraper_transport_rejects_every_url_outside_exact_https_origin(url: str) -> None:
    session = ScraperSession(base_url="https://www.job-room.ch")
    client = _FakeClient()
    session.client = client  # type: ignore[assignment]

    with pytest.raises(ValueError, match="provider origin"):
        await session.get(url)

    assert client.requests == []


@pytest.mark.asyncio
async def test_scraper_transport_accepts_paths_on_the_configured_https_origin() -> None:
    session = ScraperSession(base_url="https://www.job-room.ch")
    client = _FakeClient()
    session.client = client  # type: ignore[assignment]

    await session.get("https://www.job-room.ch/jobadservice/api/jobAdvertisements?_ng=ZW4%3D")

    assert client.requests == [
        (
            "GET",
            "https://www.job-room.ch/jobadservice/api/jobAdvertisements?_ng=ZW4%3D",
        )
    ]


@pytest.mark.asyncio
async def test_scraper_transport_refuses_redirects_without_a_second_request() -> None:
    requests: list[httpx.Request] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"Location": "http://127.0.0.1:8000/admin"})

    session = ScraperSession(base_url="https://www.job-room.ch")
    session.client = httpx.AsyncClient(
        transport=httpx.MockTransport(redirect),
        follow_redirects=False,
        trust_env=False,
    )
    try:
        response = await session.get("https://www.job-room.ch/jobadservice/api/jobAdvertisements")
    finally:
        await session.close()

    assert response.status_code == 302
    assert [request.url.host for request in requests] == ["www.job-room.ch"]


@pytest.mark.asyncio
async def test_retry_wrapper_rejects_an_invalid_target_without_retrying_or_network() -> None:
    session = ScraperSession(base_url="https://www.job-room.ch")
    client = _FakeClient()
    session.client = client  # type: ignore[assignment]

    with pytest.raises(ValueError, match="provider origin"):
        await session.with_retry_csrf(
            "GET",
            "http://127.0.0.1:8000/admin",
            "https://www.job-room.ch",
        )

    assert client.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("size_source", ["declared", "buffered"])
async def test_retry_wrapper_rejects_oversized_responses_without_retry(
    size_source: str,
) -> None:
    requests: list[httpx.Request] = []

    def oversized(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if size_source == "declared":
            return httpx.Response(200, headers={"content-length": "5"}, content=b"")
        return httpx.Response(
            200,
            headers={"transfer-encoding": "chunked"},
            content=b"12345",
        )

    session = ScraperSession(
        base_url="https://www.job-room.ch",
        max_response_bytes=4,
    )
    session.client = httpx.AsyncClient(
        transport=httpx.MockTransport(oversized),
        follow_redirects=False,
        trust_env=False,
        event_hooks=session._response_hooks,
    )
    try:
        with pytest.raises(ResponseParseError):
            await session.with_retry_csrf(
                "GET",
                "https://www.job-room.ch/jobadservice/api/jobAdvertisements",
                "https://www.job-room.ch",
            )
    finally:
        await session.close()

    assert len(requests) == 1
