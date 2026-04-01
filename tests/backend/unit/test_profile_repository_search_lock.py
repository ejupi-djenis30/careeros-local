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
