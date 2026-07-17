"""Local-only model factory kept at the legacy import path during the refactor."""

from typing import Any

from backend.core.config import settings
from backend.inference.managed_runtime import get_managed_runtime
from backend.inference.ollama import OllamaProvider

_KNOWN_STEPS = {
    "plan",
    "match",
    "normalize",
    "normalize_profile",
    "compress",
    "critique",
    "rerank",
}


def _resolve_step_config(step: str) -> dict[str, Any]:
    normalized = step.lower()
    prefix = f"LLM_{normalized.upper()}_" if normalized in _KNOWN_STEPS else ""
    model = getattr(settings, f"{prefix}MODEL", "") if prefix else ""
    temperature = getattr(settings, f"{prefix}TEMPERATURE", None) if prefix else None
    top_p = getattr(settings, f"{prefix}TOP_P", None) if prefix else None
    max_tokens = getattr(settings, f"{prefix}MAX_TOKENS", None) if prefix else None
    context_window = getattr(settings, f"{prefix}CONTEXT_WINDOW", None) if prefix else None
    return {
        "endpoint": settings.LOCAL_INFERENCE_URL,
        "allowed_hosts": settings.local_inference_allowed_hosts,
        "model": model or settings.LOCAL_MODEL,
        "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
        "top_p": settings.LLM_TOP_P if top_p is None else top_p,
        "max_tokens": settings.LLM_MAX_TOKENS if max_tokens is None else max_tokens,
        "context_window": (
            settings.LLM_CONTEXT_WINDOW if not context_window else context_window
        ),
    }


def _build_provider(cfg: dict[str, Any], step: str = "default") -> OllamaProvider:
    del step
    return OllamaProvider(
        endpoint=cfg["endpoint"],
        allowed_hosts=set(cfg["allowed_hosts"]),
        model=cfg["model"],
        temperature=cfg["temperature"],
        top_p=cfg["top_p"],
        max_tokens=cfg["max_tokens"],
        context_window=cfg["context_window"],
        connect_timeout=settings.LOCAL_INFERENCE_CONNECT_TIMEOUT_SECONDS,
        request_timeout=settings.LOCAL_INFERENCE_REQUEST_TIMEOUT_SECONDS,
    )


def get_provider_name_for_step(step: str = "default") -> str:
    del step
    return "llama-cpp-managed" if get_managed_runtime().snapshot().ready else "ollama-local"


def get_fallback_provider_for_step(step: str = "default") -> None:
    del step
    return None


def get_provider_for_step(step: str = "default"):
    manager = get_managed_runtime()
    if manager.snapshot().ready:
        return manager.provider()
    return _build_provider(_resolve_step_config(step), step=step)


def get_llm_provider():
    return get_provider_for_step("default")
