from __future__ import annotations

from pathlib import Path

import pytest

from backend.desktop.settings import DesktopRuntimeSettings


def test_browser_mode_has_no_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CAREEROS_DESKTOP_MODE", raising=False)
    monkeypatch.delenv("CAREEROS_DESKTOP_SESSION_TOKEN", raising=False)
    settings = DesktopRuntimeSettings.from_environment()
    assert settings.enabled is False
    assert settings.session_token == ""


def test_desktop_mode_requires_private_loopback_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = (Path.cwd() / ".artifacts" / "desktop-settings").resolve()
    monkeypatch.setenv("CAREEROS_DESKTOP_MODE", "1")
    monkeypatch.setenv("CAREEROS_DESKTOP_SESSION_TOKEN", "s" * 43)
    monkeypatch.setenv("CAREEROS_DESKTOP_HOST", "127.0.0.1")
    monkeypatch.setenv("CAREEROS_DESKTOP_PORT", "43127")
    monkeypatch.setenv("CAREEROS_DESKTOP_DATA_DIR", str(data_dir))
    settings = DesktopRuntimeSettings.from_environment()
    assert settings.enabled is True
    assert settings.host == "127.0.0.1"
    assert settings.port == 43127
    assert settings.data_dir == data_dir
    assert settings.database_path == data_dir / "vault" / "careeros.db"


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("CAREEROS_DESKTOP_HOST", "0.0.0.0", "loopback"),
        ("CAREEROS_DESKTOP_SESSION_TOKEN", "short", "session token"),
        ("CAREEROS_DESKTOP_PORT", "70000", "port"),
        ("CAREEROS_DESKTOP_DATA_DIR", "relative/data", "absolute"),
    ],
)
def test_desktop_mode_rejects_unsafe_values(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    data_dir = (Path.cwd() / ".artifacts" / "desktop-settings").resolve()
    monkeypatch.setenv("CAREEROS_DESKTOP_MODE", "true")
    monkeypatch.setenv("CAREEROS_DESKTOP_SESSION_TOKEN", "s" * 43)
    monkeypatch.setenv("CAREEROS_DESKTOP_HOST", "127.0.0.1")
    monkeypatch.setenv("CAREEROS_DESKTOP_PORT", "43127")
    monkeypatch.setenv("CAREEROS_DESKTOP_DATA_DIR", str(data_dir))
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=message):
        DesktopRuntimeSettings.from_environment()
