import json
import time
from typing import Any, Dict, Optional

import httpx

from backend.inference.endpoint import validate_local_inference_url
from backend.inference.ports import (
    InferenceUsage,
    StructuredInferenceRequest,
    StructuredInferenceResult,
)
from backend.inference.runtime_schema import runtime_json_schema
from backend.providers.llm.base import LLMProvider, extract_json_payload


class OllamaProvider(LLMProvider):
    """Native Ollama adapter with no credential or non-local escape hatch."""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        allowed_hosts: Optional[set[str]] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        max_tokens: int = 4096,
        context_window: int = 8192,
        connect_timeout: float = 2.0,
        request_timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
        async_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.endpoint = validate_local_inference_url(endpoint, allowed_hosts=allowed_hosts)
        self.model = model.strip()
        if not self.model:
            raise ValueError("A local model name is required")
        self.temperature = float(temperature)
        self.top_p = float(top_p)
        self.max_tokens = int(max_tokens)
        self.context_window = int(context_window)
        if self.context_window < 1024:
            raise ValueError("The local model context window must be at least 1024 tokens")
        self.timeout = httpx.Timeout(
            timeout=float(request_timeout),
            connect=float(connect_timeout),
        )
        self.transport = transport
        self.async_transport = async_transport

    @property
    def runtime_name(self) -> str:
        return "ollama"

    @property
    def model_id(self) -> str:
        return f"ollama-local/{self.model}"

    @property
    def runtime_capabilities(self) -> frozenset[str]:
        return frozenset({"json-schema", "usage", "seed"})

    def _structured_payload(self, request: StructuredInferenceRequest) -> dict[str, Any]:
        payload = self._payload(request.system_prompt, request.user_prompt, request.max_tokens)
        payload["format"] = runtime_json_schema(request.json_schema)
        payload["options"].update(
            {
                "temperature": request.temperature,
                "top_p": request.top_p,
                "seed": request.seed,
            }
        )
        return payload

    async def generate_structured_async(
        self, request: StructuredInferenceRequest
    ) -> StructuredInferenceResult:
        started = time.monotonic()
        async with httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=self.timeout,
            trust_env=False,
            transport=self.async_transport,
        ) as client:
            response = await client.post("/api/chat", json=self._structured_payload(request))
        response.raise_for_status()
        body = response.json()
        content = body.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Local model returned an empty structured response")
        parsed = json.loads(extract_json_payload(content))
        if not isinstance(parsed, dict):
            raise RuntimeError("Local model structured response must be a JSON object")
        return StructuredInferenceResult(
            payload=parsed,
            model_id=self.model_id,
            runtime="ollama",
            usage=InferenceUsage(
                prompt_tokens=body.get("prompt_eval_count"),
                completion_tokens=body.get("eval_count"),
            ),
            duration_ms=max(0, round((time.monotonic() - started) * 1000)),
        )

    def _payload(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int]) -> dict:
        return {
            "model": self.model,
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "num_predict": int(max_tokens or self.max_tokens),
                "num_ctx": self.context_window,
            },
        }

    @staticmethod
    def _content(response: httpx.Response) -> str:
        response.raise_for_status()
        payload = response.json()
        content = payload.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Local model returned an empty response")
        return content.strip()

    def generate_text(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> str:
        with httpx.Client(
            base_url=self.endpoint,
            timeout=self.timeout,
            trust_env=False,
            transport=self.transport,
        ) as client:
            response = client.post(
                "/api/chat", json=self._payload(system_prompt, user_prompt, max_tokens)
            )
        return self._content(response)

    def generate_json(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        payload = self._payload(system_prompt, user_prompt, max_tokens)
        payload["format"] = "json"
        with httpx.Client(
            base_url=self.endpoint,
            timeout=self.timeout,
            trust_env=False,
            transport=self.transport,
        ) as client:
            response = client.post("/api/chat", json=payload)
        parsed = json.loads(extract_json_payload(self._content(response)))
        if not isinstance(parsed, dict):
            raise RuntimeError("Local model JSON response must be an object")
        return parsed

    async def generate_text_async(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> str:
        async with httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=self.timeout,
            trust_env=False,
            transport=self.async_transport,
        ) as client:
            response = await client.post(
                "/api/chat", json=self._payload(system_prompt, user_prompt, max_tokens)
            )
        return self._content(response)

    async def generate_json_async(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        payload = self._payload(system_prompt, user_prompt, max_tokens)
        payload["format"] = "json"
        async with httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=self.timeout,
            trust_env=False,
            transport=self.async_transport,
        ) as client:
            response = await client.post("/api/chat", json=payload)
        parsed = json.loads(extract_json_payload(self._content(response)))
        if not isinstance(parsed, dict):
            raise RuntimeError("Local model JSON response must be an object")
        return parsed

    def list_models(self) -> list[str]:
        with httpx.Client(
            base_url=self.endpoint,
            timeout=self.timeout,
            trust_env=False,
            transport=self.transport,
        ) as client:
            response = client.get("/api/tags")
        response.raise_for_status()
        return [
            str(item["name"])
            for item in response.json().get("models", [])
            if isinstance(item, dict) and item.get("name")
        ]

    async def list_models_async(self) -> list[str]:
        async with httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=self.timeout,
            trust_env=False,
            transport=self.async_transport,
        ) as client:
            response = await client.get("/api/tags")
        response.raise_for_status()
        return [
            str(item["name"])
            for item in response.json().get("models", [])
            if isinstance(item, dict) and item.get("name")
        ]
