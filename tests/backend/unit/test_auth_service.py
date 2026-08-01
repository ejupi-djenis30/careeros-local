from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException, Response
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from backend.api.deps import limiter
from backend.api.routes.auth import REFRESH_COOKIE_PATH, register
from backend.core.config import settings
from backend.db.base import get_db
from backend.main import app
from backend.schemas.user import UserCreate
from backend.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    get_password_hash,
    verify_password,
)
from backend.services.auth_sessions import AuthSessionTokens

client = TestClient(app, raise_server_exceptions=False)

REFRESH_COOKIE_NAME = "careeros_refresh_token"
LEGACY_REFRESH_COOKIE_NAME = "jh_refresh_token"


def _session_tokens(
    *,
    username: str = "user",
    access_token: str = "access",
    refresh_token: str = "refresh",
) -> AuthSessionTokens:
    return AuthSessionTokens(
        username=username,
        session_id="a" * 32,
        access_token=access_token,
        refresh_token=refresh_token,
    )


def _cookie_header_has_path(header, path):
    return f"Path={path}" in {part.strip() for part in header.split(";")}


def _cookie_was_deleted(response, cookie_name, path=None):
    return any(
        header.startswith(f"{cookie_name}=")
        and ("Max-Age=0" in header or "expires=" in header.lower())
        and (path is None or _cookie_header_has_path(header, path))
        for header in response.headers.get_list("set-cookie")
    )


def _assert_narrow_refresh_cookie(response, expected_value):
    headers = response.headers.get_list("set-cookie")
    assert any(
        header.startswith(f"{REFRESH_COOKIE_NAME}={expected_value}")
        and _cookie_header_has_path(header, REFRESH_COOKIE_PATH)
        and "HttpOnly" in header
        and "SameSite=lax" in header
        and "Max-Age=0" not in header
        for header in headers
    )
    assert _cookie_was_deleted(response, REFRESH_COOKIE_NAME, "/")
    assert _cookie_was_deleted(response, LEGACY_REFRESH_COOKIE_NAME, "/")
    assert _cookie_was_deleted(response, LEGACY_REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH)


def test_register_success():
    client.cookies.clear()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[limiter] = lambda: (
        None
    )  # Assuming limiter bypass if possible, though slowapi usually ignores testclient

    with (
        patch(
            "backend.api.routes.auth.issue_auth_session",
            return_value=_session_tokens(),
        ),
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
        _assert_narrow_refresh_cookie(response, "refresh")
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


def test_register_unique_constraint_race_returns_generic_failure_without_session():
    client.cookies.clear()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db

    with (
        patch(
            "backend.api.routes.auth.UserRepository.create",
            side_effect=IntegrityError(
                "INSERT INTO users",
                {"username": "racing_user"},
                RuntimeError("unique constraint"),
            ),
        ),
        patch("backend.api.routes.auth.issue_auth_session") as issue_session,
    ):
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "racing_user", "password": "RacePassword1!"},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Registration failed. Please try a different username."}
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert "set-cookie" not in response.headers
    assert "unique constraint" not in response.text
    issue_session.assert_not_called()
    app.dependency_overrides.clear()


def test_register_unique_constraint_race_suppresses_database_exception_cause():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    database_detail = "unique constraint with sensitive SQL parameters"

    with (
        patch(
            "backend.api.routes.auth.UserRepository.create",
            side_effect=IntegrityError(
                "INSERT INTO users",
                {"hashed_password": database_detail},
                RuntimeError(database_detail),
            ),
        ),
        patch("backend.api.routes.auth.get_password_hash", return_value="redacted-hash"),
        pytest.raises(HTTPException) as failure,
    ):
        original_register = getattr(register, "__wrapped__", register)
        original_register(
            MagicMock(),
            Response(),
            UserCreate(username="racing_user", password="RacePassword1!"),
            mock_db,
        )

    assert failure.value.status_code == 400
    assert failure.value.__cause__ is None
    assert database_detail not in str(failure.value)


def test_registration_rejects_passwords_beyond_bcrypt_utf8_limit_without_mutation():
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    for password in ("A1" + ("x" * 71), "A1" + ("é" * 36)):
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "oversized_password", "password": password},
        )

        assert response.status_code == 422
        assert response.headers["cache-control"] == "no-store, max-age=0"
        assert "set-cookie" not in response.headers
        assert password not in response.text
    mock_db.query.assert_not_called()
    app.dependency_overrides.clear()


def test_registration_accepts_the_exact_bcrypt_utf8_boundary():
    password = "A1" + ("x" * 70)

    assert len(password.encode("utf-8")) == 72
    assert UserCreate(username="boundary_user", password=password).password == password


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
        patch(
            "backend.api.routes.auth.issue_auth_session",
            return_value=_session_tokens(access_token="acc", refresh_token="ref"),
        ),
    ):
        response = client.post("/api/v1/auth/login", data={"username": "user", "password": "pwd"})
        assert response.status_code == 200
        assert response.json()["access_token"] == "acc"
        assert f"{REFRESH_COOKIE_NAME}=ref" in response.headers.get("set-cookie", "")
        _assert_narrow_refresh_cookie(response, "ref")
        assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies
        assert _cookie_was_deleted(response, LEGACY_REFRESH_COOKIE_NAME)
        mock_hash.assert_not_called()

    app.dependency_overrides.clear()


def test_login_rejects_oversized_password_before_database_or_bcrypt_work():
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch("backend.api.routes.auth.verify_password") as verify:
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "user", "password": "A1" + ("é" * 36)},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Credential fields exceed supported limits"}
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert "set-cookie" not in response.headers
    mock_db.query.assert_not_called()
    verify.assert_not_called()
    app.dependency_overrides.clear()


def test_login_failure():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db

    with (
        patch("backend.api.routes.auth.get_password_hash") as mock_hash,
        patch("backend.api.routes.auth.verify_password", return_value=False) as mock_verify,
    ):
        response = client.post("/api/v1/auth/login", data={"username": "user", "password": "pwd"})
        assert response.status_code == 401
        mock_hash.assert_not_called()
        mock_verify.assert_called_once()
        assert mock_verify.call_args.args[1].startswith("$2b$")

    app.dependency_overrides.clear()


def test_refresh_success():
    client.cookies.clear()
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    with (
        patch(
            "backend.api.routes.auth.rotate_refresh_session",
            return_value=_session_tokens(access_token="acc2", refresh_token="ref2"),
        ),
    ):
        client.cookies.set(
            LEGACY_REFRESH_COOKIE_NAME, "old_ref", domain="testserver.local", path="/"
        )
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 200
        assert response.json()["access_token"] == "acc2"
        assert f"{REFRESH_COOKIE_NAME}=ref2" in response.headers.get("set-cookie", "")
        _assert_narrow_refresh_cookie(response, "ref2")
        assert REFRESH_COOKIE_NAME in client.cookies
        assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies
        assert _cookie_was_deleted(response, LEGACY_REFRESH_COOKIE_NAME)

    app.dependency_overrides.clear()
    client.cookies.clear()


def test_refresh_prefers_canonical_cookie_and_removes_legacy_cookie():
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE_NAME, "current_ref", domain="testserver.local", path="/")
    client.cookies.set(
        LEGACY_REFRESH_COOKIE_NAME, "legacy_ref", domain="testserver.local", path="/"
    )
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    with (
        patch(
            "backend.api.routes.auth.rotate_refresh_session",
            return_value=_session_tokens(access_token="access", refresh_token="rotated"),
        ) as rotate_refresh,
    ):
        response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    assert rotate_refresh.call_args.args[1] == "current_ref"
    _assert_narrow_refresh_cookie(response, "rotated")
    assert client.cookies.get(REFRESH_COOKIE_NAME) == "rotated"
    assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies
    assert _cookie_was_deleted(response, LEGACY_REFRESH_COOKIE_NAME)

    app.dependency_overrides.clear()
    client.cookies.clear()


def test_refresh_rejects_a_token_without_live_server_side_state():
    client.cookies.clear()
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch("backend.api.routes.auth.rotate_refresh_session", return_value=None):
        client.cookies.set(
            LEGACY_REFRESH_COOKIE_NAME, "old_ref", domain="testserver.local", path="/"
        )
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid refresh token"
        assert REFRESH_COOKIE_NAME not in client.cookies
        assert LEGACY_REFRESH_COOKIE_NAME not in client.cookies

    app.dependency_overrides.clear()
    client.cookies.clear()


def test_logout():
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE_NAME, "current", domain="testserver.local", path="/")
    client.cookies.set(LEGACY_REFRESH_COOKIE_NAME, "legacy", domain="testserver.local", path="/")
    with patch("backend.api.routes.auth.revoke_presented_sessions") as revoke:
        response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert revoke.call_args.kwargs == {
        "refresh_token": "current",
        "access_token": None,
    }
    assert _cookie_was_deleted(response, REFRESH_COOKIE_NAME)
    assert _cookie_was_deleted(response, LEGACY_REFRESH_COOKIE_NAME)
    for cookie_name in (REFRESH_COOKIE_NAME, LEGACY_REFRESH_COOKIE_NAME):
        assert _cookie_was_deleted(response, cookie_name, "/")
        assert _cookie_was_deleted(response, cookie_name, REFRESH_COOKIE_PATH)
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
    token = create_access_token({"sub": "user"}, session_id="b" * 32)
    decoded = decode_access_token(token)
    assert decoded["sub"] == "user"
    assert decoded["type"] == "access"
    assert len(decoded["jti"]) == 32
    assert decoded["sid"] == "b" * 32
    assert isinstance(decoded["iat"], int)


def test_create_and_decode_refresh_token():
    token = create_refresh_token({"sub": "user"})
    decoded = decode_refresh_token(token)
    assert decoded["sub"] == "user"
    assert decoded["type"] == "refresh"
    assert len(decoded["jti"]) == 32
    assert len(decoded["sid"]) == 32
    assert isinstance(decoded["iat"], int)


def test_refresh_rotation_always_issues_a_distinct_token():
    first = create_refresh_token({"sub": "user"})
    second = create_refresh_token({"sub": "user"})

    assert first != second
    assert decode_refresh_token(first)["jti"] != decode_refresh_token(second)["jti"]


def test_access_decoder_rejects_a_signed_token_without_an_explicit_type():
    token = jwt.encode(
        {
            "sub": "user",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    assert decode_access_token(token) is None


@pytest.mark.parametrize("missing", ["exp", "iat", "jti", "sid", "sub", "type"])
def test_access_decoder_requires_every_security_claim(missing):
    claims = {
        "sub": "user",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        "iat": datetime.now(timezone.utc),
        "jti": "a" * 32,
        "sid": "b" * 32,
        "type": "access",
    }
    del claims[missing]
    token = jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    assert decode_access_token(token) is None


@pytest.mark.parametrize("missing", ["exp", "iat", "jti", "sid", "sub", "type"])
def test_refresh_decoder_requires_every_security_claim(missing):
    claims = {
        "sub": "user",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        "iat": datetime.now(timezone.utc),
        "jti": "a" * 32,
        "sid": "b" * 32,
        "type": "refresh",
    }
    del claims[missing]
    token = jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    assert decode_refresh_token(token) is None


def test_decode_invalid_token():
    assert decode_access_token("invalid.token.here") is None
    assert decode_refresh_token("invalid.token.here") is None


def test_decode_wrong_type_token():
    access_token = create_access_token({"sub": "user"}, session_id="b" * 32)
    refresh_token = create_refresh_token({"sub": "user"})

    assert decode_access_token(refresh_token) is None
    assert decode_refresh_token(access_token) is None
