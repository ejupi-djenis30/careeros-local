import logging
from backend.providers.llm.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


class OllamaProvider(OpenAICompatibleProvider):
    """Provider for locally-running Ollama models (OpenAI-compatible API).

    Inherits all behaviour from ``OpenAICompatibleProvider``.  The only
    difference is the default ``provider_name`` and ``model_id`` prefix.
    All settings are injected via the factory.
    """

    def __init__(
        self,
        *,
        api_key: str = "ollama",
        base_url: str = "http://localhost:11434/v1",
        model: str = "llama3",
        temperature: float = 0.7,
        top_p: float = 0.95,
        max_tokens: int = 16384,
        **kwargs,
    ):
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            thinking=False,
            provider_name="ollama",
        )
        logger.info(f"Initialized OllamaProvider with model={self.model}, base_url={base_url}")

    @property
    def model_id(self) -> str:
        return f"ollama/{self.model}"
