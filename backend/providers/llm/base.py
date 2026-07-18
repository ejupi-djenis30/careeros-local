import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Map from step name to the relevant timeout setting attribute.
_STEP_TIMEOUT_ATTRS: dict[str, str] = {
    "plan": "LLM_CALL_TIMEOUT_PLAN",
    "normalize": "LLM_CALL_TIMEOUT_NORMALIZE",
    "normalize_profile": "LLM_CALL_TIMEOUT_NORMALIZE",
    "compress": "LLM_CALL_TIMEOUT_NORMALIZE",
    "match": "LLM_CALL_TIMEOUT_MATCH",
    "critique": "LLM_CALL_TIMEOUT_CRITIQUE",
    "rerank": "LLM_CALL_TIMEOUT_RERANK",
}


def resolve_step_timeout_seconds(step: str, timeout_override: Optional[float] = None) -> float:
    """Resolve the effective timeout budget for a pipeline step."""
    from backend.core.config import settings  # lazy to avoid circular import

    if timeout_override is not None:
        return float(timeout_override)

    timeout_attr = _STEP_TIMEOUT_ATTRS.get(step, "LLM_CALL_TIMEOUT_MATCH")
    return float(getattr(settings, timeout_attr, 0) or 0)


def extract_json_payload(text: str) -> str:
    """Extract the first decodable JSON object/array from model output."""
    text = (text or "").strip()
    if not text:
        return "{}"

    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) > 2 and lines[-1].strip().startswith("```"):
            text = "\n".join(lines[1:-1])
        else:
            lines = [line for line in lines[1:] if line.strip() != "```"]
            text = "\n".join(lines)

    start_idx_dict = text.find("{")
    start_idx_list = text.find("[")

    start_idx = -1
    if start_idx_dict != -1 and start_idx_list != -1:
        start_idx = min(start_idx_dict, start_idx_list)
    else:
        start_idx = max(start_idx_dict, start_idx_list)

    if start_idx > 0:
        text = text[start_idx:]

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch not in "[{":
            continue
        try:
            _, end = decoder.raw_decode(text[idx:])
            return text[idx : idx + end].strip()
        except Exception:
            continue

    end_idx = max(text.rfind("}"), text.rfind("]"))
    if end_idx != -1 and end_idx < len(text) - 1:
        text = text[: end_idx + 1]

    return text.strip() or "{}"


class LLMProvider(ABC):
    """Abstract base for all LLM providers.

    Concrete implementations receive all runtime parameters (model,
    temperature, ...) via their constructor — they must not read from
    ``backend.core.config.settings`` directly.  Parameter resolution is
    handled by the **factory** layer (``get_provider_for_step``).
    """

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Return a human-readable identifier: '<provider>/<model>'"""
        pass

    @abstractmethod
    def generate_text(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> str:
        """Generate text from the LLM"""
        pass

    @abstractmethod
    def generate_json(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """Generate a JSON response from the LLM based on prompts."""
        pass

    async def generate_text_async(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> str:
        """Async version — default falls back to sync via to_thread."""
        return await asyncio.to_thread(self.generate_text, system_prompt, user_prompt, max_tokens)

    async def generate_json_async(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """Async version — default falls back to sync via to_thread."""
        return await asyncio.to_thread(self.generate_json, system_prompt, user_prompt, max_tokens)

    async def generate_structured_async(self, request):
        """Generate schema-bound local output; adapters should override when supported."""
        from backend.inference.ports import (
            StructuredInferenceResult,
        )

        started_at = time.monotonic()
        payload = await self.generate_json_async(
            request.system_prompt,
            request.user_prompt,
            request.max_tokens,
        )
        return StructuredInferenceResult(
            payload=payload,
            model_id=self.model_id,
            runtime=self.model_id.split("/", 1)[0],
            duration_ms=max(0, round((time.monotonic() - started_at) * 1000)),
        )

    async def generate_text_async_with_timeout(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: Optional[int] = None,
        *,
        step: str = "match",
        timeout_override: Optional[float] = None,
    ) -> str:
        """Like ``generate_text_async`` but enforces a per-step call timeout."""
        effective_timeout = resolve_step_timeout_seconds(step, timeout_override)
        coro = self.generate_text_async(system_prompt, user_prompt, max_tokens)
        if effective_timeout <= 0:
            return await coro

        started_at = time.monotonic()
        try:
            return await asyncio.wait_for(coro, timeout=effective_timeout)
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - started_at
            logger.error(
                "LLM text timeout (%.0fs) hit for step=%s model=%s elapsed=%.1fs",
                effective_timeout,
                step,
                self.model_id,
                elapsed,
            )
            raise

    async def generate_json_async_with_timeout(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: Optional[int] = None,
        *,
        step: str = "match",
        timeout_override: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Like ``generate_json_async`` but enforces a per-step call timeout.

        Falls back to ``generate_json_async`` when the effective timeout is 0
        (i.e. disabled).  Raises ``asyncio.TimeoutError`` on breach.
        """
        effective_timeout = resolve_step_timeout_seconds(step, timeout_override)
        coro = self.generate_json_async(system_prompt, user_prompt, max_tokens)
        if effective_timeout <= 0:
            return await coro

        started_at = time.monotonic()
        try:
            return await asyncio.wait_for(coro, timeout=effective_timeout)
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - started_at
            logger.error(
                "LLM call timeout (%.0fs) hit for step=%s model=%s elapsed=%.1fs",
                effective_timeout,
                step,
                self.model_id,
                elapsed,
            )
            raise
