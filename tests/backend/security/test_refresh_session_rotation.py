from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import model_registry  # noqa: F401 - complete metadata for isolated engines
from backend.api.deps import get_current_user_id
from backend.api.routes.auth import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH
from backend.core.config import settings
from backend.db.base import Base, get_db
from backend.main import app
from backend.models.auth_session import AuthSession
from backend.models.user import VAULT_STATE_RESET_PENDING, User
from backend.services import auth_sessions
from backend.services.auth import decode_access_token, decode_refresh_token, get_password_hash
from backend.services.auth_sessions import (
    MAX_ACTIVE_REFRESH_SESSIONS,
    VaultMaintenancePendingError,
    issue_auth_session,
    issue_refresh_session,
    revoke_presented_sessions,
    rotate_refresh_session,
)


def test_normal_session_issue_rechecks_durable_lifecycle_state(
    db_session,
    test_user,
) -> None:
    # The caller can hold a stale ready User instance after password verification;
    # issuance must lock and refresh the database row before creating a family.
    assert test_user.vault_lifecycle_state != VAULT_STATE_RESET_PENDING
    test_user.vault_lifecycle_state = VAULT_STATE_RESET_PENDING
    db_session.commit()

    with pytest.raises(VaultMaintenancePendingError):
        issue_auth_session(db_session, test_user)

    assert db_session.query(AuthSession).filter(AuthSession.user_id == test_user.id).count() == 0


def _cookie_value(client, name: str) -> str:
    values = [cookie.value for cookie in client.cookies.jar if cookie.name == name]
    assert len(values) == 1
    return values[0]


def _set_refresh_cookie(client, token: str) -> None:
    client.cookies.clear()
    client.cookies.set(
        REFRESH_COOKIE_NAME,
        token,
        domain="testserver.local",
        path=REFRESH_COOKIE_PATH,
    )


def _access_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_access_is_live(client, token: str) -> None:
    response = client.get("/api/v1/career-profile/summary", headers=_access_headers(token))
    assert response.status_code == 404, response.text


def _assert_access_is_revoked(client, token: str) -> None:
    response = client.get("/api/v1/career-profile/summary", headers=_access_headers(token))
    assert response.status_code == 401, response.text
    assert response.json() == {"detail": "Invalid token"}


def test_refresh_rotation_persists_only_digest_and_replay_revokes_the_family(
    client, db_session, test_user
) -> None:
    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
    )
    assert login.status_code == 200, login.text
    first_access_token = login.json()["access_token"]
    first_token = _cookie_value(client, REFRESH_COOKIE_NAME)
    first_claims = decode_refresh_token(first_token)
    first_access_claims = decode_access_token(first_access_token)
    assert first_claims is not None
    assert first_access_claims is not None
    assert first_access_claims["sid"] == first_claims["sid"]
    _assert_access_is_live(client, first_access_token)

    row = db_session.get(AuthSession, first_claims["sid"])
    assert row is not None
    assert row.refresh_jti_digest == hashlib.sha256(first_claims["jti"].encode("ascii")).hexdigest()
    assert first_claims["jti"] not in row.refresh_jti_digest
    assert first_token not in row.refresh_jti_digest

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    second_access_token = refreshed.json()["access_token"]
    second_token = _cookie_value(client, REFRESH_COOKIE_NAME)
    second_claims = decode_refresh_token(second_token)
    second_access_claims = decode_access_token(second_access_token)
    assert second_claims is not None
    assert second_access_claims is not None
    assert second_claims["sid"] == first_claims["sid"]
    assert second_access_claims["sid"] == first_claims["sid"]
    assert second_claims["jti"] != first_claims["jti"]
    _assert_access_is_live(client, first_access_token)
    _assert_access_is_live(client, second_access_token)

    _set_refresh_cookie(client, first_token)
    replay = client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401
    assert replay.json() == {"detail": "Invalid refresh token"}

    db_session.expire_all()
    revoked = db_session.get(AuthSession, first_claims["sid"])
    assert revoked is not None
    assert revoked.revoked_at is not None
    _assert_access_is_revoked(client, first_access_token)
    _assert_access_is_revoked(client, second_access_token)

    _set_refresh_cookie(client, second_token)
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_revokes_server_state_before_clearing_the_cookie(
    client, db_session, test_user
) -> None:
    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
    )
    assert login.status_code == 200
    access_token = login.json()["access_token"]
    token = _cookie_value(client, REFRESH_COOKIE_NAME)
    claims = decode_refresh_token(token)
    assert claims is not None

    logged_out = client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 200
    db_session.expire_all()
    session = db_session.get(AuthSession, claims["sid"])
    assert session is not None
    assert session.revoked_at is not None
    _assert_access_is_revoked(client, access_token)

    _set_refresh_cookie(client, token)
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_revokes_the_access_family_when_the_refresh_cookie_is_missing(
    client, db_session, test_user
) -> None:
    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
    )
    assert login.status_code == 200, login.text
    access_token = login.json()["access_token"]
    claims = decode_access_token(access_token)
    assert claims is not None
    client.cookies.clear()

    logged_out = client.post(
        "/api/v1/auth/logout",
        headers=_access_headers(access_token),
    )

    assert logged_out.status_code == 200, logged_out.text
    db_session.expire_all()
    family = db_session.get(AuthSession, claims["sid"])
    assert family is not None
    assert family.revoked_at is not None
    _assert_access_is_revoked(client, access_token)


def test_logout_rejects_duplicate_authorization_headers_without_claiming_success(
    client, test_user
) -> None:
    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
    )
    access_token = login.json()["access_token"]
    client.cookies.clear()

    response = client.post(
        "/api/v1/auth/logout",
        headers=[
            ("Authorization", f"Bearer {access_token}"),
            ("Authorization", f"Bearer {access_token}"),
        ],
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Authorization header is invalid"}
    _assert_access_is_live(client, access_token)


def test_logout_with_a_rotated_old_token_revokes_the_winning_family(
    client, db_session, test_user
) -> None:
    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
    )
    assert login.status_code == 200
    old_token = _cookie_value(client, REFRESH_COOKIE_NAME)
    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    current_token = _cookie_value(client, REFRESH_COOKIE_NAME)
    claims = decode_refresh_token(current_token)
    assert claims is not None

    _set_refresh_cookie(client, old_token)
    assert client.post("/api/v1/auth/logout").status_code == 200
    db_session.expire_all()
    family = db_session.get(AuthSession, claims["sid"])
    assert family is not None
    assert family.revoked_at is not None

    _set_refresh_cookie(client, current_token)
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_pre_migration_refresh_token_without_session_id_fails_closed_and_is_cleared(
    client, test_user
) -> None:
    old_token = jwt.encode(
        {
            "sub": test_user.username,
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
            "iat": datetime.now(timezone.utc),
            "jti": "a" * 32,
            "type": "refresh",
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    _set_refresh_cookie(client, old_token)

    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid refresh token"}
    assert all(cookie.name != REFRESH_COOKIE_NAME for cookie in client.cookies.jar)


def test_pre_migration_access_token_without_session_id_fails_closed(client, test_user) -> None:
    old_token = jwt.encode(
        {
            "sub": test_user.username,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "iat": datetime.now(timezone.utc),
            "jti": "a" * 32,
            "type": "access",
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    response = client.get(
        "/api/v1/career-profile/summary",
        headers=_access_headers(old_token),
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token"}


def test_per_user_session_slots_are_hard_bounded(db_session, test_user) -> None:
    tokens = [
        issue_refresh_session(db_session, test_user)
        for _index in range(MAX_ACTIVE_REFRESH_SESSIONS + 3)
    ]

    sessions = (
        db_session.query(AuthSession)
        .filter(AuthSession.user_id == test_user.id)
        .order_by(AuthSession.slot.asc())
        .all()
    )
    assert len(sessions) == MAX_ACTIVE_REFRESH_SESSIONS
    assert {session.slot for session in sessions} == set(range(MAX_ACTIVE_REFRESH_SESSIONS))
    assert rotate_refresh_session(db_session, tokens[0]) is None
    assert rotate_refresh_session(db_session, tokens[-1]) is not None


def test_parallel_refresh_has_one_rotation_winner_then_revokes_the_family(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "refresh-race.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as setup:
        user = User(username="refresh-race", hashed_password=get_password_hash("Racepass1!"))
        setup.add(user)
        setup.commit()
        token = issue_refresh_session(setup, user)
        session_id = decode_refresh_token(token)["sid"]

    barrier = threading.Barrier(2)
    real_create = auth_sessions.create_refresh_token

    def synchronized_create(data, *, session_id=None):
        if session_id is not None:
            barrier.wait(timeout=10)
        return real_create(data, session_id=session_id)

    monkeypatch.setattr(auth_sessions, "create_refresh_token", synchronized_create)

    def rotate_once(_worker: int):
        with sessions() as db:
            return rotate_refresh_session(db, token)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(rotate_once, range(2)))
        assert sum(outcome is not None for outcome in outcomes) == 1
        assert sum(outcome is None for outcome in outcomes) == 1
        winner = next(outcome for outcome in outcomes if outcome is not None)
        with sessions() as verify:
            family = verify.get(AuthSession, session_id)
            assert family is not None
            assert family.revoked_at is not None
            with pytest.raises(HTTPException) as rejected:
                get_current_user_id(winner.access_token, verify)
            assert rejected.value.status_code == 401
    finally:
        engine.dispose()


def test_rotation_commit_failure_rolls_back_the_consumed_digest(
    db_session, test_user, monkeypatch
) -> None:
    token = issue_refresh_session(db_session, test_user)
    claims = decode_refresh_token(token)
    assert claims is not None
    before = db_session.get(AuthSession, claims["sid"])
    assert before is not None
    original_digest = before.refresh_jti_digest
    rollback = MagicMock(wraps=db_session.rollback)
    monkeypatch.setattr(db_session, "rollback", rollback)
    monkeypatch.setattr(db_session, "commit", MagicMock(side_effect=RuntimeError("disk full")))

    with pytest.raises(RuntimeError, match="disk full"):
        rotate_refresh_session(db_session, token)

    assert rollback.called
    db_session.expire_all()
    persisted = db_session.get(AuthSession, claims["sid"])
    assert persisted is not None
    assert persisted.refresh_jti_digest == original_digest
    assert persisted.revoked_at is None


def test_issue_commit_failure_rolls_back_without_returning_a_session(
    db_session, test_user, monkeypatch
) -> None:
    rollback = MagicMock(wraps=db_session.rollback)
    monkeypatch.setattr(db_session, "rollback", rollback)
    monkeypatch.setattr(db_session, "commit", MagicMock(side_effect=RuntimeError("read only")))

    with pytest.raises(RuntimeError, match="read only"):
        issue_refresh_session(db_session, test_user)

    assert rollback.called
    assert db_session.query(AuthSession).filter(AuthSession.user_id == test_user.id).count() == 0


def test_issue_access_generation_failure_rolls_back_slot_reclamation(
    db_session, test_user, monkeypatch
) -> None:
    existing = [
        issue_auth_session(db_session, test_user) for _index in range(MAX_ACTIVE_REFRESH_SESSIONS)
    ]
    existing_ids = {tokens.session_id for tokens in existing}
    rollback = MagicMock(wraps=db_session.rollback)
    monkeypatch.setattr(db_session, "rollback", rollback)
    monkeypatch.setattr(
        auth_sessions,
        "create_access_token",
        MagicMock(side_effect=RuntimeError("signing unavailable")),
    )

    with pytest.raises(RuntimeError, match="signing unavailable"):
        issue_auth_session(db_session, test_user)

    assert rollback.called
    db_session.expire_all()
    persisted_ids = {
        session_id
        for (session_id,) in db_session.query(AuthSession.id)
        .filter(AuthSession.user_id == test_user.id)
        .all()
    }
    assert persisted_ids == existing_ids


def test_rotation_access_generation_failure_preserves_the_current_refresh_digest(
    db_session, test_user, monkeypatch
) -> None:
    tokens = issue_auth_session(db_session, test_user)
    family = db_session.get(AuthSession, tokens.session_id)
    assert family is not None
    digest_before = family.refresh_jti_digest
    rollback = MagicMock(wraps=db_session.rollback)
    monkeypatch.setattr(db_session, "rollback", rollback)
    monkeypatch.setattr(
        auth_sessions,
        "create_access_token",
        MagicMock(side_effect=RuntimeError("signing unavailable")),
    )

    with pytest.raises(RuntimeError, match="signing unavailable"):
        rotate_refresh_session(db_session, tokens.refresh_token)

    assert rollback.called
    db_session.expire_all()
    persisted = db_session.get(AuthSession, tokens.session_id)
    assert persisted is not None
    assert persisted.refresh_jti_digest == digest_before
    assert persisted.revoked_at is None


def test_logout_revokes_two_presented_families_atomically_on_commit_failure(
    db_session, test_user, monkeypatch
) -> None:
    refresh_family = issue_auth_session(db_session, test_user)
    access_family = issue_auth_session(db_session, test_user)
    rollback = MagicMock(wraps=db_session.rollback)

    with monkeypatch.context() as transaction_patch:
        transaction_patch.setattr(db_session, "rollback", rollback)
        transaction_patch.setattr(
            db_session,
            "commit",
            MagicMock(side_effect=RuntimeError("disk full")),
        )
        with pytest.raises(RuntimeError, match="disk full"):
            revoke_presented_sessions(
                db_session,
                refresh_token=refresh_family.refresh_token,
                access_token=access_family.access_token,
            )

    assert rollback.called
    db_session.expire_all()
    families = (
        db_session.query(AuthSession)
        .filter(AuthSession.id.in_([refresh_family.session_id, access_family.session_id]))
        .all()
    )
    assert len(families) == 2
    assert all(family.revoked_at is None for family in families)


def test_logout_commit_failure_clears_cookie_and_keeps_bearer_retry_authority(
    client, db_session, test_user, monkeypatch
) -> None:
    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
    )
    assert login.status_code == 200, login.text
    access_token = login.json()["access_token"]
    refresh_token = _cookie_value(client, REFRESH_COOKIE_NAME)
    access_claims = decode_access_token(access_token)
    assert access_claims is not None

    missing_override = object()
    original_override = app.dependency_overrides.get(get_db, missing_override)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app, raise_server_exceptions=False) as failure_client:
            _set_refresh_cookie(failure_client, refresh_token)
            with monkeypatch.context() as transaction_patch:
                transaction_patch.setattr(
                    db_session,
                    "commit",
                    MagicMock(side_effect=RuntimeError("disk full")),
                )
                failed = failure_client.post(
                    "/api/v1/auth/logout",
                    headers=_access_headers(access_token),
                )

            assert failed.status_code == 503
            assert failed.json() == {
                "detail": "Logout could not revoke the local session. Retry logout."
            }
            assert all(cookie.name != REFRESH_COOKIE_NAME for cookie in failure_client.cookies.jar)
            db_session.expire_all()
            family = db_session.get(AuthSession, access_claims["sid"])
            assert family is not None
            assert family.revoked_at is None
            refresh_after_reload = failure_client.post("/api/v1/auth/refresh")
            assert refresh_after_reload.status_code == 401
            assert refresh_after_reload.json() == {"detail": "Refresh token missing"}

            retried = failure_client.post(
                "/api/v1/auth/logout",
                headers=_access_headers(access_token),
            )
            assert retried.status_code == 200, retried.text
            assert all(cookie.name != REFRESH_COOKIE_NAME for cookie in failure_client.cookies.jar)
            db_session.expire_all()
            assert db_session.get(AuthSession, access_claims["sid"]).revoked_at is not None
    finally:
        if original_override is missing_override:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = original_override
