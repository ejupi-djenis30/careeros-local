"""Reservation cleanup must not erase a replacement search owner's status."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.db.base import SessionLocal
from backend.models import SearchProfile
from backend.repositories.profile_repository import ProfileRepository
from backend.services import search_status


@pytest.fixture
def reserved_profile(db_session, test_user):
    profile = SearchProfile(
        user_id=test_user.id,
        name="Synthetic reservation",
        role_description="Synthetic role",
        cv_content="Synthetic skills",
    )
    db_session.add(profile)
    db_session.commit()
    repo = ProfileRepository(db_session)
    assert repo.acquire_search_lock(
        profile.id, "current-owner", reservation_ttl_seconds=30, active_ttl_seconds=1800
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    payload = {
        "state": "reserved",
        "reservation_token": "current-owner",
        "user_id": test_user.id,
        "started_at": timestamp,
        "updated_at": timestamp,
        "finished_at": None,
    }
    assert repo.update_search_status(profile.id, payload)
    return profile.id, payload


def test_expired_owner_release_preserves_current_lock_and_status(db_session, reserved_profile):
    profile_id, payload = reserved_profile

    assert search_status.release_task(profile_id, "expired-owner") is False

    db_session.expire_all()
    profile = ProfileRepository(db_session).get(profile_id)
    assert profile.search_lock_token == "current-owner"
    assert profile.search_lock_state == "reserved"
    assert profile.search_status_payload == payload
    visible = search_status.get_status(profile_id)
    assert all(visible[key] == value for key, value in payload.items())


@pytest.mark.parametrize("local_token", [None, "current-owner", "expired-owner"])
def test_stale_release_preserves_new_local_status(db_session, reserved_profile, local_token):
    profile_id, payload = reserved_profile
    with search_status._lock:
        search_status._statuses[profile_id] = payload.copy()
        if local_token is not None:
            search_status._reserved_tasks[profile_id] = {"token": local_token}

    assert search_status.release_task(profile_id, "expired-owner") is (
        local_token == "expired-owner"
    )

    assert search_status._statuses[profile_id] == payload
    if local_token == "current-owner":
        assert search_status._reserved_tasks[profile_id]["token"] == "current-owner"
    else:
        assert profile_id not in search_status._reserved_tasks
    assert ProfileRepository(db_session).get_search_status(profile_id) == payload


@pytest.mark.parametrize("token", ["current-owner", None])
def test_matching_or_maintenance_release_clears_reserved_state(db_session, reserved_profile, token):
    profile_id, payload = reserved_profile
    with search_status._lock:
        search_status._statuses[profile_id] = payload.copy()
        search_status._reserved_tasks[profile_id] = {"token": "current-owner"}

    assert search_status.release_task(profile_id, token) is True

    assert profile_id not in search_status._statuses
    assert profile_id not in search_status._reserved_tasks
    db_session.expire_all()
    profile = ProfileRepository(db_session).get(profile_id)
    assert profile.search_lock_token is None
    assert profile.search_lock_state is None
    assert profile.search_lock_acquired_at is None
    assert profile.search_status_state is None
    assert profile.search_status_payload is None
    assert profile.search_status_started_at is None
    assert profile.search_status_updated_at is None
    assert profile.search_status_finished_at is None


@pytest.mark.parametrize("state", ["searching", "done", "error", "stopped", "cancelled"])
def test_release_preserves_progress_and_terminal_status(db_session, reserved_profile, state):
    profile_id, payload = reserved_profile
    payload = {**payload, "state": state}
    repo = ProfileRepository(db_session)
    assert repo.update_search_status(profile_id, payload)
    with search_status._lock:
        search_status._statuses[profile_id] = payload.copy()

    assert search_status.release_task(profile_id, "current-owner") is True

    assert search_status._statuses[profile_id] == payload
    assert repo.get_search_status(profile_id) == payload
    db_session.expire_all()
    assert repo.get(profile_id).search_lock_token is None


def test_release_preserves_reserved_status_with_different_owner(db_session, reserved_profile):
    profile_id, payload = reserved_profile
    payload = {**payload, "reservation_token": "another-status-owner"}
    repo = ProfileRepository(db_session)
    assert repo.update_search_status(profile_id, payload)

    assert search_status.release_task(profile_id, "current-owner") is True

    assert repo.get_search_status(profile_id) == payload


def test_failed_release_commit_rolls_back_lock_and_status(db_session, reserved_profile):
    profile_id, payload = reserved_profile
    repo = ProfileRepository(db_session)
    with patch.object(db_session, "commit", side_effect=RuntimeError("synthetic commit failure")):
        with pytest.raises(RuntimeError, match="synthetic commit failure"):
            repo.release_search_lock(profile_id, "current-owner")

    with SessionLocal() as fresh_session:
        profile = ProfileRepository(fresh_session).get(profile_id)
        assert profile.search_lock_token == "current-owner"
        assert profile.search_lock_state == "reserved"
        assert profile.search_status_payload == payload
        assert profile.search_status_started_at is not None
        assert profile.search_status_updated_at is not None
