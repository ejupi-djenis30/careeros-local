from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.testclient import TestClient

from backend.api.middleware import PrivatePathNoStoreMiddleware
from backend.desktop.session import DesktopSessionMiddleware

PRIVATE_PATH = "/api/v1/automation/grants"


def _assert_private(response) -> None:
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"


def test_private_headers_wrap_trusted_host_early_response() -> None:
    inner = FastAPI()
    trusted = TrustedHostMiddleware(inner, allowed_hosts=["allowed.local"])
    app = PrivatePathNoStoreMiddleware(trusted, path_prefix=PRIVATE_PATH)

    response = TestClient(app).get(PRIVATE_PATH, headers={"host": "untrusted.invalid"})

    assert response.status_code == 400
    _assert_private(response)


def test_private_headers_wrap_desktop_session_early_response() -> None:
    inner = FastAPI()
    desktop = DesktopSessionMiddleware(inner, token="s" * 32)
    app = PrivatePathNoStoreMiddleware(desktop, path_prefix=PRIVATE_PATH)

    response = TestClient(app).get(PRIVATE_PATH)

    assert response.status_code == 403
    _assert_private(response)


def test_private_headers_do_not_leak_to_other_routes() -> None:
    inner = FastAPI()

    @inner.get("/api/v1/health/live")
    def health() -> dict[str, str]:
        return {"status": "alive"}

    app = PrivatePathNoStoreMiddleware(inner, path_prefix=PRIVATE_PATH)

    response = TestClient(app).get("/api/v1/health/live")

    assert response.status_code == 200
    assert "cache-control" not in response.headers
    assert "pragma" not in response.headers
