from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.desktop.session import DesktopSessionMiddleware


def _client(token: str = "t" * 43) -> TestClient:
    app = FastAPI()
    app.add_middleware(DesktopSessionMiddleware, token=token)

    @app.get("/private")
    def private() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_desktop_session_rejects_missing_and_wrong_tokens() -> None:
    with _client() as client:
        missing = client.get("/private")
        wrong = client.get("/private", headers={"X-CareerOS-Session": "x" * 43})

        for response in (missing, wrong):
            assert response.status_code == 403
            assert response.json() == {"detail": "Desktop session authorization failed"}
            assert response.headers["cache-control"] == "no-store, max-age=0"
            assert response.headers["pragma"] == "no-cache"


def test_desktop_session_accepts_exact_token_and_preflight() -> None:
    token = "t" * 43
    with _client(token) as client:
        assert client.get("/private", headers={"X-CareerOS-Session": token}).json() == {"ok": True}
        assert client.options("/private").status_code != 403


def test_desktop_session_rejects_ambiguous_duplicate_headers() -> None:
    token = "t" * 43
    with _client(token) as client:
        for duplicate in (
            [("X-CareerOS-Session", token), ("X-CareerOS-Session", "x" * 43)],
            [("X-CareerOS-Session", token), ("X-CareerOS-Session", token)],
        ):
            response = client.get("/private", headers=duplicate)
            assert response.status_code == 403
            assert response.json() == {"detail": "Desktop session authorization failed"}


def test_desktop_session_allows_only_fixed_bridge_operations() -> None:
    token = "t" * 43
    app = FastAPI()
    app.add_middleware(
        DesktopSessionMiddleware,
        token=token,
        exempt_path_prefix="/api/v1/agent-bridge",
    )

    @app.get("/api/v1/agent-bridge/status")
    def bridge_status() -> dict[str, bool]:
        return {"bridge": True}

    @app.get("/api/v1/owner")
    def owner() -> dict[str, bool]:
        return {"owner": True}

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        # Bridge route should succeed without X-CareerOS-Session
        res = client.get("/api/v1/agent-bridge/status")
        assert res.status_code == 200
        assert res.json() == {"bridge": True}

        # Non-exempt route should fail without X-CareerOS-Session
        res = client.get("/api/v1/owner")
        assert res.status_code == 403

        # Non-exempt route should succeed with X-CareerOS-Session
        res = client.get("/api/v1/owner", headers={"X-CareerOS-Session": token})
        assert res.status_code == 200


def test_bridge_prefix_does_not_exempt_unknown_routes_methods_or_origins():
    app = FastAPI()
    app.add_middleware(
        DesktopSessionMiddleware, token="t" * 43, exempt_path_prefix="/api/v1/agent-bridge"
    )
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        for method, path in [
            ("DELETE", "status"),
            ("POST", "status"),
            ("GET", "admin"),
            ("POST", "work-requests/not-a-uuid/result"),
        ]:
            response = client.request(method, "/api/v1/agent-bridge/" + path)
            assert response.status_code == 403
            assert "no-store" in response.headers["cache-control"]
        assert (
            client.get(
                "/api/v1/agent-bridge/status", headers={"Origin": "https://example.com"}
            ).status_code
            == 403
        )
