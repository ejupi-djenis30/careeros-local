import logging

from backend.core.config import Settings


def test_cors_origins_list_warns_and_falls_back(caplog):
    caplog.set_level(logging.WARNING)
    settings = Settings(CORS_ORIGINS='[invalid', SECRET_KEY='custom-secret')

    assert settings.cors_origins_list == ['[invalid']
    assert 'Invalid CORS_ORIGINS JSON' in caplog.text


def test_allowed_hosts_warns_and_falls_back(caplog):
    caplog.set_level(logging.WARNING)
    settings = Settings(ALLOWED_HOSTS='[invalid', SECRET_KEY='custom-secret')

    assert settings.ALLOWED_HOSTS == ['[invalid']
    assert 'Invalid ALLOWED_HOSTS JSON' in caplog.text