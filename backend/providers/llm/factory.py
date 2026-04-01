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
from backend.providers.llm.gemini import GeminiProvider
from backend.providers.llm.ollama import OllamaProvider
from backend.providers.llm.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

# ─── recognised step names (used as env-var prefixes) ────────────────────────
_KNOWN_STEPS = {
    "plan",
    "match",
    "normalize",
    "normalize_profile",
    "compress",
    "critique",
    "rerank",
}


def _parse_csv_names(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _resolve_g4f_model(step: str) -> str:
    step = step.lower()
    if step in _KNOWN_STEPS:
        step_model = getattr(settings, f"LLM_{step.upper()}_MODEL", "")
        if step_model:
            return step_model
    return settings.G4F_MODEL


def _resolve_step_config(step: str) -> dict:
    """Build a resolved config dict for the given pipeline *step*.

    Returns a flat dict with keys:
        provider, model, api_key, base_url, temperature, top_p,
        max_tokens, thinking, thinking_level
    """
    step = step.lower()

    if step in _KNOWN_STEPS:
        prefix = f"LLM_{step.upper()}_"
        step_provider = getattr(settings, f"{prefix}PROVIDER", "")
        step_model = getattr(settings, f"{prefix}MODEL", "")
        step_api_key = getattr(settings, f"{prefix}API_KEY", "")
        step_base_url = getattr(settings, f"{prefix}BASE_URL", "")
        step_temp = getattr(settings, f"{prefix}TEMPERATURE", None)
        step_top_p = getattr(settings, f"{prefix}TOP_P", None)
        step_max_tok = getattr(settings, f"{prefix}MAX_TOKENS", None)
        # Use None as sentinel so explicit False overrides are respected.
        step_thinking = getattr(settings, f"{prefix}THINKING", None)
        step_thinking_level = getattr(settings, f"{prefix}THINKING_LEVEL", "")
    else:
        # Unknown step or "default" — everything falls through to globals
        step_provider = step_model = step_api_key = step_base_url = ""
        step_temp = None
        step_top_p = None
        step_max_tok = None
        step_thinking = None
        step_thinking_level = ""

    return {
        "provider": step_provider or settings.LLM_PROVIDER,
        "model": step_model or settings.LLM_MODEL,
        "api_key": step_api_key or settings.LLM_API_KEY,
        "base_url": step_base_url or settings.LLM_BASE_URL,
        # None means "not set for this step" → use global default
        "temperature": step_temp if step_temp is not None else settings.LLM_TEMPERATURE,
        "top_p": step_top_p if step_top_p is not None else settings.LLM_TOP_P,
        "max_tokens": step_max_tok if step_max_tok is not None else settings.LLM_MAX_TOKENS,
        # Preserve explicit per-step False: only fall back when the per-step
        # value is unset (None).
        "thinking": step_thinking if step_thinking is not None else settings.LLM_THINKING,
        "thinking_level": step_thinking_level or settings.LLM_THINKING_LEVEL,
    }


def _resolve_fallback_step_config(step: str) -> dict | None:
    """Build the fallback provider config for *step*.

    Fallback config is optional. When present, it reuses the resolved per-step
    primary parameters as a last resort for any unset fallback field so that a
    stable provider can inherit existing model tuning when practical.
    """

    fallback_provider = (settings.LLM_FALLBACK_PROVIDER or "").strip()
    if not fallback_provider:
        return None

    primary_cfg = _resolve_step_config(step)

    return {
        "provider": fallback_provider,
        "model": settings.LLM_FALLBACK_MODEL or primary_cfg["model"],
        "api_key": settings.LLM_FALLBACK_API_KEY or primary_cfg["api_key"],
        "base_url": settings.LLM_FALLBACK_BASE_URL or primary_cfg["base_url"],
        "temperature": (
            settings.LLM_FALLBACK_TEMPERATURE
            if settings.LLM_FALLBACK_TEMPERATURE is not None
            else primary_cfg["temperature"]
        ),
        "top_p": (
            settings.LLM_FALLBACK_TOP_P
            if settings.LLM_FALLBACK_TOP_P is not None
            else primary_cfg["top_p"]
        ),
        "max_tokens": (
            settings.LLM_FALLBACK_MAX_TOKENS
            if settings.LLM_FALLBACK_MAX_TOKENS is not None
            else primary_cfg["max_tokens"]
        ),
        "thinking": (
            settings.LLM_FALLBACK_THINKING
            if settings.LLM_FALLBACK_THINKING is not None
            else primary_cfg["thinking"]
        ),
        "thinking_level": settings.LLM_FALLBACK_THINKING_LEVEL or primary_cfg["thinking_level"],
    }


def _build_provider(cfg: dict, step: str = "default") -> LLMProvider:
    """Instantiate the correct ``LLMProvider`` subclass from a resolved *cfg*."""
    provider_name = cfg["provider"].lower()
    step_label = step or "default"
    api_key_hint = (
        "LLM_API_KEY"
        if step_label == "default"
        else f"LLM_{step_label.upper()}_API_KEY or LLM_API_KEY"
    )

    # Validate API key is present for cloud providers (not needed for ollama)
    if provider_name not in ("ollama", "g4f") and not cfg.get("api_key"):
        raise ValueError(
            f"LLM provider '{provider_name}' for step '{step_label}' requires an API key but none was set. "
            f"Configure {api_key_hint} in your environment."
        )

    try:
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
            api_key = cfg["api_key"] or "ollama"
            model = cfg["model"] or settings.OLLAMA_MODEL
            return OllamaProvider(
                api_key=api_key,
                base_url=base_url,
                model=model,
                temperature=cfg["temperature"],
                top_p=cfg["top_p"],
                max_tokens=cfg["max_tokens"],
            )

        if provider_name == "g4f":
            from backend.providers.llm.g4f_provider import G4FProvider

            return G4FProvider(
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                model=_resolve_g4f_model(step_label),
                providers_list=_parse_csv_names(settings.G4F_PROVIDERS),
                cookies_dir=settings.G4F_COOKIES_DIR or None,
                proxies=settings.G4F_PROXY,
                temperature=cfg["temperature"],
                top_p=cfg["top_p"],
                max_tokens=cfg["max_tokens"],
                max_request_attempts=settings.G4F_MAX_REQUEST_ATTEMPTS,
                request_timeout_cap_seconds=settings.G4F_REQUEST_TIMEOUT_CAP_SECONDS,
                timeout_buffer_seconds=settings.G4F_TIMEOUT_BUFFER_SECONDS,
                rate_limit_wait_seconds=settings.G4F_RATE_LIMIT_WAIT_SECONDS,
                shuffle_providers=settings.G4F_SHUFFLE_PROVIDERS,
                allow_auto_discovery=settings.G4F_AUTO_DISCOVER_PROVIDERS,
                allow_internal_provider_fallback=settings.G4F_ALLOW_INTERNAL_PROVIDER_FALLBACK,
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
    except Exception as exc:
        raise ValueError(
            f"Failed to initialize LLM provider '{provider_name}' for step '{step_label}': {exc}"
        ) from exc


# ─── public API ──────────────────────────────────────────────────────────────


def get_provider_name_for_step(step: str = "default") -> str:
    """Return the resolved primary provider name for a pipeline *step*."""

    return str(_resolve_step_config(step).get("provider") or "").strip().lower()


def get_fallback_provider_for_step(step: str = "default") -> LLMProvider | None:
    """Resolve and instantiate the configured fallback provider for a step.

    Returns ``None`` when no fallback provider has been configured.
    """

    cfg = _resolve_fallback_step_config(step)
    if cfg is None:
        return None

    provider = _build_provider(cfg, step=step)
    logger.debug(
        f"[LLM Factory] fallback step={step!r} → {provider.model_id} "
        f"(temp={cfg['temperature']}, top_p={cfg['top_p']}, max_tok={cfg['max_tokens']})"
    )
    return provider


def get_provider_for_step(step: str = "default") -> LLMProvider:
    """Resolve and instantiate the LLM provider for a pipeline *step*.

    Recognised steps: ``"plan"``, ``"match"``, ``"normalize"``, ``"normalize_profile"``,
    ``"compress"``, ``"critique"``, ``"rerank"``.
    Any other value (including ``"default"``) falls through to globals.
    """
    cfg = _resolve_step_config(step)
    provider = _build_provider(cfg, step=step)
    logger.debug(
        f"[LLM Factory] step={step!r} → {provider.model_id} "
        f"(temp={cfg['temperature']}, top_p={cfg['top_p']}, max_tok={cfg['max_tokens']})"
    )
    return provider


def get_llm_provider() -> LLMProvider:
    """Backward-compatible alias — returns the global default provider."""
    return get_provider_for_step("default")
