from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.automation.grants import (
    TOKEN_PREFIX,
    AutomationGrantError,
    authenticate_grant,
    issue_grant,
    revoke_grant,
)
from backend.automation.models import AutomationGrant
from backend.models import User


def test_grant_persists_only_digest_and_binds_principal(db_session, test_user) -> None:
    view, token = issue_grant(
        db_session,
        user_id=test_user.id,
        label="Codex workstation",
        scopes=("system:read", "applications:read"),
    )

    row = db_session.get(AutomationGrant, view.id)
    assert row is not None
    assert token.startswith(TOKEN_PREFIX)
    assert token not in row.token_digest
    assert len(row.token_digest) == 64
    assert "token" not in view.model_dump()
    assert "user_id" not in view.model_dump()

    principal = authenticate_grant(db_session, token)
    assert principal.user_id == test_user.id
    assert principal.grant_id == view.id
    assert principal.scopes == {"system:read", "applications:read"}


@pytest.mark.parametrize(
    ("token", "code"),
    [
        ("", "invalid_grant"),
        (TOKEN_PREFIX + "too-short", "invalid_grant"),
        (TOKEN_PREFIX + "z" * 43, "invalid_grant"),
    ],
)
def test_invalid_grants_fail_with_stable_errors(db_session, token: str, code: str) -> None:
    with pytest.raises(AutomationGrantError) as raised:
        authenticate_grant(db_session, token)
    assert raised.value.code == code


def test_revoked_and_expired_grants_fail_closed(db_session, test_user) -> None:
    view, revoked_token = issue_grant(
        db_session,
        user_id=test_user.id,
        label="Revoked client",
        scopes=("system:read",),
    )
    revoke_grant(db_session, user_id=test_user.id, grant_id=view.id)
    with pytest.raises(AutomationGrantError) as revoked:
        authenticate_grant(db_session, revoked_token)
    assert revoked.value.code == "revoked_grant"

    expired_view, expired_token = issue_grant(
        db_session,
        user_id=test_user.id,
        label="Expired client",
        scopes=("system:read",),
        lifetime=timedelta(minutes=5),
    )
    expired = db_session.get(AutomationGrant, expired_view.id)
    assert expired is not None
    expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    with pytest.raises(AutomationGrantError) as expired_error:
        authenticate_grant(db_session, expired_token)
    assert expired_error.value.code == "expired_grant"


def test_one_user_cannot_revoke_another_users_grant(db_session, test_user) -> None:
    other = User(username="other-automation-user", hashed_password="not-used")
    db_session.add(other)
    db_session.commit()
    grant, _token = issue_grant(
        db_session,
        user_id=test_user.id,
        label="Owned grant",
        scopes=("system:read",),
    )

    with pytest.raises(AutomationGrantError) as raised:
        revoke_grant(db_session, user_id=other.id, grant_id=grant.id)
    assert raised.value.code == "grant_not_found"
