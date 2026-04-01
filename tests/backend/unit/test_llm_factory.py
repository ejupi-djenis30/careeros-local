"""Unit tests for backend/providers/llm/factory.py.

Covers:
- _resolve_step_config: known steps, unknown step, per-step overrides
- _build_provider: gemini, ollama, openai-compatible, missing API key error
- get_provider_for_step: end-to-end instantiation for each known step
"""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from backend.providers.llm.factory import (
    _build_provider,
    _resolve_fallback_step_config,
    _resolve_step_config,
    get_fallback_provider_for_step,
    get_provider_for_step,
    get_provider_name_for_step,
)
from backend.providers.llm.g4f_provider import G4FProvider
from backend.providers.llm.gemini import GeminiProvider
from backend.providers.llm.ollama import OllamaProvider
from backend.providers.llm.openai_compatible import OpenAICompatibleProvider

# ─── _resolve_step_config ─────────────────────────────────────────────────────


class TestResolveStepConfig:
    def _mock_settings(self, **overrides):
        defaults = dict(
            LLM_PROVIDER="openai",
            LLM_MODEL="gpt-4",
            LLM_API_KEY="global-key",
            LLM_BASE_URL="https://api.openai.com",
            LLM_TEMPERATURE=0.2,
            LLM_TOP_P=0.9,
            LLM_MAX_TOKENS=1024,
            LLM_THINKING=False,
            LLM_THINKING_LEVEL="",
            # step-specific defaults (empty = use global)
            LLM_PLAN_PROVIDER="",
            LLM_PLAN_MODEL="",
            LLM_PLAN_API_KEY="",
            LLM_PLAN_BASE_URL="",
            LLM_PLAN_TEMPERATURE=None,
            LLM_PLAN_TOP_P=None,
            LLM_PLAN_MAX_TOKENS=None,
            LLM_PLAN_THINKING=False,
            LLM_PLAN_THINKING_LEVEL="",
            LLM_MATCH_PROVIDER="",
            LLM_MATCH_MODEL="",
            LLM_MATCH_API_KEY="",
            LLM_MATCH_BASE_URL="",
            LLM_MATCH_TEMPERATURE=None,
            LLM_MATCH_TOP_P=None,
            LLM_MATCH_MAX_TOKENS=None,
            LLM_MATCH_THINKING=False,
            LLM_MATCH_THINKING_LEVEL="",
            LLM_NORMALIZE_PROVIDER="",
            LLM_NORMALIZE_MODEL="",
            LLM_NORMALIZE_API_KEY="",
            LLM_NORMALIZE_BASE_URL="",
            LLM_NORMALIZE_TEMPERATURE=None,
            LLM_NORMALIZE_TOP_P=None,
            LLM_NORMALIZE_MAX_TOKENS=None,
            LLM_NORMALIZE_THINKING=False,
            LLM_NORMALIZE_THINKING_LEVEL="",
            LLM_NORMALIZE_PROFILE_PROVIDER="",
            LLM_NORMALIZE_PROFILE_MODEL="",
            LLM_NORMALIZE_PROFILE_API_KEY="",
            LLM_NORMALIZE_PROFILE_BASE_URL="",
            LLM_NORMALIZE_PROFILE_TEMPERATURE=None,
            LLM_NORMALIZE_PROFILE_TOP_P=None,
            LLM_NORMALIZE_PROFILE_MAX_TOKENS=None,
            LLM_NORMALIZE_PROFILE_THINKING=False,
            LLM_NORMALIZE_PROFILE_THINKING_LEVEL="",
            LLM_COMPRESS_PROVIDER="",
            LLM_COMPRESS_MODEL="",
            LLM_COMPRESS_API_KEY="",
            LLM_COMPRESS_BASE_URL="",
            LLM_COMPRESS_TEMPERATURE=None,
            LLM_COMPRESS_TOP_P=None,
            LLM_COMPRESS_MAX_TOKENS=None,
            LLM_COMPRESS_THINKING=False,
            LLM_COMPRESS_THINKING_LEVEL="",
            G4F_MODEL="",
            G4F_PROVIDERS="HuggingChat,DeepInfra",
            G4F_COOKIES_DIR="",
            G4F_PROXY="http://localhost:8080",
            G4F_SHUFFLE_PROVIDERS=False,
            G4F_MAX_REQUEST_ATTEMPTS=2,
            G4F_REQUEST_TIMEOUT_CAP_SECONDS=20.0,
            G4F_TIMEOUT_BUFFER_SECONDS=1.0,
            G4F_RATE_LIMIT_WAIT_SECONDS=3600.0,
            G4F_AUTO_DISCOVER_PROVIDERS=True,
            G4F_ALLOW_INTERNAL_PROVIDER_FALLBACK=False,
            LLM_FALLBACK_PROVIDER="",
            LLM_FALLBACK_MODEL="",
            LLM_FALLBACK_API_KEY="",
            LLM_FALLBACK_BASE_URL="",
            LLM_FALLBACK_TEMPERATURE=None,
            LLM_FALLBACK_TOP_P=None,
            LLM_FALLBACK_MAX_TOKENS=None,
            LLM_FALLBACK_THINKING=None,
            LLM_FALLBACK_THINKING_LEVEL="",
            OLLAMA_BASE_URL="http://localhost:11434",
            OLLAMA_MODEL="mistral",
        )
        defaults.update(overrides)
        m = MagicMock()
        for k, v in defaults.items():
            setattr(m, k, v)
        return m

    def test_unknown_step_falls_through_to_globals(self):
        with patch("backend.providers.llm.factory.settings", self._mock_settings()):
            cfg = _resolve_step_config("default")
        assert cfg["provider"] == "openai"
        assert cfg["model"] == "gpt-4"
        assert cfg["api_key"] == "global-key"

    def test_known_step_plan_uses_global_when_step_fields_empty(self):
        with patch("backend.providers.llm.factory.settings", self._mock_settings()):
            cfg = _resolve_step_config("plan")
        assert cfg["provider"] == "openai"
        assert cfg["temperature"] == 0.2

    def test_known_step_plan_overrides_when_step_fields_set(self):
        with patch(
            "backend.providers.llm.factory.settings",
            self._mock_settings(
                LLM_PLAN_PROVIDER="gemini",
                LLM_PLAN_MODEL="gemini-pro",
                LLM_PLAN_API_KEY="plan-key",
                LLM_PLAN_TEMPERATURE=0.5,
            ),
        ):
            cfg = _resolve_step_config("plan")
        assert cfg["provider"] == "gemini"
        assert cfg["model"] == "gemini-pro"
        assert cfg["api_key"] == "plan-key"
        assert cfg["temperature"] == 0.5

    def test_step_temperature_none_falls_back_to_global(self):
        with patch(
            "backend.providers.llm.factory.settings",
            self._mock_settings(
                LLM_MATCH_TEMPERATURE=None,
                LLM_TEMPERATURE=0.7,
            ),
        ):
            cfg = _resolve_step_config("match")
        assert cfg["temperature"] == 0.7

    def test_all_known_steps_are_resolvable(self):
        with patch("backend.providers.llm.factory.settings", self._mock_settings()):
            for step in (
                "plan",
                "match",
                "normalize",
                "normalize_profile",
                "compress",
                "critique",
                "rerank",
            ):
                cfg = _resolve_step_config(step)
                assert "provider" in cfg

    def test_fallback_config_reuses_primary_step_fields_when_unset(self):
        with patch(
            "backend.providers.llm.factory.settings",
            self._mock_settings(
                LLM_PROVIDER="g4f",
                LLM_MATCH_MODEL="llama-3.3-70b-versatile",
                LLM_MATCH_API_KEY="primary-match-key",
                LLM_MATCH_BASE_URL="https://api.groq.com/openai/v1",
                LLM_FALLBACK_PROVIDER="groq",
            ),
        ):
            cfg = _resolve_fallback_step_config("match")

        assert cfg is not None
        assert cfg["provider"] == "groq"
        assert cfg["model"] == "llama-3.3-70b-versatile"
        assert cfg["api_key"] == "primary-match-key"
        assert cfg["base_url"] == "https://api.groq.com/openai/v1"


# ─── _build_provider ──────────────────────────────────────────────────────────


class TestBuildProvider:
    def _mock_settings(self, **overrides):
        defaults = dict(
            G4F_MODEL="",
            G4F_PROVIDERS="HuggingChat,DeepInfra",
            G4F_COOKIES_DIR="/tmp/g4f-cookies",
            G4F_PROXY="http://localhost:8080",
            G4F_SHUFFLE_PROVIDERS=False,
            G4F_MAX_REQUEST_ATTEMPTS=2,
            G4F_REQUEST_TIMEOUT_CAP_SECONDS=20.0,
            G4F_TIMEOUT_BUFFER_SECONDS=1.0,
            G4F_RATE_LIMIT_WAIT_SECONDS=3600.0,
            G4F_AUTO_DISCOVER_PROVIDERS=True,
            G4F_ALLOW_INTERNAL_PROVIDER_FALLBACK=False,
            LLM_MATCH_MODEL="",
            LLM_FALLBACK_PROVIDER="",
            LLM_FALLBACK_MODEL="",
            LLM_FALLBACK_API_KEY="",
            LLM_FALLBACK_BASE_URL="",
            LLM_FALLBACK_TEMPERATURE=None,
            LLM_FALLBACK_TOP_P=None,
            LLM_FALLBACK_MAX_TOKENS=None,
            LLM_FALLBACK_THINKING=None,
            LLM_FALLBACK_THINKING_LEVEL="",
            OLLAMA_BASE_URL="http://localhost:11434",
            OLLAMA_MODEL="mistral",
        )
        defaults.update(overrides)
        m = MagicMock()
        for key, value in defaults.items():
            setattr(m, key, value)
        return m

    def _base_cfg(self, **overrides):
        cfg = {
            "provider": "openai",
            "model": "gpt-4",
            "api_key": "test-key",
            "base_url": "https://api.openai.com",
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 512,
            "thinking": False,
            "thinking_level": "",
        }
        cfg.update(overrides)
        return cfg

    def test_builds_openai_compatible_provider(self):
        cfg = self._base_cfg()
        provider = _build_provider(cfg)
        assert isinstance(provider, OpenAICompatibleProvider)

    def test_builds_gemini_provider(self):
        cfg = self._base_cfg(provider="gemini", api_key="gemini-key")
        provider = _build_provider(cfg)
        assert isinstance(provider, GeminiProvider)

    def test_builds_ollama_provider(self):
        with patch("backend.providers.llm.factory.settings") as mock_settings:
            mock_settings.OLLAMA_BASE_URL = "http://localhost:11434"
            mock_settings.OLLAMA_MODEL = "mistral"
            cfg = self._base_cfg(provider="ollama", api_key="")
            provider = _build_provider(cfg)
        assert isinstance(provider, OllamaProvider)

    def test_raises_when_no_api_key_for_cloud_provider(self):
        cfg = self._base_cfg(provider="openai", api_key="")
        with pytest.raises(ValueError, match="API key"):
            _build_provider(cfg)

    def test_missing_api_key_error_includes_step_context(self):
        cfg = self._base_cfg(provider="openai", api_key="")
        with pytest.raises(ValueError, match="step 'match'.*LLM_MATCH_API_KEY or LLM_API_KEY"):
            _build_provider(cfg, step="match")

    def test_ollama_does_not_require_api_key(self):
        with patch("backend.providers.llm.factory.settings") as mock_settings:
            mock_settings.OLLAMA_BASE_URL = "http://localhost:11434"
            mock_settings.OLLAMA_MODEL = "llama3"
            cfg = self._base_cfg(provider="ollama", api_key="")
            # Should not raise
            provider = _build_provider(cfg)
        assert isinstance(provider, OllamaProvider)

    def test_builds_g4f_provider(self):
        cfg = self._base_cfg(provider="g4f", api_key="")
        with patch("backend.providers.llm.factory.settings", self._mock_settings()):
            with patch(
                "backend.providers.llm.g4f_provider.G4FProvider.__init__",
                return_value=None,
            ) as mock_init:
                provider = _build_provider(cfg, step="match")

        assert isinstance(provider, G4FProvider)
        mock_init.assert_called_once_with(
            api_key="",
            base_url="https://api.openai.com",
            model="",
            providers_list=["HuggingChat", "DeepInfra"],
            cookies_dir="/tmp/g4f-cookies",
            proxies="http://localhost:8080",
            temperature=0.2,
            top_p=0.9,
            max_tokens=512,
            max_request_attempts=2,
            request_timeout_cap_seconds=20.0,
            timeout_buffer_seconds=1.0,
            rate_limit_wait_seconds=3600.0,
            shuffle_providers=False,
            allow_auto_discovery=True,
            allow_internal_provider_fallback=False,
        )

    def test_builds_fallback_provider_when_configured(self):
        with patch(
            "backend.providers.llm.factory.settings",
            self._mock_settings(
                LLM_FALLBACK_PROVIDER="groq",
                LLM_FALLBACK_MODEL="llama-3.3-70b-versatile",
                LLM_FALLBACK_API_KEY="fallback-key",
                LLM_FALLBACK_BASE_URL="https://api.groq.com/openai/v1",
            ),
        ):
            provider = get_fallback_provider_for_step("match")

        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider.model_id == "groq/llama-3.3-70b-versatile"

    def test_g4f_does_not_require_api_key(self):
        cfg = self._base_cfg(provider="g4f", api_key="")
        with patch("backend.providers.llm.factory.settings", self._mock_settings()):
            with patch(
                "backend.providers.llm.g4f_provider.G4FProvider.__init__",
                return_value=None,
            ):
                provider = _build_provider(cfg)
        assert isinstance(provider, G4FProvider)


# ─── get_provider_for_step ────────────────────────────────────────────────────


class TestGetProviderForStep:
    def _patched_settings(self):
        m = MagicMock()
        m.LLM_PROVIDER = "openai"
        m.LLM_MODEL = "gpt-4o"
        m.LLM_API_KEY = "sk-test"
        m.LLM_BASE_URL = ""
        m.LLM_TEMPERATURE = 0.3
        m.LLM_TOP_P = 1.0
        m.LLM_MAX_TOKENS = 1024
        m.LLM_THINKING = False
        m.LLM_THINKING_LEVEL = ""
        m.G4F_MODEL = ""
        m.G4F_PROVIDERS = "HuggingChat,DeepInfra"
        m.G4F_COOKIES_DIR = ""
        m.G4F_PROXY = ""
        m.G4F_SHUFFLE_PROVIDERS = True
        m.G4F_MAX_REQUEST_ATTEMPTS = 2
        m.G4F_REQUEST_TIMEOUT_CAP_SECONDS = 20.0
        m.G4F_TIMEOUT_BUFFER_SECONDS = 1.0
        m.G4F_RATE_LIMIT_WAIT_SECONDS = 3600.0
        m.G4F_AUTO_DISCOVER_PROVIDERS = True
        m.G4F_ALLOW_INTERNAL_PROVIDER_FALLBACK = False
        m.LLM_FALLBACK_PROVIDER = ""
        m.LLM_FALLBACK_MODEL = ""
        m.LLM_FALLBACK_API_KEY = ""
        m.LLM_FALLBACK_BASE_URL = ""
        m.LLM_FALLBACK_TEMPERATURE = None
        m.LLM_FALLBACK_TOP_P = None
        m.LLM_FALLBACK_MAX_TOKENS = None
        m.LLM_FALLBACK_THINKING = None
        m.LLM_FALLBACK_THINKING_LEVEL = ""
        for step in ("PLAN", "MATCH", "NORMALIZE", "NORMALIZE_PROFILE", "COMPRESS"):
            for field in ("PROVIDER", "MODEL", "API_KEY", "BASE_URL", "THINKING_LEVEL"):
                setattr(m, f"LLM_{step}_{field}", "")
            for field in ("TEMPERATURE", "TOP_P", "MAX_TOKENS"):
                setattr(m, f"LLM_{step}_{field}", None)
            setattr(m, f"LLM_{step}_THINKING", False)
        for step in ("CRITIQUE", "RERANK"):
            for field in ("PROVIDER", "MODEL", "API_KEY", "BASE_URL"):
                setattr(m, f"LLM_{step}_{field}", "")
            for field in ("TEMPERATURE", "TOP_P", "MAX_TOKENS"):
                setattr(m, f"LLM_{step}_{field}", None)
        return m

    def test_default_step_returns_provider(self):
        with patch("backend.providers.llm.factory.settings", self._patched_settings()):
            provider = get_provider_for_step("default")
        assert isinstance(provider, OpenAICompatibleProvider)

    def test_each_known_step_returns_provider(self):
        with patch("backend.providers.llm.factory.settings", self._patched_settings()):
            for step in (
                "plan",
                "match",
                "normalize",
                "normalize_profile",
                "compress",
                "critique",
                "rerank",
            ):
                provider = get_provider_for_step(step)
                assert provider is not None

    def test_g4f_provider_for_any_step(self):
        settings = self._patched_settings()
        settings.LLM_PROVIDER = "g4f"
        settings.LLM_API_KEY = ""

        with patch("backend.providers.llm.factory.settings", settings):
            with patch(
                "backend.providers.llm.g4f_provider.G4FProvider.__init__",
                return_value=None,
            ):
                with patch(
                    "backend.providers.llm.g4f_provider.G4FProvider.model_id",
                    new_callable=PropertyMock,
                    return_value="g4f/auto",
                ):
                    for step in ("plan", "match", "normalize"):
                        provider = get_provider_for_step(step)
                        assert isinstance(provider, G4FProvider)

    def test_get_provider_name_for_step_returns_resolved_primary_provider(self):
        settings = self._patched_settings()
        settings.LLM_NORMALIZE_PROVIDER = "g4f"

        with patch("backend.providers.llm.factory.settings", settings):
            assert get_provider_name_for_step("normalize") == "g4f"
