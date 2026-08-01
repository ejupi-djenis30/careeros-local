from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.providers.jobs.exceptions import ResponseParseError
from backend.providers.jobs.jobroom.avam_mapper import AVAMProfessionMapper


class _RecordingAsyncClient:
    def __init__(
        self,
        response: httpx.Response,
        options: dict[str, Any],
        calls: list[tuple[str, dict[str, str]]],
        exits: list[bool],
    ) -> None:
        self._response = response
        self._options = options
        self._calls = calls
        self._exits = exits

    async def __aenter__(self) -> "_RecordingAsyncClient":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        self._exits.append(True)

    async def get(self, url: str, *, params: dict[str, str]) -> httpx.Response:
        self._calls.append((url, params))
        return self._response


def _install_client(
    monkeypatch: pytest.MonkeyPatch,
    response: httpx.Response,
) -> tuple[list[dict[str, Any]], list[tuple[str, dict[str, str]]], list[bool]]:
    options: list[dict[str, Any]] = []
    calls: list[tuple[str, dict[str, str]]] = []
    exits: list[bool] = []

    def factory(**kwargs: Any) -> _RecordingAsyncClient:
        options.append(kwargs)
        return _RecordingAsyncClient(response, kwargs, calls, exits)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return options, calls, exits


@pytest.mark.asyncio
@pytest.mark.parametrize("title", ["R&D architect", "C# platform", "Développeuse Zürich"])
async def test_avam_lookup_encodes_title_as_params_and_closes_transport(
    monkeypatch: pytest.MonkeyPatch,
    title: str,
) -> None:
    response = httpx.Response(
        200,
        json=[
            {"type": "AVAM", "code": "20"},
            {"type": "AVAM", "code": "10"},
            {"type": "OTHER", "code": "ignored"},
        ],
        request=httpx.Request("GET", AVAMProfessionMapper._API_URL),
    )
    options, calls, exits = _install_client(monkeypatch, response)

    mapper = AVAMProfessionMapper()
    assert await mapper._fetch_from_api(title) == ["10", "20"]

    assert calls == [
        (
            "https://www.job-room.ch/job-board-api/public/occupations",
            {"prefix": title, "language": "en"},
        )
    ]
    assert options[0]["trust_env"] is False
    assert options[0]["follow_redirects"] is False
    assert options[0]["headers"]["Accept-Encoding"] == "identity"
    assert len(options[0]["event_hooks"]["response"]) == 1
    assert exits == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize("size_source", ["declared", "buffered"])
async def test_avam_oversize_is_closed_and_not_retried(
    monkeypatch: pytest.MonkeyPatch,
    size_source: str,
) -> None:
    if size_source == "declared":
        response = httpx.Response(
            200,
            headers={"content-length": "5"},
            content=b"",
            request=httpx.Request("GET", AVAMProfessionMapper._API_URL),
        )
    else:
        response = httpx.Response(
            200,
            headers={"transfer-encoding": "chunked"},
            content=b"12345",
            request=httpx.Request("GET", AVAMProfessionMapper._API_URL),
        )
    options, calls, exits = _install_client(monkeypatch, response)
    mapper = AVAMProfessionMapper()
    mapper._MAX_RESPONSE_BYTES = 4

    with pytest.raises(ResponseParseError):
        await mapper._fetch_from_api("unmapped & role")

    assert len(options) == 1
    assert len(calls) == 1
    assert exits == [True]


@pytest.mark.asyncio
async def test_avam_cache_refreshes_lru_and_purges_expired_entries() -> None:
    mapper = AVAMProfessionMapper()
    mapper._static_cache = {}
    mapper._api_cache_max_size = 2
    mapper._fetch_from_api = AsyncMock(side_effect=lambda title: [title])

    assert await mapper.resolve("first") == ["first"]
    assert await mapper.resolve("second") == ["second"]
    assert await mapper.resolve("first") == ["first"]
    assert await mapper.resolve("third") == ["third"]

    assert list(mapper._api_cache) == ["first", "third"]
    assert mapper._fetch_from_api.await_count == 3

    mapper._ttl_seconds = 1
    expired_clock = max(cached_at for _, cached_at in mapper._api_cache.values()) + 2
    with patch(
        "backend.providers.jobs.jobroom.avam_mapper.time.monotonic",
        return_value=expired_clock,
    ):
        assert await mapper.resolve("fresh") == ["fresh"]
    assert list(mapper._api_cache) == ["fresh"]


@pytest.mark.asyncio
async def test_avam_whitespace_title_does_not_match_every_static_alias() -> None:
    mapper = AVAMProfessionMapper()
    mapper._fetch_from_api = AsyncMock()

    assert await mapper.resolve("   \t") == []
    mapper._fetch_from_api.assert_not_awaited()


@pytest.mark.asyncio
async def test_avam_failure_emits_one_sanitized_diagnostic() -> None:
    mapper = AVAMProfessionMapper()
    mapper._static_cache = {}
    request = httpx.Request("GET", AVAMProfessionMapper._API_URL)
    mapper._fetch_from_api = AsyncMock(
        side_effect=httpx.ConnectError("private proxy detail", request=request)
    )

    with patch("backend.providers.jobs.jobroom.avam_mapper.log_failure") as log_failure:
        assert await mapper.resolve("unmapped role") == []

    mapper._fetch_from_api.assert_awaited_once()
    log_failure.assert_called_once()
