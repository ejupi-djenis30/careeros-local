"""Shared resource limits for untrusted job-provider HTTP responses."""

from collections.abc import AsyncIterator, Awaitable, Callable

import httpx

from backend.providers.jobs.exceptions import ResponseParseError

MAX_PROVIDER_RESPONSE_BYTES = 8 * 1024 * 1024
_RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


class _BoundedAsyncByteStream(httpx.AsyncByteStream):
    """Stop an async provider body before HTTPX buffers beyond the limit."""

    def __init__(
        self,
        stream: httpx.AsyncByteStream,
        *,
        provider: str,
        max_bytes: int,
    ) -> None:
        self._stream = stream
        self._provider = provider
        self._max_bytes = max_bytes

    async def __aiter__(self) -> AsyncIterator[bytes]:
        received = 0
        async for chunk in self._stream:
            received += len(chunk)
            if received > self._max_bytes:
                raise ResponseParseError(
                    self._provider,
                    "Provider response exceeded the safe size limit",
                )
            yield chunk

    async def aclose(self) -> None:
        await self._stream.aclose()


def _validate_max_bytes(max_bytes: int) -> None:
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")


def _assert_declared_size(
    response: httpx.Response,
    provider: str,
    max_bytes: int,
) -> None:
    headers = getattr(response, "headers", None)
    # Runtime clients always return httpx.Response/httpx.Headers. A few older
    # provider unit tests use lightweight response doubles; the body-limit
    # itself is covered with real responses below this boundary.
    if not isinstance(headers, httpx.Headers):
        return
    raw_length = headers.get("content-length")
    if raw_length is None:
        return
    if not raw_length.isascii() or not raw_length.isdecimal():
        raise ResponseParseError(provider, "Provider response size is invalid")
    # Avoid feeding an attacker-controlled, arbitrarily long decimal string to
    # Python's integer parser. Any value beyond 20 digits already exceeds the
    # supported response bound by many orders of magnitude.
    if len(raw_length) > 20:
        raise ResponseParseError(provider, "Provider response exceeded the safe size limit")
    if int(raw_length, 10) > max_bytes:
        raise ResponseParseError(provider, "Provider response exceeded the safe size limit")


def _assert_identity_encoded(response: httpx.Response, provider: str) -> None:
    headers = getattr(response, "headers", None)
    if not isinstance(headers, httpx.Headers):
        return
    content_encoding = headers.get("content-encoding")
    if content_encoding is not None and content_encoding.strip().lower() != "identity":
        raise ResponseParseError(provider, "Compressed provider responses are not accepted")


def is_retryable_provider_http_error(error: BaseException) -> bool:
    """Retry transport failures and explicitly transient HTTP statuses only."""

    if isinstance(error, httpx.RequestError):
        return True
    return (
        isinstance(error, httpx.HTTPStatusError)
        and error.response.status_code in _RETRYABLE_HTTP_STATUSES
    )


def assert_bounded_provider_response(
    response: httpx.Response,
    provider: str,
    *,
    max_bytes: int = MAX_PROVIDER_RESPONSE_BYTES,
) -> httpx.Response:
    """Reject oversized buffered bodies before JSON parsing or caching."""

    _validate_max_bytes(max_bytes)
    _assert_declared_size(response, provider, max_bytes)
    _assert_identity_encoded(response, provider)
    try:
        content = response.content
    except httpx.ResponseNotRead as error:
        raise ResponseParseError(provider, "Provider response was not buffered") from error
    if isinstance(content, bytes) and len(content) > max_bytes:
        raise ResponseParseError(provider, "Provider response exceeded the safe size limit")
    return response


def provider_response_hooks(
    provider: str,
    *,
    max_bytes: int = MAX_PROVIDER_RESPONSE_BYTES,
) -> dict[str, list[Callable[[httpx.Response], Awaitable[None]]]]:
    """Fail before download when a provider declares an oversized body."""

    _validate_max_bytes(max_bytes)

    async def reject_oversized_declared_body(response: httpx.Response) -> None:
        _assert_declared_size(response, provider, max_bytes)
        _assert_identity_encoded(response, provider)
        if not response.is_stream_consumed:
            if not isinstance(response.stream, httpx.AsyncByteStream):
                raise ResponseParseError(provider, "Provider response stream is invalid")
            response.stream = _BoundedAsyncByteStream(
                response.stream,
                provider=provider,
                max_bytes=max_bytes,
            )

    return {"response": [reject_oversized_declared_body]}
