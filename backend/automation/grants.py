"""Issuance, verification and revocation for automation grants."""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy.orm import Session

from backend.automation.models import AutomationGrant
from backend.automation.schemas import ALL_AUTOMATION_SCOPES, AutomationScope, GrantView

TOKEN_ENVIRONMENT_VARIABLE = "CAREEROS_MCP_TOKEN"
TOKEN_PREFIX = "_".join(("careeros", "mcp", "v1", ""))
_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,119}$")


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
        raise AutomationGrantError("invalid_scopes", "Choose one or more supported read scopes")
    return tuple(scope for scope in ALL_AUTOMATION_SCOPES if scope in requested)


def issue_grant(
    db: Session,
    *,
    user_id: int,
    label: str,
    scopes: list[str] | tuple[str, ...],
    lifetime: timedelta = timedelta(days=30),
) -> tuple[GrantView, str]:
    normalized_label = label.strip()
    if not _LABEL_PATTERN.fullmatch(normalized_label):
        raise AutomationGrantError(
            "invalid_label",
            "Grant labels may use letters, numbers, spaces, dots, dashes and underscores",
        )
    if lifetime < timedelta(minutes=5) or lifetime > timedelta(days=365):
        raise AutomationGrantError(
            "invalid_lifetime", "Grant lifetime must be 5 minutes to 365 days"
        )
    normalized_scopes = normalize_scopes(scopes)
    token = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    now = datetime.now(UTC)
    grant = AutomationGrant(
        user_id=user_id,
        label=normalized_label,
        token_digest=_digest(token),
        scopes=list(normalized_scopes),
        expires_at=now + lifetime,
        revoked_at=None,
    )
    db.add(grant)
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
    rows = (
        db.query(AutomationGrant)
        .filter(AutomationGrant.user_id == user_id)
        .order_by(AutomationGrant.created_at.desc(), AutomationGrant.id.asc())
        .limit(100)
        .all()
    )
    return [grant_view(item) for item in rows]


def revoke_grant(db: Session, *, user_id: int, grant_id: str) -> GrantView:
    grant = (
        db.query(AutomationGrant)
        .filter(AutomationGrant.id == grant_id, AutomationGrant.user_id == user_id)
        .first()
    )
    if grant is None:
        raise AutomationGrantError("grant_not_found", "Automation grant not found")
    if grant.revoked_at is None:
        grant.revoked_at = datetime.now(UTC)
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
