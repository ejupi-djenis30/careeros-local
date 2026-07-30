from __future__ import annotations

import hashlib
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api.routes import automation as automation_routes
from backend.api.routes.automation import reauthentication_guard
from backend.automation.grants import (
    MAX_ACTIVE_GRANTS_PER_USER,
    RECENT_GRANT_HISTORY_LIMIT,
    TOKEN_PREFIX,
    authenticate_grant,
)
from backend.automation.models import AutomationGrant
from backend.models import User
from backend.services.auth import get_password_hash

ENDPOINT = "/api/v1/automation/grants"


@pytest.fixture(autouse=True)
def reset_reauthentication_guard():
    reauthentication_guard.reset()
    yield
    reauthentication_guard.reset()


def _payload(**overrides):
    payload = {
        "label": "Codex workstation",
        "scopes": ["system:read", "applications:read"],
        "lifetime_days": 30,
        "password": "Globalpass1",
    }
    payload.update(overrides)
    return payload


def test_agent_access_requires_an_authenticated_account(client) -> None:
    response = client.get(ENDPOINT)

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"


def test_create_returns_one_time_token_and_metadata_only_listing(
    client,
    auth_headers,
    db_session,
    test_user,
) -> None:
    created = client.post(ENDPOINT, headers=auth_headers, json=_payload())

    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store, max-age=0"
    assert created.headers["pragma"] == "no-cache"
    body = created.json()
    token = body["token"]
    assert token.startswith(TOKEN_PREFIX)
    assert body["token_environment_variable"] == "CAREEROS_MCP_TOKEN"
    assert body["grant"]["scopes"] == ["system:read", "applications:read"]
    assert "shown once" in body["warning"]
    assert "Globalpass1" not in created.text

    db_session.expire_all()
    row = db_session.get(AutomationGrant, body["grant"]["id"])
    assert row is not None
    assert row.user_id == test_user.id
    assert row.token_digest == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert token not in row.token_digest

    listing = client.get(ENDPOINT, headers=auth_headers)
    assert listing.status_code == 200
    assert listing.headers["cache-control"] == "no-store, max-age=0"
    assert listing.json() == [body["grant"]]
    assert token not in listing.text
    assert "token" not in listing.json()[0]

    principal = authenticate_grant(db_session, token)
    assert principal.user_id == test_user.id


def test_create_accepts_a_natural_unicode_client_label(
    client,
    auth_headers,
) -> None:
    response = client.post(
        ENDPOINT,
        headers=auth_headers,
        json=_payload(label="Claude Code – Zürich · Djenis’s Mac"),
    )

    assert response.status_code == 201
    assert response.json()["grant"]["label"] == "Claude Code – Zürich · Djenis’s Mac"


def test_create_reauthenticates_without_persisting_a_failed_attempt(
    client,
    auth_headers,
    db_session,
) -> None:
    response = client.post(
        ENDPOINT,
        headers=auth_headers,
        json=_payload(password="incorrect-password"),
    )

    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.json()["detail"]["code"] == "authentication_failed"
    assert "incorrect-password" not in response.text
    assert db_session.query(AutomationGrant).count() == 0


def test_failed_reauthentication_locks_grant_creation_per_account(
    client,
    auth_headers,
) -> None:
    failures = [
        client.post(
            ENDPOINT,
            headers=auth_headers,
            json=_payload(password="incorrect-password"),
        )
        for _ in range(5)
    ]

    assert [response.status_code for response in failures] == [403, 403, 403, 403, 429]
    locked = failures[-1]
    assert locked.json()["detail"]["code"] == "reauthentication_locked"
    assert int(locked.headers["retry-after"]) > 0
    assert locked.headers["cache-control"] == "no-store, max-age=0"
    assert locked.headers["pragma"] == "no-cache"

    still_locked = client.post(ENDPOINT, headers=auth_headers, json=_payload())
    assert still_locked.status_code == 429
    assert still_locked.json()["detail"]["code"] == "reauthentication_locked"


def test_parallel_failed_reauthentication_is_serialized_and_stops_at_lockout(
    monkeypatch,
) -> None:
    start = threading.Barrier(6)
    counter_lock = threading.Lock()
    active_checks = 0
    maximum_active_checks = 0
    verification_calls = 0

    class StubUserRepository:
        def __init__(self, _db) -> None:
            pass

        def get(self, _user_id: int):
            return SimpleNamespace(hashed_password="test-hash")

    def verify(candidate: str, _hashed_password: str) -> bool:
        nonlocal active_checks, maximum_active_checks, verification_calls
        with counter_lock:
            active_checks += 1
            verification_calls += 1
            maximum_active_checks = max(maximum_active_checks, active_checks)
        time.sleep(0.01)
        with counter_lock:
            active_checks -= 1
        return candidate == "correct-password"

    monkeypatch.setattr(automation_routes, "UserRepository", StubUserRepository)
    monkeypatch.setattr(automation_routes, "verify_password", verify)

    def fail_once() -> int:
        start.wait(timeout=1)
        try:
            automation_routes._require_current_password(
                object(),
                user_id=77,
                password="incorrect-password",
            )
        except HTTPException as exc:
            return exc.status_code
        raise AssertionError("An incorrect password unexpectedly passed")

    with ThreadPoolExecutor(max_workers=6) as executor:
        statuses = list(executor.map(lambda _: fail_once(), range(6)))

    assert sorted(statuses) == [403, 403, 403, 403, 429, 429]
    assert verification_calls == 5
    assert maximum_active_checks == 1

    with pytest.raises(HTTPException) as locked:
        automation_routes._require_current_password(
            object(),
            user_id=77,
            password="correct-password",
        )
    assert locked.value.status_code == 429
    assert verification_calls == 5


def test_locked_account_uses_session_only_revocation_without_password_oracle(
    monkeypatch,
    client,
    auth_headers,
    db_session,
    test_user,
) -> None:
    other = User(
        username="other-emergency-revoke-user",
        hashed_password=get_password_hash("Otherpass1"),
    )
    db_session.add(other)
    db_session.flush()
    grants = [
        AutomationGrant(
            user_id=test_user.id,
            label=f"Emergency revocation {index}",
            token_digest=f"{index + 10:064x}",
            scopes=["system:read"],
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        for index in range(2)
    ]
    foreign = AutomationGrant(
        user_id=other.id,
        label="Foreign emergency revocation",
        token_digest="f" * 64,
        scopes=["system:read"],
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add_all([*grants, foreign])
    db_session.commit()

    original_verify_password = automation_routes.verify_password
    verification_calls = 0

    def counted_verify_password(password: str, hashed_password: str) -> bool:
        nonlocal verification_calls
        verification_calls += 1
        return original_verify_password(password, hashed_password)

    monkeypatch.setattr(
        automation_routes,
        "verify_password",
        counted_verify_password,
    )
    failures = [
        client.post(
            ENDPOINT,
            headers=auth_headers,
            json=_payload(password="incorrect-password"),
        )
        for _ in range(5)
    ]
    assert [response.status_code for response in failures] == [403, 403, 403, 403, 429]
    assert verification_calls == 5
    initial_retry_after = int(failures[-1].headers["retry-after"])

    revoked_with_wrong_password = client.post(
        f"{ENDPOINT}/{grants[0].id}/revoke",
        headers=auth_headers,
        json={"password": "still-incorrect"},
    )
    revoked_with_correct_password = client.post(
        f"{ENDPOINT}/{grants[1].id}/revoke",
        headers=auth_headers,
        json={"password": "Globalpass1"},
    )
    repeated = client.post(
        f"{ENDPOINT}/{grants[0].id}/revoke",
        headers=auth_headers,
        json={"password": "another-ignored-value"},
    )
    foreign_response = client.post(
        f"{ENDPOINT}/{foreign.id}/revoke",
        headers=auth_headers,
        json={"password": "Globalpass1"},
    )
    unknown_response = client.post(
        f"{ENDPOINT}/{uuid.uuid4()}/revoke",
        headers=auth_headers,
        json={"password": "still-incorrect"},
    )
    still_locked = client.post(
        ENDPOINT,
        headers=auth_headers,
        json=_payload(label="Post-revocation agent", password="Globalpass1"),
    )

    assert revoked_with_wrong_password.status_code == 200
    assert revoked_with_correct_password.status_code == 200
    assert repeated.status_code == 200
    assert revoked_with_wrong_password.json()["revoked_at"] is not None
    assert revoked_with_correct_password.json()["revoked_at"] is not None
    assert foreign_response.status_code == 404
    assert unknown_response.status_code == 404
    assert still_locked.status_code == 429
    assert int(still_locked.headers["retry-after"]) <= initial_retry_after
    assert verification_calls == 5


@pytest.mark.parametrize(
    "overrides",
    [
        {"label": "contains\nnewline"},
        {"label": "contains\u200bseparator"},
        {"label": "contains\u2028separator"},
        {"label": "contains\u2029separator"},
        {"scopes": []},
        {"scopes": ["system:read", "system:read"]},
        {"scopes": ["write:everything"]},
        {"lifetime_days": 0},
        {"lifetime_days": 366},
    ],
)
def test_create_rejects_unbounded_or_unsupported_requests(
    client,
    auth_headers,
    db_session,
    overrides,
) -> None:
    response = client.post(ENDPOINT, headers=auth_headers, json=_payload(**overrides))

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert "Globalpass1" not in response.text
    assert db_session.query(AutomationGrant).count() == 0


@pytest.mark.parametrize(
    "path",
    [
        ENDPOINT,
        f"{ENDPOINT}/00000000-0000-4000-8000-000000000000/revoke",
    ],
)
def test_malformed_password_never_appears_in_validation_errors(
    client,
    auth_headers,
    path,
) -> None:
    secret = "MalformedActualSecret123"
    payload = (
        _payload(password=[secret])
        if path == ENDPOINT
        else {"password": [secret]}
    )

    response = client.post(path, headers=auth_headers, json=payload)

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert secret not in response.text
    assert all("input" not in error for error in response.json()["detail"])
    assert all("ctx" not in error for error in response.json()["detail"])


def test_unexpected_field_name_never_appears_in_validation_errors(
    client,
    auth_headers,
) -> None:
    sensitive_field_name = "SecretUsedAsUnexpectedField123"
    payload = {
        **_payload(),
        sensitive_field_name: "request-controlled value",
    }

    response = client.post(ENDPOINT, headers=auth_headers, json=payload)

    assert response.status_code == 422
    assert sensitive_field_name not in response.text
    assert response.json()["detail"] == [
        {
            "type": "extra_forbidden",
            "loc": ["body", "field"],
            "msg": "Extra inputs are not permitted",
        }
    ]


def test_listing_and_revocation_are_user_scoped_and_revocation_is_idempotent(
    client,
    auth_headers,
    db_session,
) -> None:
    created = client.post(ENDPOINT, headers=auth_headers, json=_payload()).json()
    grant_id = created["grant"]["id"]
    token = created["token"]

    other = User(
        username="other-agent-user",
        hashed_password=get_password_hash("Otherpass1"),
    )
    db_session.add(other)
    db_session.commit()
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "other-agent-user", "password": "Otherpass1"},
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert client.get(ENDPOINT, headers=other_headers).json() == []
    foreign_revoke = client.post(
        f"{ENDPOINT}/{grant_id}/revoke",
        headers=other_headers,
        json={"password": "Otherpass1"},
    )
    assert foreign_revoke.status_code == 404
    assert foreign_revoke.json()["detail"]["code"] == "grant_not_found"

    wrong_password = client.post(
        f"{ENDPOINT}/{grant_id}/revoke",
        headers=auth_headers,
        json={"password": "incorrect-password"},
    )
    assert wrong_password.status_code == 403
    assert authenticate_grant(db_session, token).grant_id == grant_id

    first = client.post(
        f"{ENDPOINT}/{grant_id}/revoke",
        headers=auth_headers,
        json={"password": "Globalpass1"},
    )
    second = client.post(
        f"{ENDPOINT}/{grant_id}/revoke",
        headers=auth_headers,
        json={"password": "Globalpass1"},
    )
    assert first.status_code == second.status_code == 200
    assert first.headers["cache-control"] == "no-store, max-age=0"
    assert first.json() == second.json()
    assert first.json()["revoked_at"] is not None
    assert token not in first.text


def test_active_grant_limit_has_a_stable_recoverable_error(
    client,
    auth_headers,
    db_session,
    test_user,
) -> None:
    now = datetime.now(UTC)
    db_session.add_all(
        [
            AutomationGrant(
                user_id=test_user.id,
                label=f"Agent {index}",
                token_digest=f"{index:064x}",
                scopes=["system:read"],
                expires_at=now + timedelta(days=30),
            )
            for index in range(MAX_ACTIVE_GRANTS_PER_USER)
        ]
    )
    db_session.commit()

    response = client.post(ENDPOINT, headers=auth_headers, json=_payload())

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "active_grant_limit"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert db_session.query(AutomationGrant).count() == MAX_ACTIVE_GRANTS_PER_USER


def test_listing_keeps_every_active_grant_with_more_than_one_hundred_history_rows(
    client,
    auth_headers,
    db_session,
    test_user,
) -> None:
    now = datetime.now(UTC)
    active = AutomationGrant(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        label="Old but active",
        token_digest="a" * 64,
        scopes=["system:read"],
        expires_at=now + timedelta(days=30),
        created_at=now - timedelta(days=365),
        updated_at=now - timedelta(days=365),
    )
    history = [
        AutomationGrant(
            id=str(uuid.uuid4()),
            user_id=test_user.id,
            label=f"Revoked {index}",
            token_digest=f"{index + 1:064x}",
            scopes=["system:read"],
            expires_at=now + timedelta(days=30),
            revoked_at=now - timedelta(minutes=index + 1),
            created_at=now - timedelta(minutes=index),
            updated_at=now - timedelta(minutes=index),
        )
        for index in range(RECENT_GRANT_HISTORY_LIMIT + 5)
    ]
    db_session.add_all([active, *history])
    db_session.commit()

    response = client.get(ENDPOINT, headers=auth_headers)

    assert response.status_code == 200
    listed = response.json()
    grant_ids = {item["id"] for item in listed}
    assert len(listed) == RECENT_GRANT_HISTORY_LIMIT + 1
    assert listed[0]["id"] == active.id
    assert active.id in grant_ids

    revoked = client.post(
        f"{ENDPOINT}/{active.id}/revoke",
        headers=auth_headers,
        json={"password": "Globalpass1"},
    )
    assert revoked.status_code == 200
