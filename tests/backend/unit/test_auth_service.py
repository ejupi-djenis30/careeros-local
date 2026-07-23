from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.api.deps import limiter
from backend.db.base import get_db
from backend.main import app
from backend.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    get_password_hash,
    verify_password,
)

client = TestClient(app, raise_server_exceptions=False)

REFRESH_COOKIE_NAME = "careeros_refresh_token"
LEGACY_REFRESH_COOKIE_NAME = "jh_refresh_token"


def _cookie_was_deleted(response, cookie_name):
    return any(
        header.startswith(f"{cookie_name}=")
        and ("Max-Age=0" in header or "expires=" in header.lower())
        for header in response.headers.get_list("set-cookie")
    )


def test_register_success():
    client.cookies.clear()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[limiter] = (
        lambda: None
    )  # Assuming limiter bypass if possible, though slowapi usually ignores testclient

    with (
        patch("backend.api.routes.auth.create_access_token", return_value="access"),
        patch("backend.api.routes.auth.create_refresh_token", return_value="refresh"),
        patch("backend.api.routes.auth.get_password_hash", return_value="hash"),
    ):
        response = client.post(
            "/api/v1/auth/register", json={"username": "newuser", "password": "NewPassword1!"}
        )
        assert response.status_code == 200
        assert response.json() == {
            "access_token": "access",
            "token_type": "bearer",
            "username": "newuser",
        }
        assert f"{REFRESH_COOKIE_NAME}=refresh" in response.headers.get("set-cookie", "")
        assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies

    app.dependency_overrides.clear()


def test_register_existing_user():
    mock_db = MagicMock()
    mock_user = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user
    app.dependency_overrides[get_db] = lambda: mock_db

    response = client.post(
        "/api/v1/auth/register", json={"username": "exist", "password": "ExistUserPwd1!"}
    )
    assert response.status_code == 400
    assert "Registration failed" in response.json()["detail"]
    app.dependency_overrides.clear()


def test_login_success():
    client.cookies.clear()
    client.cookies.set(
        LEGACY_REFRESH_COOKIE_NAME, "legacy-session", domain="testserver.local", path="/"
    )
    mock_db = MagicMock()
    mock_user = MagicMock(username="user", hashed_password="pwd")
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user
    app.dependency_overrides[get_db] = lambda: mock_db

    with (
        patch("backend.api.routes.auth.verify_password", return_value=True),
        patch("backend.api.routes.auth.get_password_hash") as mock_hash,
        patch("backend.api.routes.auth.create_access_token", return_value="acc"),
        patch("backend.api.routes.auth.create_refresh_token", return_value="ref"),
    ):
        response = client.post("/api/v1/auth/login", data={"username": "user", "password": "pwd"})
        assert response.status_code == 200
        assert response.json()["access_token"] == "acc"
        assert f"{REFRESH_COOKIE_NAME}=ref" in response.headers.get("set-cookie", "")
        assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies
        assert _cookie_was_deleted(response, LEGACY_REFRESH_COOKIE_NAME)
        mock_hash.assert_not_called()

    app.dependency_overrides.clear()


def test_login_failure():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db

    with (
        patch("backend.api.routes.auth.get_password_hash") as mock_hash,
        patch("backend.api.routes.auth.verify_password", return_value=False) as mock_verify,
    ):
        response = client.post(
            "/api/v1/auth/login", data={"username": "user", "password": "pwd"}
        )
        assert response.status_code == 401
        mock_hash.assert_not_called()
        mock_verify.assert_called_once()
        assert mock_verify.call_args.args[1].startswith("$2b$")

    app.dependency_overrides.clear()


def test_refresh_success():
    client.cookies.clear()
    mock_db = MagicMock()
    mock_user = MagicMock(username="user")
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user
    app.dependency_overrides[get_db] = lambda: mock_db

    with (
        patch("backend.api.routes.auth.decode_refresh_token", return_value={"sub": "user"}),
        patch("backend.api.routes.auth.create_access_token", return_value="acc2"),
        patch("backend.api.routes.auth.create_refresh_token", return_value="ref2"),
    ):
        client.cookies.set(
            LEGACY_REFRESH_COOKIE_NAME, "old_ref", domain="testserver.local", path="/"
        )
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 200
        assert response.json()["access_token"] == "acc2"
        assert f"{REFRESH_COOKIE_NAME}=ref2" in response.headers.get("set-cookie", "")
        assert REFRESH_COOKIE_NAME in client.cookies
        assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies
        assert _cookie_was_deleted(response, LEGACY_REFRESH_COOKIE_NAME)

    app.dependency_overrides.clear()
    client.cookies.clear()


def test_refresh_prefers_canonical_cookie_and_removes_legacy_cookie():
    client.cookies.clear()
    client.cookies.set(
        REFRESH_COOKIE_NAME, "current_ref", domain="testserver.local", path="/"
    )
    client.cookies.set(
        LEGACY_REFRESH_COOKIE_NAME, "legacy_ref", domain="testserver.local", path="/"
    )
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(username="user")
    app.dependency_overrides[get_db] = lambda: mock_db

    with (
        patch(
            "backend.api.routes.auth.decode_refresh_token", return_value={"sub": "user"}
        ) as decode_refresh,
        patch("backend.api.routes.auth.create_access_token", return_value="access"),
        patch("backend.api.routes.auth.create_refresh_token", return_value="rotated"),
    ):
        response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    decode_refresh.assert_called_once_with("current_ref")
    assert client.cookies.get(REFRESH_COOKIE_NAME) == "rotated"
    assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies
    assert _cookie_was_deleted(response, LEGACY_REFRESH_COOKIE_NAME)

    app.dependency_overrides.clear()
    client.cookies.clear()


def test_refresh_vanished_user():
    client.cookies.clear()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch("backend.api.routes.auth.decode_refresh_token", return_value={"sub": "user"}):
        client.cookies.set(
            LEGACY_REFRESH_COOKIE_NAME, "old_ref", domain="testserver.local", path="/"
        )
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 401
        assert response.json()["detail"] == "User vanished"
        assert REFRESH_COOKIE_NAME not in client.cookies
        assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies

    app.dependency_overrides.clear()
    client.cookies.clear()


def test_logout():
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE_NAME, "current", domain="testserver.local", path="/")
    client.cookies.set(
        LEGACY_REFRESH_COOKIE_NAME, "legacy", domain="testserver.local", path="/"
    )
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert _cookie_was_deleted(response, REFRESH_COOKIE_NAME)
    assert _cookie_was_deleted(response, LEGACY_REFRESH_COOKIE_NAME)
    assert REFRESH_COOKIE_NAME not in client.cookies
    assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies


def test_password_hashing():
    pwd = "my_secure_password"
    hashed = get_password_hash(pwd)
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrong", hashed) is False


def test_password_verify_value_error():
    assert verify_password("plain", "not_a_valid_hash") is False  # triggers ValueError from bcrypt


def test_create_and_decode_access_token():
    token = create_access_token({"sub": "user"})
    decoded = decode_access_token(token)
    assert decoded["sub"] == "user"
    assert decoded["type"] == "access"


def test_create_and_decode_refresh_token():
    token = create_refresh_token({"sub": "user"})
    decoded = decode_refresh_token(token)
    assert decoded["sub"] == "user"
    assert decoded["type"] == "refresh"


def test_decode_invalid_token():
    assert decode_access_token("invalid.token.here") is None
    assert decode_refresh_token("invalid.token.here") is None


def test_decode_wrong_type_token():
    access_token = create_access_token({"sub": "user"})
    refresh_token = create_refresh_token({"sub": "user"})

    assert decode_access_token(refresh_token) is None
    assert decode_refresh_token(access_token) is None
