from unittest.mock import MagicMock, patch

from backend.inference.ollama import OllamaProvider
from backend.providers.llm.factory import (
    _resolve_step_config,
    get_fallback_provider_for_step,
    get_provider_for_step,
    get_provider_name_for_step,
)


def _settings(**overrides):
    values = {
        "LOCAL_INFERENCE_URL": "http://localhost:11434",
        "local_inference_allowed_hosts": {"localhost"},
        "LOCAL_MODEL": "qwen3:1.7b",
        "LOCAL_INFERENCE_CONNECT_TIMEOUT_SECONDS": 1.0,
        "LOCAL_INFERENCE_REQUEST_TIMEOUT_SECONDS": 30.0,
        "LLM_TEMPERATURE": 0.2,
        "LLM_TOP_P": 0.9,
        "LLM_MAX_TOKENS": 2048,
        "LLM_CONTEXT_WINDOW": 8192,
        "LLM_PLAN_MODEL": "",
        "LLM_PLAN_CONTEXT_WINDOW": 0,
        "LLM_PLAN_TEMPERATURE": None,
        "LLM_PLAN_TOP_P": None,
        "LLM_PLAN_MAX_TOKENS": None,
        "LLM_MATCH_MODEL": "",
        "LLM_MATCH_CONTEXT_WINDOW": 0,
        "LLM_MATCH_TEMPERATURE": None,
        "LLM_MATCH_TOP_P": None,
        "LLM_MATCH_MAX_TOKENS": None,
    }
    values.update(overrides)
    result = MagicMock()
    for key, value in values.items():
        setattr(result, key, value)
    return result


def test_unknown_step_uses_local_defaults():
    with patch("backend.providers.llm.factory.settings", _settings()):
        config = _resolve_step_config("default")
    assert config["endpoint"] == "http://localhost:11434"
    assert config["model"] == "qwen3:1.7b"


def test_step_can_select_another_installed_local_model():
    with patch(
        "backend.providers.llm.factory.settings",
        _settings(LLM_MATCH_MODEL="gemma3:4b", LLM_MATCH_TEMPERATURE=0.1),
    ):
        config = _resolve_step_config("match")
    assert config["model"] == "gemma3:4b"
    assert config["temperature"] == 0.1


def test_factory_always_builds_native_local_provider():
    with patch("backend.providers.llm.factory.settings", _settings()):
        provider = get_provider_for_step("plan")
    assert isinstance(provider, OllamaProvider)
    assert provider.model_id == "ollama-local/qwen3:1.7b"


def test_factory_has_no_remote_fallback():
    assert get_provider_name_for_step("match") == "ollama-local"
    assert get_fallback_provider_for_step("match") is None
