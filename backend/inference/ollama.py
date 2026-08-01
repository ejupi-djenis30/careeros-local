import json
import math
import time
from typing import Any, Dict, Optional

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
        if (
            not self.model
            or len(self.model) > 256
            or any(ord(character) < 32 or ord(character) == 127 for character in self.model)
        ):
            raise ValueError("A local model name is required")
        self.temperature = float(temperature)
        self.top_p = float(top_p)
        self.max_tokens = int(max_tokens)
        self.context_window = int(context_window)
        if not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2:
            raise ValueError("Local model temperature must be between 0 and 2")
        if not math.isfinite(self.top_p) or not 0 <= self.top_p <= 1:
            raise ValueError("Local model top_p must be between 0 and 1")
        if self.context_window < 1024:
            raise ValueError("The local model context window must be at least 1024 tokens")
        if self.max_tokens < 1 or self.max_tokens > self.context_window:
            raise ValueError("Local model max_tokens must fit inside the context window")
        connect_timeout = float(connect_timeout)
        request_timeout = float(request_timeout)
        if (
            not math.isfinite(connect_timeout)
            or not math.isfinite(request_timeout)
            or connect_timeout <= 0
            or request_timeout <= 0
        ):
            raise ValueError("Local inference timeouts must be finite and greater than zero")
        self.timeout = httpx.Timeout(
            timeout=request_timeout,
            connect=connect_timeout,
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
            headers=INFERENCE_TRANSPORT_HEADERS,
            timeout=self.timeout,
            trust_env=False,
            transport=self.async_transport,
            event_hooks=ASYNC_RESPONSE_HOOKS,
        ) as client:
            response = await client.post("/api/chat", json=self._structured_payload(request))
        body = self._response_object(response)
        content = self._message_content(
            body,
            empty_message="Local model returned an empty structured response",
        )
        parsed = json.loads(extract_json_payload(content))
        if not isinstance(parsed, dict):
            raise RuntimeError("Local model structured response must be a JSON object")
        return StructuredInferenceResult(
            payload=parsed,
            model_id=self.model_id,
            runtime="ollama",
            usage=InferenceUsage(
                prompt_tokens=self._usage_count(body.get("prompt_eval_count")),
                completion_tokens=self._usage_count(body.get("eval_count")),
            ),
            duration_ms=max(0, round((time.monotonic() - started) * 1000)),
        )

    def _payload(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int]) -> dict:
        if not isinstance(system_prompt, str) or not isinstance(user_prompt, str):
            raise TypeError("Local inference prompts must be strings")
        effective_max_tokens = self.max_tokens if max_tokens is None else int(max_tokens)
        if effective_max_tokens < 1 or effective_max_tokens > self.context_window:
            raise ValueError("Requested max_tokens must fit inside the context window")
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
                "num_predict": effective_max_tokens,
                "num_ctx": self.context_window,
            },
        }

    @staticmethod
    def _response_object(response: httpx.Response) -> dict[str, Any]:
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as error:
            raise RuntimeError("Local model returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise RuntimeError("Local model returned an invalid response envelope")
        return payload

    @staticmethod
    def _message_content(payload: dict[str, Any], *, empty_message: str) -> str:
        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(empty_message)
        return content.strip()

    @classmethod
    def _content(cls, response: httpx.Response) -> str:
        return cls._message_content(
            cls._response_object(response),
            empty_message="Local model returned an empty response",
        )

    @staticmethod
    def _usage_count(value: Any) -> int | None:
        return (
            value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
        )

    def generate_text(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> str:
        with httpx.Client(
            base_url=self.endpoint,
            headers=INFERENCE_TRANSPORT_HEADERS,
            timeout=self.timeout,
            trust_env=False,
            transport=self.transport,
            event_hooks=SYNC_RESPONSE_HOOKS,
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
            headers=INFERENCE_TRANSPORT_HEADERS,
            timeout=self.timeout,
            trust_env=False,
            transport=self.transport,
            event_hooks=SYNC_RESPONSE_HOOKS,
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
            headers=INFERENCE_TRANSPORT_HEADERS,
            timeout=self.timeout,
            trust_env=False,
            transport=self.async_transport,
            event_hooks=ASYNC_RESPONSE_HOOKS,
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
            headers=INFERENCE_TRANSPORT_HEADERS,
            timeout=self.timeout,
            trust_env=False,
            transport=self.async_transport,
            event_hooks=ASYNC_RESPONSE_HOOKS,
        ) as client:
            response = await client.post("/api/chat", json=payload)
        parsed = json.loads(extract_json_payload(self._content(response)))
        if not isinstance(parsed, dict):
            raise RuntimeError("Local model JSON response must be an object")
        return parsed

    def list_models(self) -> list[str]:
        with httpx.Client(
            base_url=self.endpoint,
            headers=INFERENCE_TRANSPORT_HEADERS,
            timeout=self.timeout,
            trust_env=False,
            transport=self.transport,
            event_hooks=SYNC_RESPONSE_HOOKS,
        ) as client:
            response = client.get("/api/tags")
        body = self._response_object(response)
        models = body.get("models")
        if not isinstance(models, list) or len(models) > 10_000:
            raise RuntimeError("Local model returned an invalid model catalog")
        return [str(item["name"]) for item in models if isinstance(item, dict) and item.get("name")]

    async def list_models_async(self) -> list[str]:
        async with httpx.AsyncClient(
            base_url=self.endpoint,
            headers=INFERENCE_TRANSPORT_HEADERS,
            timeout=self.timeout,
            trust_env=False,
            transport=self.async_transport,
            event_hooks=ASYNC_RESPONSE_HOOKS,
        ) as client:
            response = await client.get("/api/tags")
        body = self._response_object(response)
        models = body.get("models")
        if not isinstance(models, list) or len(models) > 10_000:
            raise RuntimeError("Local model returned an invalid model catalog")
        return [str(item["name"]) for item in models if isinstance(item, dict) and item.get("name")]
