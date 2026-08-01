from __future__ import annotations

import json
import math
import time
from typing import Any

import httpx

from backend.inference.endpoint import validate_local_inference_url
from backend.inference.http_policy import (
    ASYNC_RESPONSE_HOOKS,
    INFERENCE_TRANSPORT_HEADERS,
    SYNC_RESPONSE_HOOKS,
)
from backend.inference.ports import (
    InferenceUsage,
    StructuredInferenceRequest,
    StructuredInferenceResult,
)
from backend.inference.runtime_schema import runtime_json_schema
from backend.providers.llm.base import LLMProvider, extract_json_payload


class LlamaCppProvider(LLMProvider):
    """Authenticated loopback adapter for the managed llama.cpp server."""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        api_key: str,
        process_id: int | None = None,
        connect_timeout: float = 2.0,
        request_timeout: float = 180.0,
        transport: httpx.BaseTransport | None = None,
        async_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.endpoint = validate_local_inference_url(endpoint)
        self.model = model.strip()
        self.api_key = api_key.strip()
        self.process_id = process_id
        if (
            not self.model
            or len(self.model) > 256
            or any(ord(character) < 32 or ord(character) == 127 for character in self.model)
            or len(self.api_key) < 32
            or len(self.api_key) > 1_024
            or any(ord(character) < 33 or ord(character) == 127 for character in self.api_key)
        ):
            raise ValueError("Managed llama.cpp requires a model alias and launch-scoped API key")
        if process_id is not None and (isinstance(process_id, bool) or process_id < 1):
            raise ValueError("Managed llama.cpp process_id must be a positive integer")
        connect_timeout = float(connect_timeout)
        request_timeout = float(request_timeout)
        if (
            not math.isfinite(connect_timeout)
            or not math.isfinite(request_timeout)
            or connect_timeout <= 0
            or request_timeout <= 0
        ):
            raise ValueError("Local inference timeouts must be finite and greater than zero")
        self.timeout = httpx.Timeout(request_timeout, connect=connect_timeout)
        self.transport = transport
        self.async_transport = async_transport

    @property
    def runtime_name(self) -> str:
        return "llama.cpp"

    @property
    def model_id(self) -> str:
        return f"llama-cpp-local/{self.model}"

    @property
    def runtime_capabilities(self) -> frozenset[str]:
        return frozenset({"json-schema", "usage", "health", "seed"})

    @property
    def _headers(self) -> dict[str, str]:
        return {
            **INFERENCE_TRANSPORT_HEADERS,
            "Authorization": f"Bearer {self.api_key}",
        }

    def _payload(self, request: StructuredInferenceRequest) -> dict[str, Any]:
        return {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            "top_p": request.top_p,
            "seed": request.seed,
            "max_tokens": request.max_tokens,
            "response_format": {
                "type": "json_schema",
                "schema": runtime_json_schema(request.json_schema),
            },
        }

    @staticmethod
    def _response_object(response: httpx.Response) -> dict[str, Any]:
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError as error:
            raise RuntimeError("llama.cpp returned invalid JSON") from error
        if not isinstance(body, dict):
            raise RuntimeError("llama.cpp returned an invalid response envelope")
        return body

    @staticmethod
    def _usage_count(value: Any) -> int | None:
        return (
            value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
        )

    @classmethod
    def _chat_content(cls, response: httpx.Response, *, empty_message: str) -> str:
        body = cls._response_object(response)
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("llama.cpp returned an invalid chat response") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(empty_message)
        return content.strip()

    @classmethod
    def _result(
        cls, response: httpx.Response, *, model_id: str, started: float
    ) -> StructuredInferenceResult:
        body = cls._response_object(response)
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("llama.cpp returned an invalid chat response") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("llama.cpp returned an empty structured response")
        payload = json.loads(extract_json_payload(content))
        if not isinstance(payload, dict):
            raise RuntimeError("llama.cpp structured response must be a JSON object")
        usage = body.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        return StructuredInferenceResult(
            payload=payload,
            model_id=model_id,
            runtime="llama.cpp",
            usage=InferenceUsage(
                prompt_tokens=cls._usage_count(usage.get("prompt_tokens")),
                completion_tokens=cls._usage_count(usage.get("completion_tokens")),
            ),
            duration_ms=max(0, round((time.monotonic() - started) * 1000)),
        )

    async def generate_structured_async(
        self, request: StructuredInferenceRequest
    ) -> StructuredInferenceResult:
        started = time.monotonic()
        async with httpx.AsyncClient(
            base_url=self.endpoint,
            headers=self._headers,
            timeout=self.timeout,
            trust_env=False,
            transport=self.async_transport,
            event_hooks=ASYNC_RESPONSE_HOOKS,
        ) as client:
            response = await client.post("/v1/chat/completions", json=self._payload(request))
        return self._result(response, model_id=self.model_id, started=started)

    async def health_async(self) -> bool:
        async with httpx.AsyncClient(
            base_url=self.endpoint,
            headers=INFERENCE_TRANSPORT_HEADERS,
            timeout=self.timeout,
            trust_env=False,
            transport=self.async_transport,
            event_hooks=ASYNC_RESPONSE_HOOKS,
        ) as client:
            response = await client.get("/health")
        if response.status_code != 200:
            return False
        try:
            body = self._response_object(response)
        except RuntimeError:
            return False
        return body.get("status") == "ok"

    async def list_models_async(self) -> list[str]:
        async with httpx.AsyncClient(
            base_url=self.endpoint,
            headers=self._headers,
            timeout=self.timeout,
            trust_env=False,
            transport=self.async_transport,
            event_hooks=ASYNC_RESPONSE_HOOKS,
        ) as client:
            response = await client.get("/v1/models")
        body = self._response_object(response)
        models = body.get("data")
        if not isinstance(models, list) or len(models) > 10_000:
            raise RuntimeError("llama.cpp returned an invalid model catalog")
        return [str(item["id"]) for item in models if isinstance(item, dict) and item.get("id")]

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens=None) -> str:
        request = StructuredInferenceRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema={"type": "object"},
            max_tokens=4096 if max_tokens is None else int(max_tokens),
        )
        with httpx.Client(
            base_url=self.endpoint,
            headers=self._headers,
            timeout=self.timeout,
            trust_env=False,
            transport=self.transport,
            event_hooks=SYNC_RESPONSE_HOOKS,
        ) as client:
            payload = self._payload(request)
            payload.pop("response_format")
            response = client.post("/v1/chat/completions", json=payload)
        return self._chat_content(
            response,
            empty_message="llama.cpp returned an empty response",
        )

    def generate_json(
        self, system_prompt: str, user_prompt: str, max_tokens=None
    ) -> dict[str, Any]:
        request = StructuredInferenceRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema={"type": "object"},
            max_tokens=4096 if max_tokens is None else int(max_tokens),
        )
        started = time.monotonic()
        with httpx.Client(
            base_url=self.endpoint,
            headers=self._headers,
            timeout=self.timeout,
            trust_env=False,
            transport=self.transport,
            event_hooks=SYNC_RESPONSE_HOOKS,
        ) as client:
            response = client.post("/v1/chat/completions", json=self._payload(request))
        return self._result(response, model_id=self.model_id, started=started).payload
