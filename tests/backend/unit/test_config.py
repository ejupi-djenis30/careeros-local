import logging
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.core.config import Settings

VALID_TEST_SIGNING_VALUE = "v" * 64


def test_cors_origins_list_warns_and_falls_back(caplog):
    caplog.set_level(logging.WARNING)
    settings = Settings(CORS_ORIGINS="[invalid", SECRET_KEY=VALID_TEST_SIGNING_VALUE)

    assert settings.cors_origins_list == ["[invalid"]
    assert "Invalid CORS_ORIGINS JSON" in caplog.text


def test_allowed_hosts_warns_and_falls_back(caplog):
    caplog.set_level(logging.WARNING)
    settings = Settings(ALLOWED_HOSTS="[invalid", SECRET_KEY=VALID_TEST_SIGNING_VALUE)

    assert settings.ALLOWED_HOSTS == ["[invalid"]
    assert "Invalid ALLOWED_HOSTS JSON" in caplog.text


def test_remote_inference_endpoint_is_rejected():
    with pytest.raises(ValueError, match="Local inference"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            LOCAL_INFERENCE_URL="https://api.example.com/v1",
        )


def test_environment_allowlist_cannot_expand_local_inference_boundary():
    with pytest.raises(ValueError, match="built-in local boundary"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            LOCAL_INFERENCE_ALLOWED_HOSTS="localhost,remote.example",
            LOCAL_INFERENCE_URL="http://remote.example:11434",
        )


def test_per_step_model_cannot_diverge_from_attested_local_model():
    with pytest.raises(ValueError, match="readiness attests"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            LOCAL_MODEL="qwen3:1.7b",
            LLM_MATCH_MODEL="another-model",
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "LOCAL_INFERENCE_CONNECT_TIMEOUT_SECONDS",
        "LOCAL_INFERENCE_REQUEST_TIMEOUT_SECONDS",
        "LLM_CALL_TIMEOUT_PLAN",
        "LLM_CALL_TIMEOUT_NORMALIZE",
        "LLM_CALL_TIMEOUT_MATCH",
        "LLM_CALL_TIMEOUT_COACH",
        "LLM_CALL_TIMEOUT_CRITIQUE",
        "LLM_CALL_TIMEOUT_RERANK",
    ],
)
@pytest.mark.parametrize("invalid_value", [0, -1])
def test_inference_timeouts_must_be_strictly_positive(field_name, invalid_value):
    with pytest.raises(ValueError, match=rf"{field_name} must be greater than zero"):
        Settings(
            SECRET_KEY=VALID_TEST_SIGNING_VALUE,
            **{field_name: invalid_value},
        )


def test_production_rejects_development_signing_value():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(ENVIRONMENT="production", SECRET_KEY="local-development-only")


def test_production_loads_persisted_installation_signing_value(monkeypatch):
    persisted_value = "p" * 64
    with TemporaryDirectory() as directory:
        data_dir = Path(directory)
        fixture_path = data_dir / "installation-value.fixture"
        fixture_path.write_text(persisted_value, encoding="utf-8")
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.setenv("DATA_DIR", str(data_dir))
        monkeypatch.setenv("CAREEROS_SECRET_FILE", str(fixture_path))

        loaded = Settings(_env_file=None, ENVIRONMENT="production")

        assert loaded.SECRET_KEY == persisted_value
