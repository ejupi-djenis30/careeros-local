from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from backend.automation.grants import (
    MAX_ACTIVE_GRANTS_PER_USER,
    RECENT_GRANT_HISTORY_LIMIT,
    TOKEN_PREFIX,
    AutomationGrantError,
    authenticate_grant,
    issue_grant,
    revoke_grant,
)
from backend.automation.models import AutomationGrant
from backend.db.base import SessionLocal
from backend.models import User
from backend.models.user import (
    VAULT_STATE_ERASURE_PENDING,
    VAULT_STATE_RESET_PENDING,
    VAULT_STATE_RESTORE_PENDING,
)


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
    "pending_state",
    [
        VAULT_STATE_RESET_PENDING,
        VAULT_STATE_RESTORE_PENDING,
        VAULT_STATE_ERASURE_PENDING,
    ],
)
def test_pending_vault_blocks_grant_reads_and_new_issuance(
    db_session,
    test_user,
    pending_state,
) -> None:
    _view, token = issue_grant(
        db_session,
        user_id=test_user.id,
        label="Existing reader",
        scopes=("system:read",),
    )
    test_user.vault_lifecycle_state = pending_state
    test_user.vault_maintenance_fingerprint = (
        "a" * 64 if pending_state == VAULT_STATE_RESTORE_PENDING else None
    )
    db_session.commit()

    with pytest.raises(AutomationGrantError) as authentication_error:
        authenticate_grant(db_session, token)
    assert authentication_error.value.code == "vault_maintenance_pending"

    with pytest.raises(AutomationGrantError) as issuance_error:
        issue_grant(
            db_session,
            user_id=test_user.id,
            label="Blocked reader",
            scopes=("system:read",),
        )
    assert issuance_error.value.code == "vault_maintenance_pending"


def test_grant_labels_support_natural_unicode_names(db_session, test_user) -> None:
    view, _token = issue_grant(
        db_session,
        user_id=test_user.id,
        label="  Claude Code – Zürich · Djenis’s Mac  ",
        scopes=("system:read",),
    )

    assert view.label == "Claude Code – Zürich · Djenis’s Mac"


@pytest.mark.parametrize(
    "label",
    [
        "",
        "   ",
        "hidden\u200bseparator",
        "line\nbreak",
        "line\u2028separator",
        "paragraph\u2029separator",
        "x" * 121,
    ],
)
def test_grant_labels_reject_empty_control_or_oversized_values(
    db_session,
    test_user,
    label,
) -> None:
    with pytest.raises(AutomationGrantError, match="printable characters") as raised:
        issue_grant(
            db_session,
            user_id=test_user.id,
            label=label,
            scopes=("system:read",),
        )
    assert raised.value.code == "invalid_label"


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


def test_successful_issue_prunes_only_the_owners_inactive_history(
    db_session,
    test_user,
) -> None:
    now = datetime.now(UTC)
    other = User(username="inactive-history-neighbor", hashed_password="not-used")
    db_session.add(other)
    db_session.flush()
    db_session.add_all(
        [
            AutomationGrant(
                user_id=test_user.id,
                label=f"Expired {index}",
                token_digest=f"{index + 1:064x}",
                scopes=["system:read"],
                expires_at=now - timedelta(minutes=index + 1),
                created_at=now - timedelta(days=2, minutes=index),
                updated_at=now - timedelta(days=2, minutes=index),
            )
            for index in range(RECENT_GRANT_HISTORY_LIMIT + 7)
        ]
    )
    foreign = AutomationGrant(
        user_id=other.id,
        label="Foreign expired history",
        token_digest="e" * 64,
        scopes=["system:read"],
        expires_at=now - timedelta(days=400),
    )
    db_session.add(foreign)
    db_session.commit()

    issued, _token = issue_grant(
        db_session,
        user_id=test_user.id,
        label="New active grant",
        scopes=("system:read",),
    )

    db_session.expire_all()
    owned = db_session.query(AutomationGrant).filter(AutomationGrant.user_id == test_user.id).all()
    assert len(owned) == RECENT_GRANT_HISTORY_LIMIT + 1
    assert {row.id for row in owned if row.expires_at > now and row.revoked_at is None} == {
        issued.id
    }
    assert db_session.get(AutomationGrant, foreign.id) is not None


def test_parallel_issuance_cannot_exceed_the_active_grant_cap(
    db_session,
    test_user,
) -> None:
    workers = MAX_ACTIVE_GRANTS_PER_USER + 8
    start = threading.Barrier(workers)

    def issue_once(index: int) -> str:
        start.wait(timeout=5)
        with SessionLocal() as session:
            try:
                issue_grant(
                    session,
                    user_id=test_user.id,
                    label=f"Parallel agent {index}",
                    scopes=("system:read",),
                )
            except AutomationGrantError as exc:
                return exc.code
        return "issued"

    with ThreadPoolExecutor(max_workers=workers) as executor:
        outcomes = list(executor.map(issue_once, range(workers)))

    assert outcomes.count("issued") == MAX_ACTIVE_GRANTS_PER_USER
    assert outcomes.count("active_grant_limit") == workers - MAX_ACTIVE_GRANTS_PER_USER
    db_session.expire_all()
    assert (
        db_session.query(AutomationGrant)
        .filter(
            AutomationGrant.user_id == test_user.id,
            AutomationGrant.revoked_at.is_(None),
            AutomationGrant.expires_at > datetime.now(UTC),
        )
        .count()
        == MAX_ACTIVE_GRANTS_PER_USER
    )


def test_parallel_revocation_is_idempotent(
    db_session,
    test_user,
) -> None:
    issued, token = issue_grant(
        db_session,
        user_id=test_user.id,
        label="Parallel revoke",
        scopes=("system:read",),
    )
    workers = 12
    start = threading.Barrier(workers)

    def revoke_once(_index: int) -> str:
        start.wait(timeout=5)
        with SessionLocal() as session:
            result = revoke_grant(
                session,
                user_id=test_user.id,
                grant_id=issued.id,
            )
            assert result.revoked_at is not None
            return result.revoked_at.isoformat()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        timestamps = list(executor.map(revoke_once, range(workers)))

    assert len(set(timestamps)) == 1
    with pytest.raises(AutomationGrantError) as rejected:
        authenticate_grant(db_session, token)
    assert rejected.value.code == "revoked_grant"
