import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

from backend.providers.llm.base import LLMProvider, extract_json_payload

logger = logging.getLogger(__name__)


class G4FProvider(LLMProvider):
    """LLM provider backed by the gpt4free (g4f) client library."""

    _DEFAULT_COOKIES_DIR = Path(__file__).resolve().parents[3] / "data" / "g4f" / "har_and_cookies"

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
        shuffle_providers: bool = True,
        cookies_dir: Optional[str] = None,
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
        self.provider_names = [
            name.strip() for name in providers_list or [] if name and name.strip()
        ]
        self.proxies = proxies or ""
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.shuffle_providers = shuffle_providers
        self.cookies_dir = str(Path(cookies_dir) if cookies_dir else self._DEFAULT_COOKIES_DIR)

        Path(self.cookies_dir).mkdir(parents=True, exist_ok=True)
        set_cookies_dir(self.cookies_dir)
        read_cookie_files(self.cookies_dir)

        self._provider_module = provider_module
        self._client_factory = ClientFactory
        self._client_cls = Client
        self._async_client_cls = AsyncClient
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

    def _build_client_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.base_url:
            kwargs["base_url"] = self.base_url
        if self.proxies:
            kwargs["proxies"] = self.proxies
        return kwargs

    def _resolve_provider(self):
        if not self.provider_names:
            return None

        resolved_providers = []
        for provider_name in self.provider_names:
            provider = getattr(self._provider_module, provider_name, None)
            if provider is None:
                provider = self._client_factory.create_provider(
                    provider_name,
                    provider_name,
                    base_url=self.base_url or None,
                    api_key=self.api_key or None,
                )
            resolved_providers.append(provider)

        if len(resolved_providers) == 1:
            return resolved_providers[0]

        retry_provider = getattr(self._provider_module, "RetryProvider")
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
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        return kwargs

    def _get_message_content(self, response: Any) -> str:
        message = response.choices[0].message
        reasoning = getattr(message, "reasoning", None)
        if reasoning:
            logger.debug("G4F reasoning trace (%s): %s", self.model_id, str(reasoning)[:200])

        content = getattr(message, "content", "") or ""
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            return "".join(parts)
        return str(content)

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

    def generate_text(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> str:
        params = self._build_completion_kwargs(system_prompt, user_prompt, max_tokens)
        try:
            response = self.client.chat.completions.create(**params)
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
        try:
            response = self.client.chat.completions.create(**params)
            return self._parse_json_content(self._get_message_content(response))
        except Exception as exc:
            logger.error("G4F JSON error (%s): %s", self.model_id, exc)
            raise

    async def generate_text_async(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> str:
        params = self._build_completion_kwargs(system_prompt, user_prompt, max_tokens)
        try:
            response = await self.async_client.chat.completions.create(**params)
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
        try:
            response = await self.async_client.chat.completions.create(**params)
            return self._parse_json_content(self._get_message_content(response))
        except Exception as exc:
            logger.error("Async G4F JSON error (%s): %s", self.model_id, exc)
            raise

    async def generate_text_stream_async(
        self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None
    ) -> AsyncIterator[str]:
        params = self._build_completion_kwargs(system_prompt, user_prompt, max_tokens)
        stream = self.async_client.chat.completions.stream(**params)
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = getattr(chunk.choices[0], "delta", None)
            content = getattr(delta, "content", None) if delta is not None else None
            if content:
                yield str(content)
