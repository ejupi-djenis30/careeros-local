import httpx
import pytest

from backend.providers.jobs.exceptions import ResponseParseError
from backend.providers.jobs.http_policy import (
    MAX_PROVIDER_RESPONSE_BYTES,
    assert_bounded_provider_response,
    is_retryable_provider_http_error,
    provider_response_hooks,
)


def response(*, body: bytes = b"{}", content_length: str | None = None) -> httpx.Response:
    headers = {} if content_length is None else {"content-length": content_length}
    return httpx.Response(
        200,
        headers=headers,
        content=body,
        request=httpx.Request("GET", "https://provider.example/jobs"),
    )


def test_buffered_provider_response_enforces_declared_and_actual_size() -> None:
    assert assert_bounded_provider_response(response(), "provider").status_code == 200

    with pytest.raises(ResponseParseError):
        assert_bounded_provider_response(
            response(content_length=str(MAX_PROVIDER_RESPONSE_BYTES + 1)),
            "provider",
        )
    with pytest.raises(ResponseParseError):
        assert_bounded_provider_response(
            response(body=b"12345"),
            "provider",
            max_bytes=4,
        )
    with pytest.raises(ResponseParseError):
        assert_bounded_provider_response(
            response(content_length="not-a-number"),
            "provider",
        )


@pytest.mark.parametrize("content_length", ["-1", "+4", " 4", "4, 4"])
def test_declared_provider_size_requires_one_ascii_decimal_value(
    content_length: str,
) -> None:
    with pytest.raises(ResponseParseError):
        assert_bounded_provider_response(
            response(content_length=content_length),
            "provider",
        )


def test_declared_provider_size_rejects_an_unbounded_decimal_without_parsing_it() -> None:
    with pytest.raises(ResponseParseError):
        assert_bounded_provider_response(
            response(content_length="9" * 5_000),
            "provider",
        )


@pytest.mark.asyncio
async def test_response_hook_rejects_declared_size_before_body_download() -> None:
    hook = provider_response_hooks("provider", max_bytes=4)["response"][0]
    oversized = httpx.Response(
        200,
        headers={"content-length": "5"},
        request=httpx.Request("GET", "https://provider.example/jobs"),
    )

    with pytest.raises(ResponseParseError):
        await hook(oversized)


@pytest.mark.asyncio
async def test_response_hook_stops_chunked_body_before_httpx_buffers_the_tail() -> None:
    class ChunkedBody(httpx.AsyncByteStream):
        def __init__(self) -> None:
            self.read_chunks = 0
            self.closed = False

        async def __aiter__(self):
            for chunk in (b"123", b"45", b"tail-must-not-be-read"):
                self.read_chunks += 1
                yield chunk

        async def aclose(self) -> None:
            self.closed = True

    body = ChunkedBody()

    def chunked_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"transfer-encoding": "chunked"},
            stream=body,
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(chunked_response),
        event_hooks=provider_response_hooks("provider", max_bytes=4),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        with pytest.raises(ResponseParseError):
            await client.get("https://provider.example/jobs")

    assert body.read_chunks == 2
    assert body.closed is True


@pytest.mark.asyncio
async def test_response_hook_rejects_encoded_bodies_before_decompression() -> None:
    hook = provider_response_hooks("provider", max_bytes=4)["response"][0]
    compressed = httpx.Response(
        200,
        headers={"content-encoding": "gzip"},
        request=httpx.Request("GET", "https://provider.example/jobs"),
    )

    with pytest.raises(ResponseParseError):
        await hook(compressed)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_response_limits_must_be_positive_integers(value) -> None:
    with pytest.raises(ValueError):
        assert_bounded_provider_response(response(), "provider", max_bytes=value)
    with pytest.raises(ValueError):
        provider_response_hooks("provider", max_bytes=value)


@pytest.mark.parametrize("status_code", [408, 425, 429, 500, 502, 503, 504])
def test_retry_policy_accepts_only_transient_http_statuses(status_code: int) -> None:
    request = httpx.Request("GET", "https://provider.example/jobs")
    response_value = httpx.Response(status_code, request=request)
    assert is_retryable_provider_http_error(
        httpx.HTTPStatusError("transient", request=request, response=response_value)
    )


@pytest.mark.parametrize("status_code", [301, 400, 401, 403, 404, 422])
def test_retry_policy_rejects_permanent_http_statuses(status_code: int) -> None:
    request = httpx.Request("GET", "https://provider.example/jobs")
    response_value = httpx.Response(status_code, request=request)
    assert not is_retryable_provider_http_error(
        httpx.HTTPStatusError("permanent", request=request, response=response_value)
    )


def test_retry_policy_accepts_transport_errors_but_not_parse_errors() -> None:
    request = httpx.Request("GET", "https://provider.example/jobs")
    assert is_retryable_provider_http_error(httpx.ConnectError("offline", request=request))
    assert not is_retryable_provider_http_error(ResponseParseError("provider", "invalid"))
