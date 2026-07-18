"""Domain slice extracted from the local AI compatibility pipeline."""

# ruff: noqa: F401

import asyncio
import logging
from typing import Any, Dict, List, Optional

from tenacity import RetryError, retry, retry_if_exception, stop_after_attempt, wait_exponential

from backend.ai.orchestrator import LocalAIOrchestrator, OrchestrationRequest
from backend.core.config import settings
from backend.providers.circuit_breaker import CircuitOpenError, CircuitState, circuit_registry
from backend.providers.llm.factory import get_provider_for_step
from backend.services.search.prompt_compaction import compact_prompt_text
from backend.services.search.query_contracts import (
    compute_plan_input_fingerprint,
    exact_query_fingerprint,
    loose_query_fingerprint,
    normalize_domain,
    normalize_search_item,
    sanitize_prompt_text,
)

logger = logging.getLogger(__name__)

def _is_retryable_plan_error(exc: Exception) -> bool:
    """Return True for transient PLAN-step failures worth retrying."""
    real_exc = exc
    if isinstance(exc, RetryError):
        try:
            candidate = exc.last_attempt.exception()
            if isinstance(candidate, Exception):
                real_exc = candidate
        except Exception:
            pass

    if isinstance(real_exc, (asyncio.TimeoutError, TimeoutError, CircuitOpenError)):
        return True

    error_text = str(real_exc).lower()
    retryable_fragments = (
        "rate limit",
        "timeout",
        "timed out",
        "temporar",
        "connection reset",
        "connection aborted",
        "connection error",
        "502",
        "503",
        "504",
    )
    return any(fragment in error_text for fragment in retryable_fragments)


def _unwrap_retry_error(exc: Exception) -> tuple[Exception, str]:
    """Extract the real cause from a tenacity RetryError and format a message.

    Returns (real_exception, formatted_message) where formatted_message
    includes the HTTP status code when the underlying error is an APIStatusError.
    """
    real_exc = exc
    if isinstance(exc, RetryError):
        try:
            candidate = exc.last_attempt.exception()
            if isinstance(candidate, Exception):
                real_exc = candidate
        except Exception:
            pass
    status_code = getattr(real_exc, "status_code", None)
    msg = str(real_exc)
    if status_code:
        msg = f"HTTP {status_code}: {msg}"
    return real_exc, msg


def _query_fingerprint(search: Dict[str, Any]) -> str:
    return exact_query_fingerprint(search)


class RuntimePolicyMixin:
    def _resolve_step_context_window(self, step: str, provider: Any | None) -> int:
        step_attr = f"LLM_{step.upper()}_CONTEXT_WINDOW"
        step_window = int(getattr(settings, step_attr, 0) or 0)
        if step_window > 0:
            return step_window

        provider_window = getattr(provider, "context_window", 0)
        if isinstance(provider_window, int) and provider_window > 0:
            return provider_window

        global_window = int(getattr(settings, "LLM_CONTEXT_WINDOW", 0) or 0)
        return global_window if global_window > 0 else 0

    def get_step_runtime_policy(self, step: str) -> Dict[str, Any]:
        provider = None
        try:
            provider = self._get_provider(step)
        except Exception as exc:
            logger.warning(
                "[LLM] step=%s could not resolve provider for runtime policy; using settings defaults: %s",
                step,
                exc,
            )
        context_window = self._resolve_step_context_window(step, provider)
        low_context_mode = str(getattr(settings, "SEARCH_LOW_CONTEXT_MODE", "auto") or "auto")
        low_context_mode = low_context_mode.strip().lower()
        threshold = int(
            getattr(settings, "SEARCH_LOW_CONTEXT_CONTEXT_WINDOW_THRESHOLD", 6000) or 6000
        )
        if low_context_mode in {"on", "always", "true", "1"}:
            low_context = True
        elif low_context_mode in {"off", "never", "false", "0"}:
            low_context = False
        else:
            low_context = context_window > 0 and context_window <= threshold

        batch_attr = self._STEP_BATCH_ATTRS.get(step)
        prompt_attr = self._STEP_PROMPT_TARGET_ATTRS.get(step)
        description_attr = self._STEP_DESCRIPTION_TARGET_ATTRS.get(step)

        batch_size = int(getattr(settings, batch_attr, 1) or 1) if batch_attr else 1
        prompt_budget_chars = int(getattr(settings, prompt_attr, 0) or 0) if prompt_attr else 0
        description_limit_chars = (
            int(getattr(settings, description_attr, 0) or 0) if description_attr else 0
        )
        legacy_description_cap = int(getattr(settings, "MAX_DESCRIPTION_CHARS", 0) or 0)
        if description_limit_chars > 0 and legacy_description_cap > 0:
            description_limit_chars = min(description_limit_chars, legacy_description_cap)

        if step == "match" and low_context:
            batch_size = min(
                batch_size,
                int(getattr(settings, "SEARCH_LOW_CONTEXT_ANALYSIS_BATCH_SIZE", 1) or 1),
            )
            prompt_budget_chars = min(
                prompt_budget_chars,
                int(
                    getattr(settings, "SEARCH_LOW_CONTEXT_MATCH_PROMPT_TARGET_CHARS", 3600) or 3600
                ),
            )
            description_limit_chars = min(
                description_limit_chars,
                int(
                    getattr(settings, "SEARCH_LOW_CONTEXT_MATCH_JOB_MAX_DESCRIPTION_CHARS", 900)
                    or 900
                ),
            )
        elif step == "normalize" and low_context:
            batch_size = min(
                batch_size,
                int(getattr(settings, "SEARCH_LOW_CONTEXT_NORMALIZE_BATCH_SIZE", 2) or 2),
            )
            prompt_budget_chars = min(
                prompt_budget_chars,
                int(
                    getattr(settings, "SEARCH_LOW_CONTEXT_NORMALIZE_PROMPT_TARGET_CHARS", 4200)
                    or 4200
                ),
            )
            description_limit_chars = min(
                description_limit_chars,
                int(
                    getattr(
                        settings,
                        "SEARCH_LOW_CONTEXT_NORMALIZE_JOB_MAX_DESCRIPTION_CHARS",
                        1200,
                    )
                    or 1200
                ),
            )

        if context_window > 0 and prompt_budget_chars > 0:
            chars_per_token = float(
                getattr(settings, "LLM_PROMPT_CHARS_PER_TOKEN_ESTIMATE", 3.6) or 3.6
            )
            ratio = float(
                getattr(
                    settings,
                    "SEARCH_LOW_CONTEXT_PROMPT_INPUT_RATIO"
                    if low_context
                    else "SEARCH_STANDARD_PROMPT_INPUT_RATIO",
                    0.28 if low_context else 0.42,
                )
                or (0.28 if low_context else 0.42)
            )
            derived_prompt_budget = max(800, int(context_window * chars_per_token * ratio))
            prompt_budget_chars = min(prompt_budget_chars, derived_prompt_budget)

            if description_limit_chars > 0:
                description_ratio = 0.22 if step == "match" else 0.28
                derived_description_limit = max(
                    300 if step == "match" else 400,
                    int(prompt_budget_chars * description_ratio),
                )
                description_limit_chars = min(description_limit_chars, derived_description_limit)

            if batch_size > 1 and description_limit_chars > 0:
                per_item_cost = description_limit_chars + (900 if step == "match" else 700)
                derived_batch_size = max(1, prompt_budget_chars // max(1, per_item_cost))
                batch_size = min(batch_size, derived_batch_size)

        return {
            "provider": provider,
            "context_window": context_window,
            "low_context": low_context,
            "batch_size": max(1, batch_size),
            "prompt_budget_chars": max(1, prompt_budget_chars) if prompt_budget_chars else 0,
            "description_limit_chars": max(1, description_limit_chars)
            if description_limit_chars
            else 0,
        }

    def _resolve_timeout_override(self, provider: Any, step: str) -> Optional[float]:
        """The local adapter uses the normal per-step timeout from the provider base."""
        del provider, step
        return None

    def _circuit_service_name(self, provider: Any, step: str) -> str:
        return f"{step}:{provider.model_id}"

    def _get_provider(self, step: str):
        if step not in self._provider_cache:
            self._provider_cache[step] = get_provider_for_step(step)
        return self._provider_cache[step]

    def clear_provider_cache(self):
        """Force reload of all LLM providers (e.g. if config changes)."""
        self._provider_cache.clear()

    def is_step_circuit_open(self, step: str) -> bool:
        provider = self._get_provider(step)
        cb = circuit_registry.get(
            self._circuit_service_name(provider, step),
            failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_seconds=float(settings.CIRCUIT_BREAKER_RECOVERY_SECONDS),
        )
        return cb.state == CircuitState.OPEN

    def is_analysis_circuit_open(self) -> bool:
        return self.is_step_circuit_open("match")

    async def _call_provider_json(
        self,
        provider,
        step: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: Optional[int] = None,
        expected_rows: int | None = None,
    ) -> Dict[str, Any]:
        """Invoke one versioned schema task with timeout, validation and one repair.

        Uses the circuit breaker keyed on the provider's model_id so that
        repeated failures trip the breaker and subsequent calls fail fast
        (raising CircuitOpenError) rather than blocking for the full timeout.
        """
        cb = circuit_registry.get(
            self._circuit_service_name(provider, step),
            failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_seconds=float(settings.CIRCUIT_BREAKER_RECOVERY_SECONDS),
        )

        task_by_step = {
            "plan": "search_plan",
            "normalize_profile": "profile_normalize",
            "normalize": "job_normalize",
            "match": "job_match",
            "critique": "job_critique",
            "rerank": "job_rerank",
        }
        task_id = task_by_step.get(step)
        if task_id is None:
            raise ValueError(f"No structured local-AI contract exists for step {step}")

        async def _do_call() -> Dict[str, Any]:
            timeout_override = self._resolve_timeout_override(provider, step)
            timeout_seconds = (
                float(timeout_override)
                if timeout_override is not None
                else float(
                    getattr(
                        settings,
                        {
                            "plan": "LLM_CALL_TIMEOUT_PLAN",
                            "normalize_profile": "LLM_CALL_TIMEOUT_NORMALIZE",
                            "normalize": "LLM_CALL_TIMEOUT_NORMALIZE",
                            "match": "LLM_CALL_TIMEOUT_MATCH",
                            "critique": "LLM_CALL_TIMEOUT_CRITIQUE",
                            "rerank": "LLM_CALL_TIMEOUT_RERANK",
                        }[step],
                    )
                )
            )
            guidance = f"TASK_GUIDANCE:\n{system_prompt}\n\n{user_prompt}"
            result = await asyncio.wait_for(
                LocalAIOrchestrator(provider).execute(
                    OrchestrationRequest(
                        task_id=task_id,
                        user_prompt=guidance,
                        expected_rows=expected_rows,
                    )
                ),
                timeout=timeout_seconds if timeout_seconds > 0 else None,
            )
            return result.output.model_dump(mode="json")

        return await cb.call(_do_call)

    async def _call_provider_text(
        self,
        provider,
        step: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: Optional[int] = None,
    ) -> str:
        cb = circuit_registry.get(
            self._circuit_service_name(provider, step),
            failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_seconds=float(settings.CIRCUIT_BREAKER_RECOVERY_SECONDS),
        )

        async def _do_call() -> str:
            timeout_override = self._resolve_timeout_override(provider, step)
            return await provider.generate_text_async_with_timeout(
                system_prompt,
                user_prompt,
                max_tokens,
                step=step,
                timeout_override=timeout_override,
            )

        return await cb.call(_do_call)
