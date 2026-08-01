import math
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest

from backend.inference.http_policy import (
    MAX_INFERENCE_RESPONSE_BYTES,
    InferenceResponseError,
    bounded_async_response_hook,
    bounded_sync_response_hook,
)
from backend.inference.llama_cpp import LlamaCppProvider
from backend.inference.ollama import OllamaProvider
from backend.inference.ports import (
    InferenceUsage,
    StructuredInferenceRequest,
    StructuredInferenceResult,
)


class _SyncChunks(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        yield from self.chunks

    def close(self) -> None:
        self.closed = True


class _AsyncChunks(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


def _structured_request() -> StructuredInferenceRequest:
    return StructuredInferenceRequest(
        system_prompt="System",
        user_prompt="User",
        json_schema={"type": "object"},
        max_tokens=64,
    )


def test_sync_stream_is_stopped_before_buffering_past_limit() -> None:
    stream = _SyncChunks([b"abc", b"def"])
    response = httpx.Response(200, stream=stream)
    bounded_sync_response_hook(response, max_bytes=5)

    with pytest.raises(InferenceResponseError, match="safe size limit"):
        response.read()

    response.close()
    assert stream.closed is True


@pytest.mark.asyncio
async def test_async_stream_is_stopped_before_buffering_past_limit() -> None:
    stream = _AsyncChunks([b"abc", b"def"])
    response = httpx.Response(200, stream=stream)
    await bounded_async_response_hook(response, max_bytes=5)

    with pytest.raises(InferenceResponseError, match="safe size limit"):
        await response.aread()

    await response.aclose()
    assert stream.closed is True


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Length": str(MAX_INFERENCE_RESPONSE_BYTES + 1)},
        {"Content-Length": "9" * 5_000},
        {"Content-Length": "+100"},
        {"Content-Encoding": "gzip"},
    ],
)
def test_declared_size_and_encoding_are_rejected_before_body_read(headers) -> None:
    response = httpx.Response(200, headers=headers, stream=_SyncChunks([b"{}"]))

    with pytest.raises(InferenceResponseError):
        bounded_sync_response_hook(response)


@pytest.mark.parametrize("max_bytes", [0, -1, True, 1.5])
def test_invalid_response_limit_is_rejected(max_bytes) -> None:
    response = httpx.Response(200, stream=_SyncChunks([b"{}"]))

    with pytest.raises(ValueError, match="positive integer"):
        bounded_sync_response_hook(response, max_bytes=max_bytes)


@pytest.mark.asyncio
async def test_ollama_requests_identity_encoding_and_rejects_oversize_declaration() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(
            200,
            headers={"Content-Length": str(MAX_INFERENCE_RESPONSE_BYTES + 1)},
            stream=_AsyncChunks([b"{}"]),
        )

    provider = OllamaProvider(
        endpoint="http://127.0.0.1:11434",
        model="compact",
        async_transport=httpx.MockTransport(handler),
    )

    with pytest.raises(InferenceResponseError, match="safe size limit"):
        await provider.generate_structured_async(_structured_request())


@pytest.mark.asyncio
async def test_llama_cpp_ignores_invalid_usage_counts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": True, "completion_tokens": -1},
            },
        )

    provider = LlamaCppProvider(
        endpoint="http://127.0.0.1:43001",
        model="compact",
        api_key="k" * 48,
        async_transport=httpx.MockTransport(handler),
    )
    result = await provider.generate_structured_async(_structured_request())

    assert result.usage == InferenceUsage()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"temperature": math.nan},
        {"temperature": math.inf},
        {"temperature": -0.1},
        {"temperature": 2.1},
        {"top_p": math.nan},
        {"top_p": -0.1},
        {"top_p": 1.1},
        {"max_tokens": 0},
        {"max_tokens": 8193},
        {"connect_timeout": math.inf},
        {"request_timeout": 0},
    ],
)
def test_ollama_constructor_rejects_invalid_runtime_limits(kwargs) -> None:
    with pytest.raises(ValueError):
        OllamaProvider(
            endpoint="http://127.0.0.1:11434",
            model="compact",
            **kwargs,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_tokens": 0},
        {"max_tokens": True},
        {"temperature": math.nan},
        {"temperature": 2.1},
        {"top_p": -0.1},
        {"seed": True},
        {"task_id": "bad\nidentifier"},
    ],
)
def test_structured_request_rejects_invalid_contract_values(overrides) -> None:
    values = {
        "system_prompt": "System",
        "user_prompt": "User",
        "json_schema": {"type": "object"},
        "max_tokens": 64,
        **overrides,
    }
    with pytest.raises((TypeError, ValueError)):
        StructuredInferenceRequest(**values)


@pytest.mark.parametrize(
    "usage",
    [
        {"prompt_tokens": -1},
        {"prompt_tokens": True},
        {"completion_tokens": -1},
    ],
)
def test_inference_usage_rejects_invalid_counts(usage) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        InferenceUsage(**usage)


def test_structured_result_rejects_invalid_identity_and_duration() -> None:
    with pytest.raises(ValueError, match="model_id"):
        StructuredInferenceResult(payload={}, model_id="bad\nmodel", runtime="ollama")

    with pytest.raises(ValueError, match="duration"):
        StructuredInferenceResult(
            payload={},
            model_id="ollama/compact",
            runtime="ollama",
            duration_ms=-1,
        )
