import json

import httpx
import pytest

from backend.inference.llama_cpp import LlamaCppProvider
from backend.inference.ollama import OllamaProvider
from backend.inference.ports import StructuredInferenceRequest

SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "pattern": "^[a-z]+$",
            "maxLength": 6000,
            "items": {"pattern": "nested"},
        }
    },
    "required": ["answer"],
    "additionalProperties": False,
}
RUNTIME_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string", "items": {}}},
    "required": ["answer"],
    "additionalProperties": False,
}


def _request() -> StructuredInferenceRequest:
    return StructuredInferenceRequest(
        system_prompt="System",
        user_prompt="User",
        json_schema=SCHEMA,
        max_tokens=200,
        temperature=0,
        top_p=0.8,
        seed=7,
        task_id="coach",
    )


@pytest.mark.asyncio
async def test_llama_cpp_uses_authenticated_json_schema_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer " + "k" * 48
        payload = json.loads(request.content)
        assert payload["response_format"] == {
            "type": "json_schema",
            "schema": RUNTIME_SCHEMA,
        }
        assert payload["seed"] == 7
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"answer":"grounded"}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            },
        )

    provider = LlamaCppProvider(
        endpoint="http://127.0.0.1:43001",
        model="compact",
        api_key="k" * 48,
        async_transport=httpx.MockTransport(handler),
    )
    result = await provider.generate_structured_async(_request())

    assert result.payload == {"answer": "grounded"}
    assert result.usage.prompt_tokens == 12
    assert result.runtime == "llama.cpp"
    assert SCHEMA["properties"]["answer"]["pattern"] == "^[a-z]+$"
    assert SCHEMA["properties"]["answer"]["maxLength"] == 6000


@pytest.mark.asyncio
async def test_ollama_uses_native_schema_and_deterministic_options() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["format"] == RUNTIME_SCHEMA
        assert payload["options"]["seed"] == 7
        assert payload["options"]["temperature"] == 0
        assert payload["think"] is False
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"answer":"grounded"}'},
                "prompt_eval_count": 10,
                "eval_count": 3,
            },
        )

    provider = OllamaProvider(
        endpoint="http://127.0.0.1:11434",
        model="compact",
        async_transport=httpx.MockTransport(handler),
    )
    result = await provider.generate_structured_async(_request())

    assert result.payload == {"answer": "grounded"}
    assert result.usage.completion_tokens == 3
    assert result.runtime == "ollama"
    assert SCHEMA["properties"]["answer"]["pattern"] == "^[a-z]+$"
    assert SCHEMA["properties"]["answer"]["maxLength"] == 6000
