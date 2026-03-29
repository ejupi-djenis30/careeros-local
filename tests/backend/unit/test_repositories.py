from unittest.mock import MagicMock

import pytest

from backend.models import ScrapedJob
from backend.repositories.base import BaseRepository
from backend.repositories.job_repository import JobRepository
from backend.repositories.profile_repository import ProfileRepository

# We use the db_session fixture provided by our global conftest.py
# If tests run in isolation from test_integration, we might need to rely on the db_session.


@pytest.fixture
def profile_repo(db_session):
    return ProfileRepository(db_session)


@pytest.fixture
def job_repo(db_session):
    return JobRepository(db_session)


def _create_scraped_job(
    db_session,
    platform="test",
    platform_job_id="pj1",
    title="Test Job",
    company="Test Company",
    external_url="http://test.com",
):
    """Helper to create a ScrapedJob and flush it."""
    sj = ScrapedJob(
        platform=platform,
        platform_job_id=platform_job_id,
        title=title,
        company=company,
        external_url=external_url,
    )
    db_session.add(sj)
    db_session.flush()
    return sj


def test_profile_repository_create_and_get(profile_repo, test_user):
    data = {
        "user_id": test_user.id,
        "name": "Repo Test Profile",
        "role_description": "Architect",
        "scrape_mode": "sequential",
    }
    profile = profile_repo.create(data)

    assert profile.id is not None
    assert profile.name == "Repo Test Profile"

    # Fetch back
    fetched = profile_repo.get(profile.id)
    assert fetched.role_description == "Architect"

    # get_by_user
    user_profiles = profile_repo.get_by_user(test_user.id)
    assert len(user_profiles) >= 1
    assert any(p.name == "Repo Test Profile" for p in user_profiles)


def test_base_repository_get_all(profile_repo, test_user):
    profile_repo.create({"user_id": test_user.id, "name": "Profile A"})
    profile_repo.create({"user_id": test_user.id, "name": "Profile B"})

    all_profiles = profile_repo.get_all(limit=100)
    assert len(all_profiles) >= 2
    names = [p.name for p in all_profiles]
    assert "Profile A" in names
    assert "Profile B" in names


def test_base_repository_delete(profile_repo, test_user):
    profile = profile_repo.create({"user_id": test_user.id, "name": "To Delete"})
    profile_id = profile.id

    deleted = profile_repo.delete(profile_id)
    assert deleted is not None
    assert deleted.id == profile_id

    assert profile_repo.get(profile_id) is None

    # Delete non-existent
    assert profile_repo.delete(999999) is None


def test_profile_repository_update(profile_repo, test_user):
    data = {"user_id": test_user.id, "name": "Initial Name"}
    profile = profile_repo.create(data)

    updated = profile_repo.update(profile, {"name": "Updated Name", "max_queries": 10})
    assert updated.name == "Updated Name"
    assert updated.max_queries == 10


def test_job_repository_create_and_get(job_repo, profile_repo, test_user, db_session):
    profile = profile_repo.create({"user_id": test_user.id, "name": "Job Host"})

    # Create a ScrapedJob first
    sj = _create_scraped_job(
        db_session,
        platform="test",
        platform_job_id="pj-cag-1",
        title="Test Job Record",
        company="Test Company",
        external_url="http://test.com",
    )

    job = job_repo.create(
        {
            "user_id": test_user.id,
            "search_profile_id": profile.id,
            "scraped_job_id": sj.id,
        }
    )
    assert job.id is not None

    jobs = job_repo.get_by_user_filtered(test_user.id, skip=0, limit=10)
    total = job_repo.count_by_user_filtered(test_user.id)
    assert total >= 1
    titles = [j.title for j in jobs]
    assert "Test Job Record" in titles


def test_job_repository_filtering(job_repo, profile_repo, test_user, db_session):
    profile1 = profile_repo.create({"user_id": test_user.id, "name": "Profile 1"})
    profile2 = profile_repo.create({"user_id": test_user.id, "name": "Profile 2"})

    sj1 = _create_scraped_job(
        db_session,
        platform_job_id="pj-f1",
        title="Job Profile 1",
        company="Corp",
        external_url="http://f1.com",
    )
    sj2 = _create_scraped_job(
        db_session,
        platform_job_id="pj-f2",
        title="Job Profile 2",
        company="Corp",
        external_url="http://f2.com",
    )

    job_repo.create(
        {"user_id": test_user.id, "search_profile_id": profile1.id, "scraped_job_id": sj1.id}
    )
    job_repo.create(
        {"user_id": test_user.id, "search_profile_id": profile2.id, "scraped_job_id": sj2.id}
    )

    jobs_p1 = job_repo.get_by_user_filtered(
        test_user.id, skip=0, limit=10, search_profile_id=profile1.id
    )
    total_p1 = job_repo.count_by_user_filtered(test_user.id, search_profile_id=profile1.id)
    assert total_p1 == 1
    assert jobs_p1[0].title == "Job Profile 1"

    stats = job_repo.get_stats_by_user_filtered(test_user.id, search_profile_id=profile2.id)
    assert "total_applied" in stats
    assert stats["total_applied"] == 0


def test_job_repository_get_by_identifiers(job_repo, test_user, db_session):
    sj = _create_scraped_job(
        db_session,
        platform="generic",
        platform_job_id="pj-123",
        title="Identifier Job",
        company="ID Corp",
        external_url="http://id-corp.com",
    )
    job_repo.create({"user_id": test_user.id, "scraped_job_id": sj.id})

    # get_user_job_identifiers
    ids = job_repo.get_user_job_identifiers(test_user.id)
    assert ("generic", "pj-123", "http://id-corp.com", "Identifier Job", "ID Corp") in ids


def test_job_repository_get_profile_job_identifiers(job_repo, profile_repo, test_user, db_session):
    p1 = profile_repo.create({"user_id": test_user.id, "name": "P1"})
    p2 = profile_repo.create({"user_id": test_user.id, "name": "P2"})

    sj1 = _create_scraped_job(db_session, platform="p1", platform_job_id="j1", external_url="url1")
    sj2 = _create_scraped_job(db_session, platform="p2", platform_job_id="j2", external_url="url2")

    job_repo.create({"user_id": test_user.id, "search_profile_id": p1.id, "scraped_job_id": sj1.id})
    job_repo.create({"user_id": test_user.id, "search_profile_id": p2.id, "scraped_job_id": sj2.id})

    ids_p1 = job_repo.get_profile_job_identifiers(p1.id)
    assert ("p1", "j1", "url1", "Test Job", "Test Company") in ids_p1
    assert ("p2", "j2", "url2", "Test Job", "Test Company") not in ids_p1

    ids_p2 = job_repo.get_profile_job_identifiers(p2.id)
    assert ("p2", "j2", "url2", "Test Job", "Test Company") in ids_p2
    assert ("p1", "j1", "url1", "Test Job", "Test Company") not in ids_p2


class _DummyModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_base_repository_create_rolls_back_on_commit_failure():
    db = MagicMock()
    db.commit.side_effect = RuntimeError("commit failed")
    repo = BaseRepository(_DummyModel, db)

    with pytest.raises(RuntimeError, match="commit failed"):
        repo.create({"name": "will-fail"})

    db.rollback.assert_called_once()
    db.refresh.assert_not_called()


def test_base_repository_update_rolls_back_on_commit_failure():
    db = MagicMock()
    db.commit.side_effect = RuntimeError("commit failed")
    repo = BaseRepository(_DummyModel, db)
    obj = _DummyModel(name="before")

    with pytest.raises(RuntimeError, match="commit failed"):
        repo.update(obj, {"name": "after"})

    db.rollback.assert_called_once()
    db.refresh.assert_not_called()


def test_base_repository_delete_rolls_back_on_commit_failure():
    db = MagicMock()
    db.commit.side_effect = RuntimeError("commit failed")
    obj = _DummyModel(id=123)
    db.get.return_value = obj
    repo = BaseRepository(_DummyModel, db)

    with pytest.raises(RuntimeError, match="commit failed"):
        repo.delete(123)

    db.rollback.assert_called_once()
