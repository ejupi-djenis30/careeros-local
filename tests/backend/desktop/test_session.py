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
