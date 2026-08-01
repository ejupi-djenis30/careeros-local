"""Resource limits for responses from local inference runtimes."""

from collections.abc import AsyncIterator, Iterator

import httpx

MAX_INFERENCE_RESPONSE_BYTES = 4 * 1024 * 1024
INFERENCE_TRANSPORT_HEADERS = {"Accept-Encoding": "identity"}


class InferenceResponseError(RuntimeError):
    """Raised when a local runtime violates the bounded response contract."""


class _BoundedSyncByteStream(httpx.SyncByteStream):
    def __init__(self, stream: httpx.SyncByteStream, max_bytes: int) -> None:
        self._stream = stream
        self._max_bytes = max_bytes

    def __iter__(self) -> Iterator[bytes]:
        received = 0
        for chunk in self._stream:
            received += len(chunk)
            if received > self._max_bytes:
                raise InferenceResponseError(
                    "Local inference response exceeded the safe size limit"
                )
            yield chunk

    def close(self) -> None:
        self._stream.close()


class _BoundedAsyncByteStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream, max_bytes: int) -> None:
        self._stream = stream
        self._max_bytes = max_bytes

    async def __aiter__(self) -> AsyncIterator[bytes]:
        received = 0
        async for chunk in self._stream:
            received += len(chunk)
            if received > self._max_bytes:
                raise InferenceResponseError(
                    "Local inference response exceeded the safe size limit"
                )
            yield chunk

    async def aclose(self) -> None:
        await self._stream.aclose()


def _validate_max_bytes(max_bytes: int) -> None:
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")


def _validate_response_headers(response: httpx.Response, max_bytes: int) -> None:
    content_encoding = response.headers.get("content-encoding")
    if content_encoding is not None and content_encoding.strip().lower() != "identity":
        raise InferenceResponseError("Compressed local inference responses are not accepted")

    raw_length = response.headers.get("content-length")
    if raw_length is None:
        return
    if not raw_length.isascii() or not raw_length.isdecimal():
        raise InferenceResponseError("Local inference response size is invalid")
    if len(raw_length) > 20 or int(raw_length, 10) > max_bytes:
        raise InferenceResponseError("Local inference response exceeded the safe size limit")


def bounded_sync_response_hook(
    response: httpx.Response,
    *,
    max_bytes: int = MAX_INFERENCE_RESPONSE_BYTES,
) -> None:
    """Reject or bound a sync response before HTTPX buffers its body."""

    _validate_max_bytes(max_bytes)
    _validate_response_headers(response, max_bytes)
    if response.is_stream_consumed:
        if len(response.content) > max_bytes:
            raise InferenceResponseError("Local inference response exceeded the safe size limit")
        return
    if not isinstance(response.stream, httpx.SyncByteStream):
        raise InferenceResponseError("Local inference response stream is invalid")
    response.stream = _BoundedSyncByteStream(response.stream, max_bytes)


async def bounded_async_response_hook(
    response: httpx.Response,
    *,
    max_bytes: int = MAX_INFERENCE_RESPONSE_BYTES,
) -> None:
    """Reject or bound an async response before HTTPX buffers its body."""

    _validate_max_bytes(max_bytes)
    _validate_response_headers(response, max_bytes)
    if response.is_stream_consumed:
        if len(response.content) > max_bytes:
            raise InferenceResponseError("Local inference response exceeded the safe size limit")
        return
    if not isinstance(response.stream, httpx.AsyncByteStream):
        raise InferenceResponseError("Local inference response stream is invalid")
    response.stream = _BoundedAsyncByteStream(response.stream, max_bytes)


SYNC_RESPONSE_HOOKS = {"response": [bounded_sync_response_hook]}
ASYNC_RESPONSE_HOOKS = {"response": [bounded_async_response_hook]}
