"""LLM provider factory with per-step resolution.

Resolution order for each field (provider, model, api_key, base_url, …):
  1. ``LLM_{STEP}_{FIELD}`` env var  →  use if non-empty / non-zero
  2. Global ``LLM_{FIELD}``          →  fallback

When ``step`` is not supplied (or is ``"default"``), global settings are used
directly — this is functionally identical to the old ``get_llm_provider()``.
"""

import logging
from backend.core.config import settings
from backend.providers.llm.base import LLMProvider
from backend.providers.llm.openai_compatible import OpenAICompatibleProvider
from backend.providers.llm.gemini import GeminiProvider
from backend.providers.llm.ollama import OllamaProvider

logger = logging.getLogger(__name__)

# ─── recognised step names (used as env-var prefixes) ────────────────────────
_KNOWN_STEPS = {"plan", "relevance", "match", "summary"}


def _resolve_step_config(step: str) -> dict:
    """Build a resolved config dict for the given pipeline *step*.

    Returns a flat dict with keys:
        provider, model, api_key, base_url, temperature, top_p,
        max_tokens, thinking, thinking_level
    """
    step = step.lower()

    if step in _KNOWN_STEPS:
        prefix = f"LLM_{step.upper()}_"
        step_provider       = getattr(settings, f"{prefix}PROVIDER", "")
        step_model           = getattr(settings, f"{prefix}MODEL", "")
        step_api_key         = getattr(settings, f"{prefix}API_KEY", "")
        step_base_url        = getattr(settings, f"{prefix}BASE_URL", "")
        step_temp            = getattr(settings, f"{prefix}TEMPERATURE", 0.0)
        step_top_p           = getattr(settings, f"{prefix}TOP_P", 0.0)
        step_max_tok         = getattr(settings, f"{prefix}MAX_TOKENS", 0)
        step_thinking        = getattr(settings, f"{prefix}THINKING", False)
        step_thinking_level  = getattr(settings, f"{prefix}THINKING_LEVEL", "")
    else:
        # Unknown step or "default" — everything falls through to globals
        step_provider = step_model = step_api_key = step_base_url = ""
        step_temp = 0.0
        step_top_p = 0.0
        step_max_tok = 0
        step_thinking = False
        step_thinking_level = ""

    return {
        "provider":       step_provider or settings.LLM_PROVIDER,
        "model":          step_model or settings.LLM_MODEL,
        "api_key":        step_api_key or settings.LLM_API_KEY,
        "base_url":       step_base_url or settings.LLM_BASE_URL,
        "temperature":    step_temp if step_temp > 0 else settings.LLM_TEMPERATURE,
        "top_p":          step_top_p if step_top_p > 0 else settings.LLM_TOP_P,
        "max_tokens":     step_max_tok if step_max_tok > 0 else settings.LLM_MAX_TOKENS,
        "thinking":       step_thinking if step_thinking else settings.LLM_THINKING,
        "thinking_level": step_thinking_level or settings.LLM_THINKING_LEVEL,
    }


def _build_provider(cfg: dict) -> LLMProvider:
    """Instantiate the correct ``LLMProvider`` subclass from a resolved *cfg*."""
    provider_name = cfg["provider"].lower()

    if provider_name == "gemini":
        return GeminiProvider(
            api_key=cfg["api_key"],
            model=cfg["model"],
            temperature=cfg["temperature"],
            top_p=cfg["top_p"],
            max_tokens=cfg["max_tokens"],
            thinking_level=cfg["thinking_level"],
        )

    if provider_name == "ollama":
        base_url = cfg["base_url"] or settings.OLLAMA_BASE_URL
        api_key  = cfg["api_key"] or "ollama"
        model    = cfg["model"] or settings.OLLAMA_MODEL
        return OllamaProvider(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=cfg["temperature"],
            top_p=cfg["top_p"],
            max_tokens=cfg["max_tokens"],
        )

    # Default: OpenAI-compatible (groq, deepseek, openai, etc.)
    return OpenAICompatibleProvider(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        model=cfg["model"],
        temperature=cfg["temperature"],
        top_p=cfg["top_p"],
        max_tokens=cfg["max_tokens"],
        thinking=cfg["thinking"],
        provider_name=provider_name,
    )


# ─── public API ──────────────────────────────────────────────────────────────

def get_provider_for_step(step: str = "default") -> LLMProvider:
    """Resolve and instantiate the LLM provider for a pipeline *step*.

    Recognised steps: ``"plan"``, ``"relevance"``, ``"match"``.
    Any other value (including ``"default"``) falls through to globals.
    """
    cfg = _resolve_step_config(step)
    provider = _build_provider(cfg)
    logger.debug(
        f"[LLM Factory] step={step!r} → {provider.model_id} "
        f"(temp={cfg['temperature']}, top_p={cfg['top_p']}, max_tok={cfg['max_tokens']})"
    )
    return provider


def get_llm_provider() -> LLMProvider:
    """Backward-compatible alias — returns the global default provider."""
    return get_provider_for_step("default")
