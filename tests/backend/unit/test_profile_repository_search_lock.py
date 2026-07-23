from datetime import datetime, timedelta, timezone

from backend.models import SearchProfile
from backend.repositories.profile_repository import (
    SEARCH_LOCK_ACTIVE,
    SEARCH_LOCK_RESERVED,
    ProfileRepository,
)


def _create_profile(db_session, test_user) -> SearchProfile:
    profile = SearchProfile(
        user_id=test_user.id,
        name="Search Lock Profile",
        role_description="Backend Engineer",
        cv_content="Python, FastAPI, PostgreSQL",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


def test_acquire_search_lock_sets_reserved_state(db_session, test_user):
    repo = ProfileRepository(db_session)
    profile = _create_profile(db_session, test_user)

    acquired = repo.acquire_search_lock(
        profile.id,
        "token-1",
        reservation_ttl_seconds=30,
        active_ttl_seconds=1800,
    )

    refreshed = repo.get(profile.id)
    assert acquired is True
    assert refreshed is not None
    assert refreshed.search_lock_token == "token-1"
    assert refreshed.search_lock_state == SEARCH_LOCK_RESERVED
    assert refreshed.search_lock_acquired_at is not None


def test_activate_search_lock_promotes_reserved_lock_to_active(db_session, test_user):
    repo = ProfileRepository(db_session)
    profile = _create_profile(db_session, test_user)
    repo.acquire_search_lock(
        profile.id,
        "token-2",
        reservation_ttl_seconds=30,
        active_ttl_seconds=1800,
    )

    activated = repo.activate_search_lock(profile.id, "token-2")

    refreshed = repo.get(profile.id)
    assert activated is True
    assert refreshed is not None
    assert refreshed.search_lock_state == SEARCH_LOCK_ACTIVE


def test_acquire_search_lock_rejects_live_active_lock(db_session, test_user):
    repo = ProfileRepository(db_session)
    profile = _create_profile(db_session, test_user)
    repo.acquire_search_lock(
        profile.id,
        "token-3",
        reservation_ttl_seconds=30,
        active_ttl_seconds=1800,
    )
    repo.activate_search_lock(profile.id, "token-3")

    acquired = repo.acquire_search_lock(
        profile.id,
        "token-4",
        reservation_ttl_seconds=30,
        active_ttl_seconds=1800,
    )

    refreshed = repo.get(profile.id)
    assert acquired is False
    assert refreshed is not None
    assert refreshed.search_lock_token == "token-3"
    assert refreshed.search_lock_state == SEARCH_LOCK_ACTIVE


def test_acquire_search_lock_reclaims_stale_reserved_lock(db_session, test_user):
    repo = ProfileRepository(db_session)
    profile = _create_profile(db_session, test_user)
    profile.search_lock_token = "stale-token"
    profile.search_lock_state = SEARCH_LOCK_RESERVED
    profile.search_lock_acquired_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    db_session.add(profile)
    db_session.commit()

    acquired = repo.acquire_search_lock(
        profile.id,
        "fresh-token",
        reservation_ttl_seconds=30,
        active_ttl_seconds=1800,
    )

    refreshed = repo.get(profile.id)
    assert acquired is True
    assert refreshed is not None
    assert refreshed.search_lock_token == "fresh-token"
    assert refreshed.search_lock_state == SEARCH_LOCK_RESERVED


def test_release_search_lock_clears_lock_fields(db_session, test_user):
    repo = ProfileRepository(db_session)
    profile = _create_profile(db_session, test_user)
    repo.acquire_search_lock(
        profile.id,
        "token-5",
        reservation_ttl_seconds=30,
        active_ttl_seconds=1800,
    )

    released = repo.release_search_lock(profile.id, "token-5")

    refreshed = repo.get(profile.id)
    assert released is True
    assert refreshed is not None
    assert refreshed.search_lock_token is None
    assert refreshed.search_lock_state is None
    assert refreshed.search_lock_acquired_at is None


def test_update_search_status_persists_payload_and_timestamps(db_session, test_user):
    repo = ProfileRepository(db_session)
    profile = _create_profile(db_session, test_user)
    payload = {
        "user_id": test_user.id,
        "state": "searching",
        "started_at": "2026-04-02T10:00:00+00:00",
        "updated_at": "2026-04-02T10:00:05+00:00",
        "finished_at": None,
        "jobs_found": 3,
    }

    updated = repo.update_search_status(profile.id, payload)

    refreshed = repo.get(profile.id)
    assert updated is True
    assert refreshed is not None
    assert refreshed.search_status_state == "searching"
    assert refreshed.search_status_payload == payload
    assert refreshed.search_status_started_at is not None
    assert refreshed.search_status_updated_at is not None
    assert refreshed.search_status_finished_at is None


def test_get_search_statuses_returns_statuses_for_user_only(db_session, test_user):
    repo = ProfileRepository(db_session)
    profile = _create_profile(db_session, test_user)
    repo.update_search_status(
        profile.id,
        {
            "user_id": test_user.id,
            "state": "done",
            "started_at": "2026-04-02T10:00:00+00:00",
            "updated_at": "2026-04-02T10:05:00+00:00",
            "finished_at": "2026-04-02T10:05:00+00:00",
        },
    )

    statuses = repo.get_search_statuses(user_id=test_user.id)
    single = repo.get_search_status(profile.id)

    assert profile.id in statuses
    assert statuses[profile.id]["state"] == "done"
    assert single is not None
    assert single["state"] == "done"


def test_clear_search_status_resets_status_columns(db_session, test_user):
    repo = ProfileRepository(db_session)
    profile = _create_profile(db_session, test_user)
    repo.update_search_status(
        profile.id,
        {
            "user_id": test_user.id,
            "state": "error",
            "started_at": "2026-04-02T10:00:00+00:00",
            "updated_at": "2026-04-02T10:01:00+00:00",
            "finished_at": "2026-04-02T10:01:00+00:00",
            "error": "boom",
        },
    )

    cleared = repo.clear_search_status(profile.id)

    refreshed = repo.get(profile.id)
    assert cleared is True
    assert refreshed is not None
    assert refreshed.search_status_state is None
    assert refreshed.search_status_payload is None
    assert refreshed.search_status_started_at is None
    assert refreshed.search_status_updated_at is None
    assert refreshed.search_status_finished_at is None


def test_clear_stale_search_statuses_removes_old_terminal_entries(db_session, test_user):
    repo = ProfileRepository(db_session)
    profile = _create_profile(db_session, test_user)
    profile.search_status_state = "done"
    profile.search_status_payload = {
        "state": "done",
        "started_at": "2026-04-01T10:00:00+00:00",
        "updated_at": "2026-04-01T10:01:00+00:00",
        "finished_at": "2026-04-01T10:01:00+00:00",
    }
    profile.search_status_started_at = datetime.now(timezone.utc) - timedelta(days=2)
    profile.search_status_updated_at = datetime.now(timezone.utc) - timedelta(days=2)
    profile.search_status_finished_at = datetime.now(timezone.utc) - timedelta(days=2)
    db_session.add(profile)
    db_session.commit()

    cleared = repo.clear_stale_search_statuses(
        max_age_seconds=3600,
        terminal_states=["done", "error", "stopped", "cancelled"],
    )

    refreshed = repo.get(profile.id)
    assert cleared == 1
    assert refreshed is not None
    assert refreshed.search_status_state is None
    assert refreshed.search_status_payload is None
