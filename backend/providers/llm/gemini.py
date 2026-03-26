import json
import logging
from typing import Dict, Any, Optional
from backend.providers.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Provider for Google Gemini (google-genai SDK).

    All settings are injected via the constructor — this class never reads
    from ``backend.core.config.settings`` directly.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        temperature: float = 0.7,
        top_p: float = 0.95,
        max_tokens: int = 16384,
        thinking_level: str = "OFF",
    ):
        try:
            from google import genai
            from google.genai import types
            self.client = genai.Client(api_key=api_key)
            self.types = types
        except ImportError:
            logger.error("google-genai package not installed")
            raise

        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.thinking_level = thinking_level

    # ── helpers ────────────────────────────────────────────────────────────

    @property
    def model_id(self) -> str:
        return f"gemini/{self.model}"

    def _get_config(self, json_mode: bool = False, max_tokens: Optional[int] = None, system_instruction: Optional[str] = None):
        gen_config_kwargs = {
            "temperature": self.temperature,
            "max_output_tokens": max_tokens or self.max_tokens,
            "top_p": self.top_p,
        }

        if system_instruction:
            gen_config_kwargs["system_instruction"] = system_instruction

        # Thinking
        if self.thinking_level != "OFF":
            gen_config_kwargs["thinking_config"] = self.types.ThinkingConfig(
                thinking_level=self.thinking_level,
            )

        if json_mode:
            gen_config_kwargs["response_mime_type"] = "application/json"
            
        return self.types.GenerateContentConfig(**gen_config_kwargs)

    # ── public API ─────────────────────────────────────────────────────────

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> str:
        config = self._get_config(json_mode=False, max_tokens=max_tokens, system_instruction=system_prompt)
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=config,
            )
            return response.text or ""
        except Exception as e:
             logger.error(f"Gemini Error ({self.model_id}): {e}")
             raise

    def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        config = self._get_config(json_mode=True, max_tokens=max_tokens, system_instruction=system_prompt)
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=config,
            )
            return json.loads(response.text or "{}")
        except Exception as e:
             logger.error(f"Gemini JSON Error ({self.model_id}): {e}")
             raise

    async def generate_text_async(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> str:
        import asyncio
        return await asyncio.to_thread(self.generate_text, system_prompt, user_prompt, max_tokens)

    async def generate_json_async(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        import asyncio
        return await asyncio.to_thread(self.generate_json, system_prompt, user_prompt, max_tokens)
