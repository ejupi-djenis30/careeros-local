from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class LLMProvider(ABC):
    """Abstract base for all LLM providers.

    Concrete implementations receive all runtime parameters (api_key, model,
    temperature, …) via their constructor — they must NOT read from
    ``backend.core.config.settings`` directly.  Parameter resolution is
    handled by the **factory** layer (``get_provider_for_step``).
    """

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Return a human-readable identifier: '<provider>/<model>'"""
        pass

    @abstractmethod
    def generate_text(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> str:
        """Generate text from the LLM"""
        pass

    @abstractmethod
    def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """Generate a JSON response from the LLM based on prompts."""
        pass

    async def generate_text_async(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> str:
        """Async version — default falls back to sync via to_thread."""
        import asyncio
        return await asyncio.to_thread(self.generate_text, system_prompt, user_prompt, max_tokens)

    async def generate_json_async(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """Async version — default falls back to sync via to_thread."""
        import asyncio
        return await asyncio.to_thread(self.generate_json, system_prompt, user_prompt, max_tokens)
