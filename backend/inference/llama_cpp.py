from __future__ import annotations

import json
import time
from typing import Any

import httpx

from backend.inference.endpoint import validate_local_inference_url
from backend.inference.ports import (
    InferenceUsage,
    StructuredInferenceRequest,
    StructuredInferenceResult,
)
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
        if not self.model or len(self.api_key) < 32:
            raise ValueError("Managed llama.cpp requires a model alias and launch-scoped API key")
        self.timeout = httpx.Timeout(request_timeout, connect=connect_timeout)
        self.transport = transport
        self.async_transport = async_transport

    @property
    def model_id(self) -> str:
        return f"llama-cpp-local/{self.model}"

    @property
    def runtime_capabilities(self) -> frozenset[str]:
        return frozenset({"json-schema", "usage", "health", "seed"})

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

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
            "response_format": {"type": "json_schema", "schema": request.json_schema},
        }

    @staticmethod
    def _result(
        response: httpx.Response, *, model_id: str, started: float
    ) -> StructuredInferenceResult:
        response.raise_for_status()
        body = response.json()
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("llama.cpp returned an invalid chat response") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("llama.cpp returned an empty structured response")
        payload = json.loads(extract_json_payload(content))
        if not isinstance(payload, dict):
            raise RuntimeError("llama.cpp structured response must be a JSON object")
        usage = body.get("usage") or {}
        return StructuredInferenceResult(
            payload=payload,
            model_id=model_id,
            runtime="llama.cpp",
            usage=InferenceUsage(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
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
        ) as client:
            response = await client.post("/v1/chat/completions", json=self._payload(request))
        return self._result(response, model_id=self.model_id, started=started)

    async def health_async(self) -> bool:
        async with httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=self.timeout,
            trust_env=False,
            transport=self.async_transport,
        ) as client:
            response = await client.get("/health")
        return response.status_code == 200 and response.json().get("status") == "ok"

    async def list_models_async(self) -> list[str]:
        async with httpx.AsyncClient(
            base_url=self.endpoint,
            headers=self._headers,
            timeout=self.timeout,
            trust_env=False,
            transport=self.async_transport,
        ) as client:
            response = await client.get("/v1/models")
        response.raise_for_status()
        return [
            str(item["id"])
            for item in response.json().get("data", [])
            if isinstance(item, dict) and item.get("id")
        ]

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens=None) -> str:
        request = StructuredInferenceRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema={"type": "object"},
            max_tokens=int(max_tokens or 4096),
        )
        with httpx.Client(
            base_url=self.endpoint,
            headers=self._headers,
            timeout=self.timeout,
            trust_env=False,
            transport=self.transport,
        ) as client:
            payload = self._payload(request)
            payload.pop("response_format")
            response = client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"])

    def generate_json(
        self, system_prompt: str, user_prompt: str, max_tokens=None
    ) -> dict[str, Any]:
        request = StructuredInferenceRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema={"type": "object"},
            max_tokens=int(max_tokens or 4096),
        )
        started = time.monotonic()
        with httpx.Client(
            base_url=self.endpoint,
            headers=self._headers,
            timeout=self.timeout,
            trust_env=False,
            transport=self.transport,
        ) as client:
            response = client.post("/v1/chat/completions", json=self._payload(request))
        return self._result(response, model_id=self.model_id, started=started).payload
