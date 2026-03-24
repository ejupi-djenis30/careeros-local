import json
import logging
from typing import Dict, Any, Optional
from openai import OpenAI, AsyncOpenAI
from backend.providers.llm.base import LLMProvider
from backend.core.config import settings

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    """Provider for any OpenAI-compatible API (Groq, DeepSeek, OpenAI, etc.).

    All settings are injected via the constructor — this class never reads
    from ``backend.core.config.settings`` directly.  Parameter resolution is
    handled by the **factory** layer (``get_provider_for_step``).
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.95,
        max_tokens: int = 16384,
        thinking: bool = False,
        provider_name: str = "openai",
    ):
        api_key = api_key or settings.LLM_API_KEY
        base_url = base_url or settings.LLM_BASE_URL
        self.model = model or settings.LLM_MODEL
        
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.async_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.thinking = thinking
        self.provider_name = provider_name

    @property
    def model_id(self) -> str:
        return f"{self.provider_name}/{self.model}"

    def _clean_json(self, text: str) -> str:
        text = text.strip()
        
        # Strip markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) > 2 and lines[-1].strip().startswith("```"):
                text = "\n".join(lines[1:-1])
            else:
                lines = [l for l in lines[1:] if not l.strip() == "```"]
                text = "\n".join(lines)
                
        # Deepseek often wraps its thought process in <think> tags before the JSON.
        # Find the first { or [ to locate the JSON payload.
        start_idx_dict = text.find("{")
        start_idx_list = text.find("[")
        
        start_idx = -1
        if start_idx_dict != -1 and start_idx_list != -1:
            start_idx = min(start_idx_dict, start_idx_list)
        else:
            start_idx = max(start_idx_dict, start_idx_list)
            
        if start_idx > 0:
            text = text[start_idx:]
            
        # Clean up any trailing text after the JSON ends
        end_idx_dict = text.rfind("}")
        end_idx_list = text.rfind("]")
        
        end_idx = max(end_idx_dict, end_idx_list)
        if end_idx != -1 and end_idx < len(text) - 1:
            text = text[:end_idx + 1]
            
        return text.strip()

    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> str:
        params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        
        if self.provider_name == "deepseek" and self.thinking:
            params.pop("temperature", None)
            params.pop("top_p", None)

        try:
            completion = self.client.chat.completions.create(**params)
            message = completion.choices[0].message
            content = message.content or ""
            
            if getattr(message, "reasoning_content", None):
                logger.info(f"DeepSeek Reasoning Trace: {message.reasoning_content[:500]}...")
            
            return content
        except Exception as e:
            logger.error(f"LLM Error ({self.model_id}): {e}")
            raise

    def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }

        if not (self.provider_name == "deepseek" and self.thinking):
             params["response_format"] = {"type": "json_object"}

        try:
            completion = self.client.chat.completions.create(**params)
            content = completion.choices[0].message.content or "{}"
            clean_text = self._clean_json(content)
            try:
                return json.loads(clean_text)
            except Exception as parse_err:
                logger.error(f"Failed to parse JSON from {self.model_id}. Raw output:\n{content}\nCleaned:\n{clean_text}")
                raise parse_err
        except Exception as e:
            logger.error(f"LLM JSON Error ({self.model_id}): {e}")
            raise

    async def generate_text_async(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> str:
        params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        
        if self.provider_name == "deepseek" and self.thinking:
            params.pop("temperature", None)
            params.pop("top_p", None)

        try:
            completion = await self.async_client.chat.completions.create(**params)
            message = completion.choices[0].message
            content = message.content or ""
            
            if getattr(message, "reasoning_content", None):
                logger.debug(f"DeepSeek Reasoning Trace: {message.reasoning_content[:200]}...")
            
            return content
        except Exception as e:
            logger.error(f"Async LLM Error ({self.model_id}): {e}")
            raise

    async def generate_json_async(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }

        if not (self.provider_name == "deepseek" and self.thinking):
             params["response_format"] = {"type": "json_object"}

        try:
            completion = await self.async_client.chat.completions.create(**params)
            content = completion.choices[0].message.content or "{}"
            clean_text = self._clean_json(content)
            try:
                return json.loads(clean_text)
            except Exception as parse_err:
                logger.error(f"Failed to parse JSON from {self.model_id}. Raw output:\n{content}\nCleaned:\n{clean_text}")
                raise parse_err
        except Exception as e:
            logger.error(f"Async LLM JSON Error ({self.model_id}): {e}")
            raise
