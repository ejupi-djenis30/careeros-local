from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.schemas import JobCreate, JobUpdate
from backend.services.job_service import JobService


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.get_applied_scraped_job_ids.return_value = set()
    return repo


@pytest.fixture
def job_service(mock_repo):
    service = JobService(MagicMock())
    service.repo = mock_repo
    return service


def test_get_jobs_by_user(job_service, mock_repo):
    job1 = MagicMock()
    job1.applied = False
    job1.scraped_job_id = 101

    job2 = MagicMock()
    job2.applied = False
    job2.scraped_job_id = 102

    mock_repo.get_by_user_filtered.return_value = [job1, job2]
    mock_repo.get_count_and_stats_by_user_filtered.return_value = {
        "total": 2,
        "total_applied": 1,
        "avg_score": 85.0,
    }
    mock_repo.get_applied_scraped_job_ids.return_value = {101}  # job1 applied elsewhere

    result = job_service.get_jobs_by_user(
        1, page=1, page_size=10, filters={"sort_by": "created_at"}
    )

    assert result["total"] == 2
    assert len(result["items"]) == 2
    assert result["items"][0].applied_elsewhere is True
    assert result["items"][1].applied_elsewhere is False
    assert result["total_applied"] == 1
    mock_repo.get_by_user_filtered.assert_called_once()
    mock_repo.get_applied_scraped_job_ids.assert_called_once_with(1)


def test_create_job(job_service, mock_repo):
    # JobCreate requires title, company, external_url
    job_in = JobCreate(
        title="New Job", company="Test Corp", external_url="https://test.com", scraped_job_id=1
    )
    mock_repo.db.query.return_value.filter.return_value.first.return_value = None
    job_service.create_job(1, job_in)
    mock_repo.create.assert_called_once()


def test_create_job_uses_deterministic_manual_platform_job_id(job_service, mock_repo):
    job_in = JobCreate(
        title="Stable Job",
        company="ACME",
        external_url="https://example.com/stable-job",
    )

    job_service.create_job(1, job_in)
    first_call_fields = mock_repo.get_or_create_scraped_job.call_args_list[0].args[0]

    mock_repo.get_or_create_scraped_job.reset_mock()
    job_service.create_job(1, job_in)
    second_call_fields = mock_repo.get_or_create_scraped_job.call_args_list[0].args[0]

    assert first_call_fields["platform_job_id"] is not None
    assert first_call_fields["platform_job_id"] == second_call_fields["platform_job_id"]


def test_create_job_rejects_foreign_profile(job_service, mock_repo):
    query_result = mock_repo.db.query.return_value.filter.return_value
    query_result.first.side_effect = [None]

    profile_query = MagicMock()
    profile_query.filter.return_value.first.return_value = None
    mock_repo.db.query.side_effect = [profile_query]

    with pytest.raises(HTTPException) as exc:
        job_service.create_job(
            1,
            JobCreate(
                title="Foreign Profile Job",
                company="ACME",
                external_url="https://example.com/foreign",
                search_profile_id=999,
            ),
        )

    assert exc.value.status_code == 403


def test_update_job_success(job_service, mock_repo):
    mock_job = MagicMock()
    mock_job.user_id = 1
    mock_job.dismissed = False
    mock_repo.get.return_value = mock_job

    updates = JobUpdate(applied=True)
    job_service.update_job(1, 101, updates)
    mock_repo.update.assert_called_once_with(mock_job, {"applied": True})


def test_update_job_not_found(job_service, mock_repo):
    mock_repo.get.return_value = None
    with pytest.raises(Exception) as exc:
        job_service.update_job(1, 999, JobUpdate())
    assert "404" in str(exc.value)


def test_update_job_forbidden(job_service, mock_repo):
    mock_job = MagicMock()
    mock_job.user_id = 2  # Different user
    mock_repo.get.return_value = mock_job

    with pytest.raises(Exception) as exc:
        job_service.update_job(1, 101, JobUpdate())
    assert "403" in str(exc.value)
