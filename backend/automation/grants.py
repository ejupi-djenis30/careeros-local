"""Issuance, verification and revocation for automation grants."""

from __future__ import annotations

import hashlib
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import case, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from backend.automation.models import AutomationGrant
from backend.automation.schemas import (
    ALL_AUTOMATION_SCOPES,
    AutomationScope,
    GrantView,
    normalize_grant_label,
)
from backend.models import User
from backend.models.user import VAULT_STATE_READY

TOKEN_ENVIRONMENT_VARIABLE = "CAREEROS_MCP_TOKEN"
TOKEN_PREFIX = "_".join(("careeros", "mcp", "v1", ""))
MAX_ACTIVE_GRANTS_PER_USER = 32
RECENT_GRANT_HISTORY_LIMIT = 100
_GRANT_MUTATION_LOCK = threading.Lock()
_PRUNE_BATCH_SIZE = 500


class AutomationGrantError(RuntimeError):
    """A stable, content-free automation authorization failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class AutomationPrincipal:
    grant_id: str
    user_id: int
    scopes: frozenset[AutomationScope]

    def allows(self, scope: AutomationScope) -> bool:
        return scope in self.scopes


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_scopes(values: list[str] | tuple[str, ...]) -> tuple[AutomationScope, ...]:
    requested = set(values)
    allowed = set(ALL_AUTOMATION_SCOPES)
    if not requested or not requested.issubset(allowed):
        raise AutomationGrantError("invalid_scopes", "Choose one or more supported scopes")
    return tuple(scope for scope in ALL_AUTOMATION_SCOPES if scope in requested)


def _inactive_filter(
    *,
    user_id: int,
    now: datetime,
) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    return (
        AutomationGrant.user_id == user_id,
        or_(
            AutomationGrant.revoked_at.is_not(None),
            AutomationGrant.expires_at <= now,
        ),
    )


def _inactivity_at() -> ColumnElement[Any]:
    """Order history by the transition that removed authority, not issuance."""
    return case(
        (
            AutomationGrant.revoked_at.is_not(None),
            AutomationGrant.revoked_at,
        ),
        else_=AutomationGrant.expires_at,
    )


def _prune_inactive_history(
    db: Session,
    *,
    user_id: int,
    now: datetime,
) -> int:
    """Retain a bounded, owner-scoped inactive audit tail after mutations.

    Active rows are never selected. Batching avoids an unbounded Python list and
    SQLite parameter list when cleaning a vault created by an older build.
    """
    removed = 0
    while True:
        stale_ids = [
            grant_id
            for (grant_id,) in (
                db.query(AutomationGrant.id)
                .filter(*_inactive_filter(user_id=user_id, now=now))
                .order_by(
                    _inactivity_at().desc(),
                    AutomationGrant.id.asc(),
                )
                .offset(RECENT_GRANT_HISTORY_LIMIT)
                .limit(_PRUNE_BATCH_SIZE)
                .all()
            )
        ]
        if not stale_ids:
            return removed
        removed += (
            db.query(AutomationGrant)
            .filter(
                AutomationGrant.user_id == user_id,
                AutomationGrant.id.in_(stale_ids),
            )
            .delete(synchronize_session=False)
        )
        db.flush()


def issue_grant(
    db: Session,
    *,
    user_id: int,
    label: str,
    scopes: list[str] | tuple[str, ...],
    lifetime: timedelta = timedelta(days=30),
) -> tuple[GrantView, str]:
    try:
        normalized_label = normalize_grant_label(label)
    except ValueError as exc:
        raise AutomationGrantError(
            "invalid_label",
            "Grant labels must contain 1 to 120 printable characters",
        ) from exc
    if lifetime < timedelta(minutes=5) or lifetime > timedelta(days=365):
        raise AutomationGrantError(
            "invalid_lifetime", "Grant lifetime must be 5 minutes to 365 days"
        )
    normalized_scopes = normalize_scopes(scopes)
    now = datetime.now(UTC)
    with _GRANT_MUTATION_LOCK:
        lifecycle_state = db.query(User.vault_lifecycle_state).filter(User.id == user_id).scalar()
        if lifecycle_state != VAULT_STATE_READY:
            raise AutomationGrantError(
                "vault_maintenance_pending",
                "Complete pending local-data maintenance before issuing a grant",
            )
        active_count = (
            db.query(AutomationGrant)
            .filter(
                AutomationGrant.user_id == user_id,
                AutomationGrant.revoked_at.is_(None),
                AutomationGrant.expires_at > now,
            )
            .count()
        )
        if active_count >= MAX_ACTIVE_GRANTS_PER_USER:
            raise AutomationGrantError(
                "active_grant_limit",
                (
                    f"An account may have at most {MAX_ACTIVE_GRANTS_PER_USER} active grants; "
                    "revoke one before creating another"
                ),
            )
        token = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
        grant = AutomationGrant(
            user_id=user_id,
            label=normalized_label,
            token_digest=_digest(token),
            scopes=list(normalized_scopes),
            expires_at=now + lifetime,
            revoked_at=None,
        )
        db.add(grant)
        db.flush()
        _prune_inactive_history(db, user_id=user_id, now=now)
        db.commit()
        db.refresh(grant)
    return grant_view(grant), token


def authenticate_grant(db: Session, token: str) -> AutomationPrincipal:
    candidate = token.strip()
    if not candidate.startswith(TOKEN_PREFIX) or not 50 <= len(candidate) <= 96:
        raise AutomationGrantError("invalid_grant", "The automation grant is invalid")
    digest = _digest(candidate)
    grant = db.query(AutomationGrant).filter(AutomationGrant.token_digest == digest).first()
    if grant is None or not secrets.compare_digest(grant.token_digest, digest):
        raise AutomationGrantError("invalid_grant", "The automation grant is invalid")
    now = datetime.now(UTC)
    if grant.revoked_at is not None:
        raise AutomationGrantError("revoked_grant", "The automation grant has been revoked")
    if grant.expires_at <= now:
        raise AutomationGrantError("expired_grant", "The automation grant has expired")
    lifecycle_state = db.query(User.vault_lifecycle_state).filter(User.id == grant.user_id).scalar()
    if lifecycle_state != VAULT_STATE_READY:
        raise AutomationGrantError(
            "vault_maintenance_pending",
            "Career Vault maintenance is pending",
        )
    try:
        scopes = frozenset(normalize_scopes(tuple(grant.scope_set())))
    except AutomationGrantError as exc:
        raise AutomationGrantError("invalid_grant", "The automation grant is invalid") from exc
    return AutomationPrincipal(
        grant_id=grant.id,
        user_id=grant.user_id,
        scopes=cast(frozenset[AutomationScope], scopes),
    )


def list_grants(db: Session, *, user_id: int) -> list[GrantView]:
    now = datetime.now(UTC)
    active_rows = (
        db.query(AutomationGrant)
        .filter(
            AutomationGrant.user_id == user_id,
            AutomationGrant.revoked_at.is_(None),
            AutomationGrant.expires_at > now,
        )
        .order_by(AutomationGrant.created_at.desc(), AutomationGrant.id.asc())
        .all()
    )
    history_rows = (
        db.query(AutomationGrant)
        .filter(*_inactive_filter(user_id=user_id, now=now))
        .order_by(_inactivity_at().desc(), AutomationGrant.id.asc())
        .limit(RECENT_GRANT_HISTORY_LIMIT)
        .all()
    )
    rows = (*active_rows, *history_rows)
    return [grant_view(item) for item in rows]


def revoke_grant(db: Session, *, user_id: int, grant_id: str) -> GrantView:
    with _GRANT_MUTATION_LOCK:
        grant = (
            db.query(AutomationGrant)
            .filter(AutomationGrant.id == grant_id, AutomationGrant.user_id == user_id)
            .first()
        )
        if grant is None:
            raise AutomationGrantError("grant_not_found", "Automation grant not found")
        if grant.revoked_at is not None:
            return grant_view(grant)
        now = datetime.now(UTC)
        grant.revoked_at = now
        db.flush()
        _prune_inactive_history(db, user_id=user_id, now=now)
        db.commit()
        db.refresh(grant)
    return grant_view(grant)


def grant_view(grant: AutomationGrant) -> GrantView:
    return GrantView(
        id=grant.id,
        label=grant.label,
        scopes=list(normalize_scopes(tuple(grant.scope_set()))),
        expires_at=grant.expires_at,
        revoked_at=grant.revoked_at,
        created_at=grant.created_at,
    )
