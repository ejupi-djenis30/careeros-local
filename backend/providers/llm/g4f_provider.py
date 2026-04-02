import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

from backend.providers.llm.base import (
    LLMProvider,
    extract_json_payload,
    resolve_step_timeout_seconds,
)

logger = logging.getLogger(__name__)


class G4FProviderError(RuntimeError):
    """Base error raised by the g4f provider integration."""


class G4FInitializationError(G4FProviderError):
    """Raised when g4f cannot bootstrap a usable client or provider chain."""


class G4FProvider(LLMProvider):
    """LLM provider backed by the gpt4free (g4f) client library."""

    _DEFAULT_COOKIES_DIR = Path(__file__).resolve().parents[3] / "data" / "g4f" / "har_and_cookies"
    _DEFAULT_PROVIDER_CANDIDATES = (
        "DeepInfra",
        "PollinationsAI",
        "HuggingFace",
        "Groq",
        "Chatai",
        "Qwen",
        "GeminiPro",
        "LMArena",
        "MetaAI",
        "ItalyGPT",
        "Yqcloud",
    )
    _EXCLUDED_PROVIDER_NAMES = {
        "AnyProvider",
        "Custom",
        "Ollama",
        "Azure",
        "CachedSearch",
        "provider",
        "HuggingFace",
        "Chatai",
    }
    _EXCLUDED_PROVIDER_KEYWORDS = (
        "Image",
        "Images",
        "Search",
        "TTS",
        "Flux",
        "Media",
        "Audio",
        "Create",
    )
    _AUTO_PROVIDER_LIMIT = 6
    _RETRY_DELAY_SECONDS = 0.15
    _MAX_RETRY_BACKOFF_SECONDS = 1.0

    def __init__(
        self,
        *,
        model: str = "",
        api_key: str = "",
        base_url: str = "",
        providers_list: Optional[list[str]] = None,
        proxies: str = "",
        temperature: float = 0.7,
        top_p: float = 0.95,
        max_tokens: int = 16384,
        max_request_attempts: int = 2,
        request_timeout_cap_seconds: float = 20.0,
        timeout_buffer_seconds: float = 1.0,
        rate_limit_wait_seconds: float = 3600.0,
        shuffle_providers: bool = True,
        cookies_dir: Optional[str] = None,
        allow_auto_discovery: bool = True,
        allow_internal_provider_fallback: bool = False,
    ):
        try:
            from g4f import Provider as provider_module
            from g4f.client import AsyncClient, Client, ClientFactory
            from g4f.cookies import read_cookie_files, set_cookies_dir
        except ImportError:
            logger.error("g4f package not installed")
            raise

        self.model = model or ""
        self.api_key = api_key or ""
        self.base_url = base_url or ""
        self.proxies = proxies or ""
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.max_request_attempts = max(1, int(max_request_attempts))
        self.request_timeout_cap_seconds = max(0.0, float(request_timeout_cap_seconds))
        self.timeout_buffer_seconds = max(0.0, float(timeout_buffer_seconds))
        self.rate_limit_wait_seconds = max(0.0, float(rate_limit_wait_seconds))
        self.shuffle_providers = shuffle_providers
        self.allow_auto_discovery = allow_auto_discovery
        self.allow_internal_provider_fallback = allow_internal_provider_fallback
        self.cookies_dir = str(Path(cookies_dir) if cookies_dir else self._DEFAULT_COOKIES_DIR)
        self._provider_selection_mode = "explicit"

        self._configure_cookie_storage(set_cookies_dir, read_cookie_files)

        self._provider_module = provider_module
        self._client_factory = ClientFactory
        self._client_cls = Client
        self._async_client_cls = AsyncClient
        self.provider_names = self._resolve_provider_names(providers_list)
        self._provider = self._resolve_provider()

        client_kwargs = self._build_client_kwargs()
        self.client = self._client_cls(provider=self._provider, **client_kwargs)
        self.async_client = self._async_client_cls(provider=self._provider, **client_kwargs)

    @property
    def model_id(self) -> str:
        model_part = self.model or "auto"
        if self.provider_names:
            return f"g4f[{','.join(self.provider_names)}]/{model_part}"
        return f"g4f/{model_part}"

    def _configure_cookie_storage(self, set_cookies_dir, read_cookie_files) -> None:
        cookies_path = Path(self.cookies_dir)
        try:
            cookies_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise G4FInitializationError(
                f"Unable to prepare g4f cookie directory '{cookies_path}': {exc}"
            ) from exc

        try:
            set_cookies_dir(str(cookies_path))
            read_cookie_files(str(cookies_path))
        except PermissionError as exc:
            raise G4FInitializationError(
                f"Unable to access g4f cookie directory '{cookies_path}': {exc}"
            ) from exc
        except OSError as exc:
            raise G4FInitializationError(
                f"Unable to initialize g4f cookies from '{cookies_path}': {exc}"
            ) from exc
        except Exception as exc:
            logger.warning("Failed to preload g4f cookies from %s: %s", cookies_path, exc)

    def _resolve_provider_names(self, providers_list: Optional[list[str]]) -> list[str]:
        normalized_names: list[str] = []
        seen_names: set[str] = set()

        for raw_name in providers_list or []:
            name = (raw_name or "").strip()
            name_key = name.lower()
            if not name or name_key in seen_names:
                continue
            seen_names.add(name_key)
            normalized_names.append(name)

        if normalized_names:
            self._provider_selection_mode = "explicit"
            return normalized_names

        if not self.allow_auto_discovery:
            if self.allow_internal_provider_fallback:
                self._provider_selection_mode = "internal"
                logger.warning(
                    "G4F provider auto-discovery is disabled and G4F_PROVIDERS is empty; using g4f internal provider selection."
                )
                return []
            raise G4FInitializationError(
                "G4F_PROVIDERS is empty while G4F_AUTO_DISCOVER_PROVIDERS is disabled. "
                "Configure G4F_PROVIDERS or LLM_FALLBACK_PROVIDER."
            )

        discovered_names = self._discover_provider_names()
        if discovered_names:
            self._provider_selection_mode = "auto"
            logger.info("G4F auto-selected provider chain: %s", ", ".join(discovered_names))
            return discovered_names

        if self.allow_internal_provider_fallback:
            self._provider_selection_mode = "internal"
            logger.warning(
                "No stable unauthenticated g4f providers were auto-discovered; using g4f internal provider selection."
            )
            return []

        raise G4FInitializationError(
            "No stable unauthenticated g4f providers were auto-discovered. "
            "Configure G4F_PROVIDERS, enable G4F_ALLOW_INTERNAL_PROVIDER_FALLBACK, "
            "or configure LLM_FALLBACK_PROVIDER."
        )

    def _discover_provider_names(self) -> list[str]:
        discovered_names: list[str] = []

        for provider_name in self._DEFAULT_PROVIDER_CANDIDATES:
            if not self._is_provider_candidate(provider_name):
                continue
            discovered_names.append(provider_name)
            if len(discovered_names) >= self._AUTO_PROVIDER_LIMIT:
                return discovered_names

        for provider_name in dir(self._provider_module):
            if provider_name in discovered_names or not self._is_provider_candidate(provider_name):
                continue
            discovered_names.append(provider_name)
            if len(discovered_names) >= self._AUTO_PROVIDER_LIMIT:
                return discovered_names

        return discovered_names

    def _is_provider_candidate(self, provider_name: str) -> bool:
        if provider_name in self._EXCLUDED_PROVIDER_NAMES:
            return False

        lowered_name = provider_name.lower()
        if any(keyword.lower() in lowered_name for keyword in self._EXCLUDED_PROVIDER_KEYWORDS):
            return False

        provider = getattr(self._provider_module, provider_name, None)
        if not isinstance(provider, type):
            return False

        if not getattr(provider, "working", False):
            return False

        if getattr(provider, "needs_auth", False):
            return False

        return bool(getattr(provider, "supports_stream", True))

    def _build_client_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.base_url:
            kwargs["base_url"] = self.base_url
        if self.proxies:
            kwargs["proxy"] = self.proxies
        return kwargs

    def _build_call_deadline(self, timeout_override: Optional[float]) -> Optional[float]:
        if timeout_override is None:
            return None

        effective_budget = float(timeout_override) - self.timeout_buffer_seconds
        return time.monotonic() + max(0.0, effective_budget)

    def _remaining_budget_seconds(self, call_deadline: Optional[float]) -> Optional[float]:
        if call_deadline is None:
            return None
        return max(0.0, call_deadline - time.monotonic())

    def _compute_attempt_timeout(self, call_deadline: Optional[float] = None) -> Optional[float]:
        timeout_cap = (
            self.request_timeout_cap_seconds if self.request_timeout_cap_seconds > 0 else None
        )
        remaining_budget = self._remaining_budget_seconds(call_deadline)
        if remaining_budget is None:
            return timeout_cap
        if remaining_budget <= 0:
            return 0.0
        if timeout_cap is None:
            return remaining_budget
        return min(timeout_cap, remaining_budget)

    def _is_rate_limit_error(self, error_text: str) -> bool:
        text = error_text.lower()
        return any(
            fragment in text
            for fragment in (
                "request limit",
                "rate limit",
                "per hour",
                "too many requests",
                "429",
            )
        )

    def _compute_backoff_seconds(self, attempt: int, exc: Optional[Exception] = None) -> float:
        if exc is not None and self._is_rate_limit_error(str(exc)):
            return self.rate_limit_wait_seconds
        return min(
            self._MAX_RETRY_BACKOFF_SECONDS,
            (self._RETRY_DELAY_SECONDS * attempt) + (0.05 * max(0, attempt - 1)),
        )

    def _log_async_attempt_result(
        self,
        *,
        phase: str,
        attempt: int,
        attempt_timeout: Optional[float],
        elapsed: float,
        exc: Optional[Exception] = None,
    ) -> None:
        timeout_repr = f"{attempt_timeout:.1f}s" if attempt_timeout is not None else "disabled"
        if exc is None:
            logger.debug(
                "Async G4F %s succeeded for %s on attempt %s/%s in %.2fs (attempt_timeout=%s, selection=%s).",
                phase,
                self.model_id,
                attempt,
                self.max_request_attempts,
                elapsed,
                timeout_repr,
                self._provider_selection_mode,
            )
            return

        logger.warning(
            "Async G4F %s failed for %s on attempt %s/%s after %.2fs (attempt_timeout=%s, selection=%s): %s",
            phase,
            self.model_id,
            attempt,
            self.max_request_attempts,
            elapsed,
            timeout_repr,
            self._provider_selection_mode,
            exc,
        )

    def _resolve_provider(self):
        if not self.provider_names:
            if self._provider_selection_mode == "internal":
                return None
            raise G4FInitializationError("No g4f providers are available after selection.")

        explicit_config = self._provider_selection_mode == "explicit"

        resolved_providers = []
        for provider_name in self.provider_names:
            try:
                provider = getattr(self._provider_module, provider_name, None)
                if provider is None:
                    provider = self._client_factory.create_provider(
                        provider_name,
                        provider_name,
                        base_url=self.base_url or None,
                        api_key=self.api_key or None,
                    )
                resolved_providers.append(provider)
            except Exception as exc:
                logger.warning("Skipping unavailable g4f provider '%s': %s", provider_name, exc)

        if not resolved_providers:
            if not explicit_config and self.allow_internal_provider_fallback:
                logger.warning(
                    "Could not resolve any configured g4f providers from %s; using g4f internal selection.",
                    self.provider_names,
                )
                self._provider_selection_mode = "internal"
                return None

            configured_source = "configured" if explicit_config else "auto-discovered"
            raise G4FInitializationError(
                f"None of the {configured_source} g4f providers could be initialized: {self.provider_names}. "
                "Adjust G4F_PROVIDERS or configure LLM_FALLBACK_PROVIDER."
            )

        if explicit_config and len(resolved_providers) < len(self.provider_names):
            logger.warning(
                "Only %s/%s configured g4f providers could be initialized for %s.",
                len(resolved_providers),
                len(self.provider_names),
                self.model_id,
            )

        if len(resolved_providers) == 1:
            return resolved_providers[0]

        retry_provider = getattr(self._provider_module, "RetryProvider", None)
        if retry_provider is None:
            logger.warning("g4f RetryProvider unavailable; using first resolved provider only.")
            return resolved_providers[0]
        return retry_provider(resolved_providers, shuffle=self.shuffle_providers)

    def _build_completion_kwargs(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: Optional[int],
        *,
        response_format: Optional[dict] = None,
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        if self.model:
            kwargs["model"] = self.model
        if self.proxies:
            kwargs["proxy"] = self.proxies
        if response_format is not None:
            kwargs["response_format"] = response_format
            combined_prompt = f"{system_prompt}\n{user_prompt}".lower()
            if "json" not in combined_prompt:
                kwargs["messages"][0]["content"] = system_prompt + "\nRespond with valid JSON."
        return kwargs

    def _extract_content(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("content") or ""))
                else:
                    parts.append(str(item))
            return "".join(parts)
        if isinstance(value, dict):
            return str(value.get("text") or value.get("content") or value)
        return str(value)

    def _get_message_content(self, response: Any) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""

        choice = choices[0]
        message = getattr(choice, "message", None)
        if message is not None:
            reasoning = getattr(message, "reasoning", None) or getattr(
                message, "reasoning_content", None
            )
            if reasoning:
                logger.debug("G4F reasoning trace (%s): %s", self.model_id, str(reasoning)[:200])

            content = self._extract_content(getattr(message, "content", None))
            if content:
                return content

        delta = getattr(choice, "delta", None)
        if delta is not None:
            content = self._extract_content(getattr(delta, "content", None))
            if content:
                return content

        return self._extract_content(getattr(choice, "text", None))

    def _parse_json_content(self, content: str) -> Dict[str, Any]:
        clean_text = extract_json_payload(content)
        try:
            return json.loads(clean_text)
        except Exception as parse_err:
            logger.error(
                "Failed to parse JSON from %s. Raw output:\n%s\nCleaned:\n%s",
                self.model_id,
                content,
                clean_text,
            )
            raise parse_err

    def _should_retry_request(self, exc: Exception, params: Dict[str, Any]) -> bool:
        error_text = str(exc).lower()

        if "response_format" in params and "response_format" in error_text:
            return False

        if "model" in params and params.get("model") and "model" in error_text:
            if any(fragment in error_text for fragment in ("unsupported", "unknown", "not found")):
                return False

        # Auth failures are permanent — retrying the same provider won't fix them.
        if any(
            fragment in error_text
            for fragment in ("401", "403", "unauthorized", "forbidden", "not authorized")
        ):
            return False

        return True

    def _create_completion(self, params: Dict[str, Any]) -> Any:
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_request_attempts + 1):
            try:
                return self.client.chat.completions.create(**params)
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_request_attempts or not self._should_retry_request(
                    exc, params
                ):
                    break
                logger.warning(
                    "G4F request failed on attempt %s/%s for %s (%s). Retrying.",
                    attempt,
                    self.max_request_attempts,
                    self.model_id,
                    exc,
                )
                backoff = self._compute_backoff_seconds(attempt, exc=exc)
                if backoff > 60:
                    logger.warning(
                        "G4F rate limit detected (%s); waiting %.0fs (%.1f min) for provider "
                        "quota reset before attempt %s/%s.",
                        self.model_id,
                        backoff,
                        backoff / 60,
                        attempt + 1,
                        self.max_request_attempts,
                    )
                time.sleep(backoff)

        if last_error is not None:
            raise last_error
        raise RuntimeError("G4F request failed without raising an exception.")

    async def _create_completion_async(
        self,
        params: Dict[str, Any],
        *,
        phase: str = "text",
        timeout_override: Optional[float] = None,
        call_deadline: Optional[float] = None,
    ) -> Any:
        last_error: Optional[Exception] = None
        if call_deadline is None:
            call_deadline = self._build_call_deadline(timeout_override)
        for attempt in range(1, self.max_request_attempts + 1):
            attempt_timeout = self._compute_attempt_timeout(call_deadline)
            if attempt_timeout is not None and attempt_timeout <= 0:
                raise asyncio.TimeoutError(
                    f"Async G4F {phase} exceeded timeout budget for {self.model_id} "
                    f"before attempt {attempt}/{self.max_request_attempts}."
                )
            started_at = time.monotonic()
            try:
                response_coro = self.async_client.chat.completions.create(**params)
                if attempt_timeout is None:
                    response = await response_coro
                else:
                    response = await asyncio.wait_for(response_coro, timeout=attempt_timeout)
                self._log_async_attempt_result(
                    phase=phase,
                    attempt=attempt,
                    attempt_timeout=attempt_timeout,
                    elapsed=time.monotonic() - started_at,
                )
                return response
            except Exception as exc:
                last_error = exc
                self._log_async_attempt_result(
                    phase=phase,
                    attempt=attempt,
                    attempt_timeout=attempt_timeout,
                    elapsed=time.monotonic() - started_at,
                    exc=exc,
                )
                if attempt >= self.max_request_attempts or not self._should_retry_request(
                    exc, params
                ):
                    break
                backoff = self._compute_backoff_seconds(attempt, exc=exc)
                remaining_budget = self._remaining_budget_seconds(call_deadline)
                if remaining_budget is not None:
                    if remaining_budget <= 0:
                        raise asyncio.TimeoutError(
                            f"Async G4F {phase} exceeded timeout budget for {self.model_id} "
                            f"after attempt {attempt}/{self.max_request_attempts}."
                        ) from exc
                    if backoff > remaining_budget:
                        logger.warning(
                            "Async G4F %s cannot wait %.1fs retry backoff for %s with only %.1fs remaining; aborting to honor timeout budget.",
                            phase,
                            backoff,
                            self.model_id,
                            remaining_budget,
                        )
                        raise asyncio.TimeoutError(
                            f"Async G4F {phase} retry backoff {backoff:.1f}s exceeded remaining timeout budget {remaining_budget:.1f}s for {self.model_id}."
                        ) from exc
                if backoff <= 0:
                    break
                if backoff > 60:
                    logger.warning(
                        "G4F rate limit detected (%s); waiting %.0fs (%.1f min) for provider "
                        "quota reset before attempt %s/%s.",
                        self.model_id,
                        backoff,
                        backoff / 60,
                        attempt + 1,
                        self.max_request_attempts,
                    )
                await asyncio.sleep(backoff)

        if last_error is not None:
            raise last_error
        raise RuntimeError("Async G4F request failed without raising an exception.")

    def generate_text(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> str:
        params = self._build_completion_kwargs(system_prompt, user_prompt, max_tokens)
        try:
            response = self._create_completion(params)
            return self._get_message_content(response)
        except Exception as exc:
            logger.error("G4F text error (%s): %s", self.model_id, exc)
            raise

    def generate_json(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        params = self._build_completion_kwargs(
            system_prompt,
            user_prompt,
            max_tokens,
            response_format={"type": "json_object"},
        )
        last_error: Optional[Exception] = None

        for use_response_format in (True, False):
            current_params: Dict[str, Any] = dict(params)
            if not use_response_format:
                if "response_format" in current_params:
                    del current_params["response_format"]

            try:
                response = self._create_completion(current_params)
                return self._parse_json_content(self._get_message_content(response))
            except Exception as exc:
                last_error = exc
                if use_response_format:
                    logger.warning(
                        "G4F JSON structured mode failed for %s (%s). Retrying without response_format.",
                        self.model_id,
                        exc,
                    )
                    continue
                logger.error("G4F JSON error (%s): %s", self.model_id, exc)
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("G4F JSON generation failed without raising an exception.")

    async def generate_text_async(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> str:
        params = self._build_completion_kwargs(system_prompt, user_prompt, max_tokens)
        try:
            response = await self._create_completion_async(params)
            return self._get_message_content(response)
        except Exception as exc:
            logger.error("Async G4F text error (%s): %s", self.model_id, exc)
            raise

    async def generate_text_async_with_timeout(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: Optional[int] = None,
        *,
        step: str = "match",
        timeout_override: Optional[float] = None,
    ) -> str:
        params = self._build_completion_kwargs(system_prompt, user_prompt, max_tokens)
        effective_timeout = resolve_step_timeout_seconds(step, timeout_override)
        call_deadline = (
            self._build_call_deadline(effective_timeout) if effective_timeout > 0 else None
        )
        try:
            response = await self._create_completion_async(
                params,
                phase=f"{step}:text",
                call_deadline=call_deadline,
            )
            return self._get_message_content(response)
        except Exception as exc:
            logger.error("Async G4F text error (%s): %s", self.model_id, exc)
            raise

    async def generate_json_async(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        params = self._build_completion_kwargs(
            system_prompt,
            user_prompt,
            max_tokens,
            response_format={"type": "json_object"},
        )
        last_error: Optional[Exception] = None

        for use_response_format in (True, False):
            current_params: Dict[str, Any] = dict(params)
            if not use_response_format:
                if "response_format" in current_params:
                    del current_params["response_format"]

            try:
                response = await self._create_completion_async(current_params)
                return self._parse_json_content(self._get_message_content(response))
            except Exception as exc:
                last_error = exc
                if use_response_format:
                    logger.warning(
                        "Async G4F JSON structured mode failed for %s (%s). Retrying without response_format.",
                        self.model_id,
                        exc,
                    )
                    continue
                logger.error("Async G4F JSON error (%s): %s", self.model_id, exc)
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("Async G4F JSON generation failed without raising an exception.")

    async def generate_json_async_with_timeout(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: Optional[int] = None,
        *,
        step: str = "match",
        timeout_override: Optional[float] = None,
    ) -> Dict[str, Any]:
        params = self._build_completion_kwargs(
            system_prompt,
            user_prompt,
            max_tokens,
            response_format={"type": "json_object"},
        )
        effective_timeout = resolve_step_timeout_seconds(step, timeout_override)
        call_deadline = (
            self._build_call_deadline(effective_timeout) if effective_timeout > 0 else None
        )
        last_error: Optional[Exception] = None

        for use_response_format in (True, False):
            current_params: Dict[str, Any] = dict(params)
            phase = f"{step}:json" if use_response_format else f"{step}:json-fallback"
            if not use_response_format:
                if "response_format" in current_params:
                    del current_params["response_format"]

            try:
                response = await self._create_completion_async(
                    current_params,
                    phase=phase,
                    call_deadline=call_deadline,
                )
                return self._parse_json_content(self._get_message_content(response))
            except Exception as exc:
                last_error = exc
                if use_response_format:
                    logger.warning(
                        "Async G4F JSON structured mode failed for %s (%s). Retrying without response_format.",
                        self.model_id,
                        exc,
                    )
                    continue
                logger.error("Async G4F JSON error (%s): %s", self.model_id, exc)
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("Async G4F JSON generation failed without raising an exception.")

    async def generate_text_stream_async(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> AsyncIterator[str]:
        params = self._build_completion_kwargs(system_prompt, user_prompt, max_tokens)
        yielded_output = False

        try:
            stream = self.async_client.chat.completions.stream(**params)
            async for chunk in stream:
                content = self._get_message_content(chunk)
                if not content:
                    continue
                yielded_output = True
                yield content
        except Exception as exc:
            if yielded_output:
                logger.error(
                    "Async G4F stream error after partial output (%s): %s", self.model_id, exc
                )
                raise

            logger.warning(
                "Async G4F stream failed for %s (%s). Falling back to non-streaming response.",
                self.model_id,
                exc,
            )
            fallback_text = await self.generate_text_async(system_prompt, user_prompt, max_tokens)
            if fallback_text:
                yield fallback_text
