import logging

from backend.core.config import Settings


def test_cors_origins_list_warns_and_falls_back(caplog):
    caplog.set_level(logging.WARNING)
    settings = Settings(CORS_ORIGINS="[invalid", SECRET_KEY="custom-secret")

    assert settings.cors_origins_list == ["[invalid"]
    assert "Invalid CORS_ORIGINS JSON" in caplog.text


def test_allowed_hosts_warns_and_falls_back(caplog):
    caplog.set_level(logging.WARNING)
    settings = Settings(ALLOWED_HOSTS="[invalid", SECRET_KEY="custom-secret")

    assert settings.ALLOWED_HOSTS == ["[invalid"]
    assert "Invalid ALLOWED_HOSTS JSON" in caplog.text


def test_g4f_retry_attempts_are_clamped(caplog):
    caplog.set_level(logging.WARNING)
    settings = Settings(
        SECRET_KEY="custom-secret",
        LLM_PROVIDER="g4f",
        LLM_FALLBACK_PROVIDER="groq",
        G4F_PROVIDERS="DeepInfra",
        G4F_MAX_REQUEST_ATTEMPTS=999999999,
    )

    assert settings.G4F_MAX_REQUEST_ATTEMPTS == 6
    assert "clamping to 6" in caplog.text


def test_negative_g4f_timeouts_are_clamped_to_zero(caplog):
    caplog.set_level(logging.WARNING)
    settings = Settings(
        SECRET_KEY="custom-secret",
        LLM_PROVIDER="g4f",
        LLM_FALLBACK_PROVIDER="groq",
        G4F_PROVIDERS="DeepInfra",
        LLM_CALL_TIMEOUT_MATCH_G4F=-12,
        G4F_TIMEOUT_BUFFER_SECONDS=-1,
    )

    assert settings.LLM_CALL_TIMEOUT_MATCH_G4F == 0
    assert settings.G4F_TIMEOUT_BUFFER_SECONDS == 0.0
    assert "LLM_CALL_TIMEOUT_MATCH_G4F=-12 is invalid" in caplog.text
    assert "G4F_TIMEOUT_BUFFER_SECONDS=-1.0 is invalid" in caplog.text
