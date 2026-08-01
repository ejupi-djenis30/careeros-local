from __future__ import annotations

import threading
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes.desktop import (
    DesktopShutdownController,
    desktop_shutdown_controller,
    router,
)
from backend.desktop.session import DesktopSessionMiddleware

SESSION_TOKEN = "desktop-shutdown-test-" + "x" * 48


def _desktop_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/desktop")
    app.add_middleware(DesktopSessionMiddleware, token=SESSION_TOKEN)
    return app


def _configure_desktop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CAREEROS_DESKTOP_MODE", "1")
    monkeypatch.setenv("CAREEROS_DESKTOP_HOST", "127.0.0.1")
    monkeypatch.setenv("CAREEROS_DESKTOP_PORT", "43127")
    monkeypatch.setenv("CAREEROS_DESKTOP_SESSION_TOKEN", SESSION_TOKEN)
    monkeypatch.setenv("CAREEROS_DESKTOP_DATA_DIR", str(tmp_path.resolve()))


def test_desktop_shutdown_requires_launch_token_and_invokes_bound_handler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_desktop(monkeypatch, tmp_path)
    requested = threading.Event()

    with desktop_shutdown_controller.bind(requested.set):
        with TestClient(_desktop_app(), raise_server_exceptions=False) as client:
            missing = client.post("/api/v1/desktop/shutdown")
            invalid = client.post(
                "/api/v1/desktop/shutdown",
                headers={"X-CareerOS-Session": "wrong-" + "x" * 40},
            )
            accepted = client.post(
                "/api/v1/desktop/shutdown",
                headers={"X-CareerOS-Session": SESSION_TOKEN},
            )

    assert missing.status_code == 403
    assert invalid.status_code == 403
    assert accepted.status_code == 202
    assert accepted.json() == {"status": "shutting_down"}
    assert requested.is_set()


def test_desktop_shutdown_is_not_exposed_in_browser_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CAREEROS_DESKTOP_MODE", raising=False)
    requested = threading.Event()

    with desktop_shutdown_controller.bind(requested.set):
        response = TestClient(_desktop_app(), raise_server_exceptions=False).post(
            "/api/v1/desktop/shutdown",
            headers={"X-CareerOS-Session": SESSION_TOKEN},
        )

    assert response.status_code == 404
    assert not requested.is_set()


def test_desktop_shutdown_reports_unavailable_without_a_bound_server(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_desktop(monkeypatch, tmp_path)
    response = TestClient(_desktop_app(), raise_server_exceptions=False).post(
        "/api/v1/desktop/shutdown",
        headers={"X-CareerOS-Session": SESSION_TOKEN},
    )
    assert response.status_code == 503


def test_desktop_shutdown_controller_allows_only_one_server_binding() -> None:
    controller = DesktopShutdownController()
    first = threading.Event()
    second = threading.Event()

    with controller.bind(first.set):
        assert controller.request() is True
        with pytest.raises(RuntimeError, match="already bound"):
            with controller.bind(second.set):
                pass

    assert first.is_set()
    assert not second.is_set()
    assert controller.request() is False
