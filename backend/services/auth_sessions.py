"""Stateful browser authority with replay-detecting refresh rotation."""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import delete, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.auth_session import AuthSession
from backend.models.user import (
    VAULT_STATE_ERASURE_PENDING,
    VAULT_STATE_READY,
    VAULT_STATE_RESET_PENDING,
    VAULT_STATE_RESTORE_PENDING,
    User,
)
from backend.services.auth import (
    ACCESS_PURPOSE_VAULT_MAINTENANCE,
    create_access_token,
    create_refresh_token,
    create_session_identifier,
    decode_access_token,
    decode_refresh_token,
)

# CareerOS is local-first, but container deployments may have more than one browser.
# Keep a small multi-session allowance while bounding persisted auth metadata per user.
MAX_ACTIVE_REFRESH_SESSIONS = 8
_ISSUE_ATTEMPTS = 3
_ERASURE_PENDING_DOMAIN = b"careeros-erasure-pending-v1:"
_MAINTENANCE_ISSUE_LOCK = threading.Lock()


class VaultMaintenancePendingError(RuntimeError):
    """Raised when normal session issuance is blocked by unfinished maintenance."""


@dataclass(frozen=True)
class AuthSessionTokens:
    """Access and refresh credentials bound to one persisted session family."""

    username: str
    session_id: str
    access_token: str
    refresh_token: str


@dataclass(frozen=True)
class MaintenanceAccessToken:
    """Password-reacquirable bearer restricted to a pending maintenance route."""

    username: str
    session_id: str
    access_token: str
    lifecycle_state: str


def _jti_digest(jti: str) -> str:
    return hashlib.sha256(jti.encode("ascii")).hexdigest()


def erasure_pending_digest(session_id: str) -> str:
    """Return a unique non-secret marker for one single-purpose retry family."""

    return hashlib.sha256(_ERASURE_PENDING_DOMAIN + session_id.encode("ascii")).hexdigest()


def is_erasure_pending_session(session: AuthSession) -> bool:
    return session.revoked_at is not None and session.refresh_jti_digest == erasure_pending_digest(
        session.id
    )


def get_erasure_pending_session(db: Session, user_id: int) -> AuthSession | None:
    for session in db.query(AuthSession).filter(AuthSession.user_id == user_id).all():
        if is_erasure_pending_session(session):
            return session
    return None


def _token_state(token: str) -> tuple[dict, str, str, datetime] | None:
    payload = decode_refresh_token(token)
    if payload is None:
        return None
    session_id = payload["sid"]
    jti = payload["jti"]
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    return payload, session_id, _jti_digest(jti), expires_at


def _available_session_slot(db: Session, user_id: int, now: datetime) -> int:
    db.query(AuthSession).filter(
        AuthSession.user_id == user_id,
        (AuthSession.revoked_at.is_not(None)) | (AuthSession.expires_at <= now),
    ).delete(synchronize_session=False)

    active = [
        (session_id, slot)
        for session_id, slot in db.query(AuthSession.id, AuthSession.slot)
        .filter(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
        .order_by(AuthSession.created_at.asc(), AuthSession.id.asc())
        .all()
    ]
    occupied = {slot for _session_id, slot in active}
    for slot in range(MAX_ACTIVE_REFRESH_SESSIONS):
        if slot not in occupied:
            return slot

    oldest_id, oldest_slot = active[0]
    db.query(AuthSession).filter(AuthSession.id == oldest_id).delete(synchronize_session=False)
    return int(oldest_slot)


def _lock_user_for_session_issue(db: Session, user_id: int) -> User | None:
    """Serialize normal issuance with lifecycle transitions on the owner row."""

    if db.get_bind().dialect.name == "sqlite":
        # Login has already performed a read transaction. End that snapshot and
        # acquire SQLite's write reservation before re-reading lifecycle state;
        # reset can then either revoke this family or win first and block issuance.
        db.commit()
        db.execute(text("BEGIN IMMEDIATE"))
    return (
        db.query(User)
        .filter(User.id == user_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )


def issue_auth_session(db: Session, user: User) -> AuthSessionTokens:
    """Issue one bounded family and both credentials without persisting either bearer."""

    for _attempt in range(_ISSUE_ATTEMPTS):
        try:
            locked_user = _lock_user_for_session_issue(db, user.id)
            if locked_user is None or locked_user.vault_lifecycle_state != VAULT_STATE_READY:
                raise VaultMaintenancePendingError(
                    "Complete pending local-data maintenance before signing in"
                )
            now = datetime.now(timezone.utc)
            slot = _available_session_slot(db, locked_user.id, now)
            session_id = create_session_identifier()
            access_token = create_access_token(
                {"sub": locked_user.username},
                session_id=session_id,
            )
            refresh_token = create_refresh_token(
                {"sub": locked_user.username},
                session_id=session_id,
            )
            state = _token_state(refresh_token)
            if state is None:  # pragma: no cover - token creator/decoder share one contract
                raise RuntimeError("Generated refresh token failed validation")
            _payload, decoded_session_id, digest, expires_at = state
            if decoded_session_id != session_id:  # pragma: no cover - same creator
                raise RuntimeError("Generated auth session identifier changed unexpectedly")
            db.add(
                AuthSession(
                    id=session_id,
                    user_id=locked_user.id,
                    slot=slot,
                    refresh_jti_digest=digest,
                    expires_at=expires_at,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()
        except IntegrityError:
            # Concurrent login can select the same free slot. The database cap
            # wins; retry from fresh state without ever exceeding eight rows.
            db.rollback()
            continue
        except Exception:
            db.rollback()
            raise
        return AuthSessionTokens(
            username=locked_user.username,
            session_id=session_id,
            access_token=access_token,
            refresh_token=refresh_token,
        )
    raise RuntimeError("Could not allocate a bounded refresh session")


def issue_maintenance_access(db: Session, user: User) -> MaintenanceAccessToken:
    """Issue no-refresh recovery authority after the account password is verified."""

    with _MAINTENANCE_ISSUE_LOCK:
        return _issue_maintenance_access_locked(db, user)


def _issue_maintenance_access_locked(
    db: Session,
    user: User,
) -> MaintenanceAccessToken:
    """Serialize slot replacement for the supported single-worker topology."""

    lifecycle_state = getattr(user, "vault_lifecycle_state", VAULT_STATE_READY)
    if lifecycle_state not in {
        VAULT_STATE_RESET_PENDING,
        VAULT_STATE_RESTORE_PENDING,
        VAULT_STATE_ERASURE_PENDING,
    }:
        raise VaultMaintenancePendingError("The vault has no pending maintenance")

    now = datetime.now(timezone.utc)
    sessions = db.query(AuthSession).filter(AuthSession.user_id == user.id).all()
    if lifecycle_state == VAULT_STATE_ERASURE_PENDING:
        session = next(
            (candidate for candidate in sessions if is_erasure_pending_session(candidate)),
            None,
        )
    else:
        session = next(
            (
                candidate
                for candidate in sessions
                if candidate.revoked_at is None and candidate.expires_at > now
            ),
            None,
        )

    try:
        needs_commit = False
        if session is None:
            db.query(AuthSession).filter(AuthSession.user_id == user.id).delete(
                synchronize_session=False
            )
            session_id = create_session_identifier()
            disposable_refresh = create_refresh_token(
                {"sub": user.username},
                session_id=session_id,
            )
            state = _token_state(disposable_refresh)
            if state is None:  # pragma: no cover - shared creator/decoder contract
                raise RuntimeError("Generated maintenance session failed validation")
            _payload, _sid, digest, expires_at = state
            session = AuthSession(
                id=session_id,
                user_id=user.id,
                slot=0,
                refresh_jti_digest=(
                    erasure_pending_digest(session_id)
                    if lifecycle_state == VAULT_STATE_ERASURE_PENDING
                    else digest
                ),
                expires_at=expires_at,
                revoked_at=(now if lifecycle_state == VAULT_STATE_ERASURE_PENDING else None),
                created_at=now,
                updated_at=now,
            )
            db.add(session)
            needs_commit = True
        elif session.expires_at <= now:
            # Correct password can renew only the maintenance-family envelope;
            # no refresh bearer is exposed or made usable.
            disposable_refresh = create_refresh_token(
                {"sub": user.username},
                session_id=session.id,
            )
            state = _token_state(disposable_refresh)
            if state is None:  # pragma: no cover - shared creator/decoder contract
                raise RuntimeError("Generated maintenance session failed validation")
            session.expires_at = state[3]
            session.updated_at = now
            needs_commit = True
        access_token = create_access_token(
            {"sub": user.username},
            session_id=session.id,
            purpose=ACCESS_PURPOSE_VAULT_MAINTENANCE,
        )
        if needs_commit:
            db.commit()
    except Exception:
        db.rollback()
        raise

    return MaintenanceAccessToken(
        username=user.username,
        session_id=session.id,
        access_token=access_token,
        lifecycle_state=lifecycle_state,
    )


def issue_refresh_session(db: Session, user: User) -> str:
    """Compatibility helper for tests and internal flows that need only a refresh bearer."""

    return issue_auth_session(db, user).refresh_token


def rotate_refresh_session(db: Session, token: str) -> AuthSessionTokens | None:
    """Consume one refresh token and rotate its family atomically.

    A valid old token for an existing family is a replay signal. In that case the
    whole family is revoked so neither side of a theft race keeps access.
    """

    state = _token_state(token)
    if state is None:
        return None
    payload, session_id, current_digest, _current_expiry = state
    username = payload["sub"]

    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            db.rollback()
            return None
        if user.vault_lifecycle_state != VAULT_STATE_READY:
            db.rollback()
            return None
        user_id = user.id
        now = datetime.now(timezone.utc)
        new_token = create_refresh_token({"sub": username}, session_id=session_id)
        new_access_token = create_access_token({"sub": username}, session_id=session_id)
        new_state = _token_state(new_token)
        if new_state is None:  # pragma: no cover - token creator/decoder share one contract
            raise RuntimeError("Generated refresh token failed validation")
        _new_payload, _new_session_id, new_digest, new_expiry = new_state
        result = cast(
            CursorResult[Any],
            db.execute(
                update(AuthSession)
                .where(
                    AuthSession.id == session_id,
                    AuthSession.user_id == user_id,
                    AuthSession.refresh_jti_digest == current_digest,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                )
                .values(
                    refresh_jti_digest=new_digest,
                    expires_at=new_expiry,
                    updated_at=now,
                )
            ),
        )
        if result.rowcount == 1:
            db.commit()
            return AuthSessionTokens(
                username=username,
                session_id=session_id,
                access_token=new_access_token,
                refresh_token=new_token,
            )
    except Exception:
        db.rollback()
        raise

    # End the transaction before inspecting the winning state. If another refresh
    # rotated first, its digest is now visible and this old token revokes the family.
    db.rollback()
    existing = db.get(AuthSession, session_id)
    if (
        existing is not None
        and existing.user_id == user_id
        and existing.revoked_at is None
        and existing.expires_at > now
        and existing.refresh_jti_digest != current_digest
    ):
        try:
            db.execute(
                update(AuthSession)
                .where(
                    AuthSession.id == session_id,
                    AuthSession.user_id == user_id,
                    AuthSession.revoked_at.is_(None),
                )
                .values(revoked_at=now, updated_at=now)
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
    else:
        db.rollback()
    return None


def revoke_refresh_session(db: Session, token: str) -> bool:
    """Revoke the token's whole family; invalid tokens remain a no-op."""

    return revoke_presented_sessions(db, refresh_token=token) > 0


def revoke_access_session(db: Session, token: str) -> bool:
    """Revoke the family named by a valid access bearer, including without a cookie."""

    return revoke_presented_sessions(db, access_token=token) > 0


def revoke_presented_sessions(
    db: Session,
    *,
    refresh_token: str | None = None,
    access_token: str | None = None,
) -> int:
    """Atomically revoke every valid family binding supplied by a logout request."""

    bindings: set[tuple[str, str]] = set()
    if refresh_token:
        refresh_state = _token_state(refresh_token)
        if refresh_state is not None:
            payload, session_id, _digest, _expires_at = refresh_state
            bindings.add((payload["sub"], session_id))
    if access_token:
        access_payload = decode_access_token(access_token)
        if access_payload is not None:
            bindings.add((access_payload["sub"], access_payload["sid"]))

    if not bindings:
        return 0

    now = datetime.now(timezone.utc)
    revoked = 0
    try:
        for username, session_id in bindings:
            user_id = db.query(User.id).filter(User.username == username).scalar()
            if user_id is None:
                continue
            existing = db.get(AuthSession, session_id)
            if (
                existing is not None
                and existing.user_id == int(user_id)
                and is_erasure_pending_session(existing)
            ):
                result = cast(
                    CursorResult[Any],
                    db.execute(
                        delete(AuthSession).where(
                            AuthSession.id == session_id,
                            AuthSession.user_id == int(user_id),
                            AuthSession.refresh_jti_digest == erasure_pending_digest(session_id),
                        )
                    ),
                )
                revoked += result.rowcount
                continue
            result = cast(
                CursorResult[Any],
                db.execute(
                    update(AuthSession)
                    .where(
                        AuthSession.id == session_id,
                        AuthSession.user_id == int(user_id),
                        AuthSession.revoked_at.is_(None),
                    )
                    .values(revoked_at=now, updated_at=now)
                ),
            )
            revoked += result.rowcount
        db.commit()
    except Exception:
        db.rollback()
        raise
    return revoked
