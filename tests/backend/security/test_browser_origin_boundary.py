"""Browser-origin checks for credentialed local account routes."""

from __future__ import annotations

import json

import pytest

from backend.api.routes.auth import (
    REFRESH_COOKIE_NAME,
    _require_trusted_browser_origin,
)
from backend.api.routes.auth import router as auth_router
from backend.core.config import settings
from backend.repositories.user_repository import UserRepository

AUTH_POST_PATHS = {
    "/register",
    "/login",
    "/refresh",
    "/logout",
}


def _blocked_origin_headers(mode: str):
    if mode == "unrelated":
        return {"Origin": "http://localhost:43111"}
    if mode == "null":
        return {"Origin": "null"}
    if mode == "concatenated":
        return {
            "Origin": "http://localhost:5173, http://127.0.0.1:5173",
        }
    if mode == "duplicated":
        return [
            ("Origin", "http://localhost:5173"),
            ("Origin", "http://127.0.0.1:5173"),
        ]
    raise AssertionError(f"Unknown origin mode: {mode}")


def _auth_request_kwargs(path: str) -> dict:
    if path == "/register":
        return {
            "json": {
                "username": "csrf_should_not_exist",
                "password": "CsrfSecure1",
            }
        }
    if path == "/login":
        return {
            "data": {
                "username": "globaladmin",
                "password": "Globalpass1",
            }
        }
    return {"json": {}}


def test_every_cookie_auth_post_has_the_origin_dependency() -> None:
    routes = {
        route.path: route
        for route in auth_router.routes
        if "POST" in getattr(route, "methods", set())
    }

    assert set(routes) == AUTH_POST_PATHS
    for route in routes.values():
        assert _require_trusted_browser_origin in {
            dependency.call for dependency in route.dependant.dependencies
        }


def test_arbitrary_localhost_port_cannot_cross_credentialed_cors_boundary(
    client,
    test_user,
) -> None:
    allowed_origin = "http://localhost:5173"
    unrelated_local_origin = "http://localhost:43111"
    preflight_headers = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    }

    allowed = client.options(
        "/api/v1/automation/grants",
        headers={"Origin": allowed_origin, **preflight_headers},
    )
    blocked = client.options(
        "/api/v1/automation/grants",
        headers={"Origin": unrelated_local_origin, **preflight_headers},
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == allowed_origin
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert blocked.status_code == 400
    assert "access-control-allow-origin" not in blocked.headers

    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
    )
    assert login.status_code == 200
    cross_origin_refresh = client.post(
        "/api/v1/auth/refresh",
        json={},
        headers={"Origin": unrelated_local_origin},
    )
    assert cross_origin_refresh.status_code == 403
    assert cross_origin_refresh.json() == {"detail": "Browser origin is not allowed"}
    assert "access_token" not in cross_origin_refresh.json()
    assert "set-cookie" not in cross_origin_refresh.headers
    assert "access-control-allow-origin" not in cross_origin_refresh.headers

    null_origin_refresh = client.post(
        "/api/v1/auth/refresh",
        headers={"Origin": "null"},
    )
    assert null_origin_refresh.status_code == 403
    assert "set-cookie" not in null_origin_refresh.headers

    allowed_refresh = client.post(
        "/api/v1/auth/refresh",
        headers={"Origin": allowed_origin},
    )
    assert allowed_refresh.status_code == 200
    assert "access_token" in allowed_refresh.json()
    assert allowed_refresh.headers["access-control-allow-origin"] == allowed_origin
    assert REFRESH_COOKIE_NAME in allowed_refresh.headers["set-cookie"]


@pytest.mark.parametrize("path", sorted(AUTH_POST_PATHS))
@pytest.mark.parametrize(
    "origin_mode",
    ["unrelated", "null", "concatenated", "duplicated"],
)
def test_every_cookie_auth_post_rejects_ambiguous_or_untrusted_origins_without_mutation(
    client,
    db_session,
    test_user,
    path: str,
    origin_mode: str,
) -> None:
    del test_user
    response = client.post(
        f"/api/v1/auth{path}",
        headers=_blocked_origin_headers(origin_mode),
        **_auth_request_kwargs(path),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Browser origin is not allowed"}
    assert "access_token" not in response.json()
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store, max-age=0"
    if path == "/register":
        db_session.expire_all()
        assert UserRepository(db_session).get_by_username("csrf_should_not_exist") is None


@pytest.mark.parametrize("path", sorted(AUTH_POST_PATHS))
@pytest.mark.parametrize("fetch_site", ["cross-site", "same-site", "none"])
def test_fetch_metadata_cannot_hide_a_missing_browser_origin(
    client,
    db_session,
    test_user,
    path: str,
    fetch_site: str,
) -> None:
    del test_user
    response = client.post(
        f"/api/v1/auth{path}",
        headers={"Sec-Fetch-Site": fetch_site},
        **_auth_request_kwargs(path),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Browser origin is not allowed"}
    assert "access_token" not in response.json()
    assert "set-cookie" not in response.headers
    if path == "/register":
        db_session.expire_all()
        assert UserRepository(db_session).get_by_username("csrf_should_not_exist") is None


def test_native_callers_without_origin_or_fetch_metadata_remain_supported(
    client,
    test_user,
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
    )

    assert response.status_code == 200
    assert "access_token" in response.json()


def test_missing_origin_with_same_origin_fetch_metadata_remains_supported(
    client,
    test_user,
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
        headers={"Sec-Fetch-Site": "same-origin"},
    )

    assert response.status_code == 200
    assert "access_token" in response.json()


def test_blocked_logout_does_not_cancel_the_existing_refresh_session(
    client,
    test_user,
) -> None:
    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
    )
    assert login.status_code == 200

    blocked_logout = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://localhost:43111"},
    )
    assert blocked_logout.status_code == 403
    assert "set-cookie" not in blocked_logout.headers

    retained_session = client.post(
        "/api/v1/auth/refresh",
        headers={"Origin": "http://localhost:5173"},
    )
    assert retained_session.status_code == 200
    assert "access_token" in retained_session.json()


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
)
def test_each_configured_browser_origin_can_complete_every_cookie_auth_post(
    client,
    test_user,
    origin: str,
) -> None:
    username = "allowed_localhost" if origin == "http://localhost:5173" else "allowed_ipv4_loopback"
    register = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "AllowedSecure1"},
        headers={"Origin": origin},
    )
    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
        headers={"Origin": origin},
    )
    refresh = client.post(
        "/api/v1/auth/refresh",
        headers={"Origin": origin},
    )
    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": origin},
    )

    for response in (register, login, refresh, logout):
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers["cache-control"] == "no-store, max-age=0"
    for response in (register, login, refresh):
        assert "access_token" in response.json()
        assert REFRESH_COOKIE_NAME in response.headers["set-cookie"]
    assert REFRESH_COOKIE_NAME in logout.headers["set-cookie"]


@pytest.mark.parametrize(
    "origin",
    [
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ],
)
def test_configured_tauri_origins_can_use_cookie_auth_routes(
    client,
    test_user,
    monkeypatch,
    origin: str,
) -> None:
    monkeypatch.setattr(
        settings,
        "CORS_ORIGINS",
        json.dumps(
            [
                "http://tauri.localhost",
                "https://tauri.localhost",
                "tauri://localhost",
            ]
        ),
    )

    response = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
        headers={"Origin": origin},
    )

    assert response.status_code == 200
    assert "access_token" in response.json()
    assert REFRESH_COOKIE_NAME in response.headers["set-cookie"]
