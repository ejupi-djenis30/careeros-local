from datetime import datetime, timezone

import pytest

from backend.models import Job, ScrapedJob, SearchProfile, User
from backend.services.auth import get_password_hash


def _make_scraped_job(
    db_session,
    platform_job_id,
    title,
    company,
    external_url,
    platform="test",
    publication_date=None,
):
    """Helper to create a ScrapedJob and flush it to get an id."""
    sj = ScrapedJob(
        platform=platform,
        platform_job_id=platform_job_id,
        title=title,
        company=company,
        external_url=external_url,
        publication_date=publication_date,
    )
    db_session.add(sj)
    db_session.flush()
    return sj


@pytest.fixture
def setup_job_data(db_session, test_user):
    # Create profile
    profile = SearchProfile(user_id=test_user.id, name="Job Data Tests")
    db_session.add(profile)
    db_session.flush()

    # Create ScrapedJobs first
    sj1 = _make_scraped_job(db_session, "pj1", "Backend Dev", "A", "http://a")
    sj2 = _make_scraped_job(db_session, "pj2", "Frontend Dev", "B", "http://b")
    sj3 = _make_scraped_job(db_session, "pj3", "QA Auto", "C", "http://c")

    # Create dummy jobs linking to ScrapedJobs
    job1 = Job(
        user_id=test_user.id,
        search_profile_id=profile.id,
        scraped_job_id=sj1.id,
        affinity_score=100,
    )
    job2 = Job(
        user_id=test_user.id,
        search_profile_id=profile.id,
        scraped_job_id=sj2.id,
        affinity_score=40,
        worth_applying=True,
    )
    job3 = Job(
        user_id=test_user.id,
        search_profile_id=profile.id,
        scraped_job_id=sj3.id,
        affinity_score=0,
        applied=True,
    )

    db_session.add_all([job1, job2, job3])
    db_session.commit()

    return profile.id, [job1.id, job2.id, job3.id]


class TestAdvancedJobsAPI:
    def test_get_all_jobs_pagination(self, client, auth_headers, setup_job_data):
        prof_id, job_ids = setup_job_data

        response = client.get("/api/v1/jobs/?page=1&page_size=2", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2  # Testing strict limit adherence
        assert data["total"] >= 3

    def test_get_jobs_filter_by_profile(self, client, auth_headers, setup_job_data):
        prof_id, job_ids = setup_job_data

        response = client.get(f"/api/v1/jobs/?search_profile_id={prof_id}", headers=auth_headers)
        data = response.json()
        assert data["total"] == 3
        # Should be ordered descendingly by default
        titles = [j["title"] for j in data["items"]]
        assert "Backend Dev" in titles

    def test_get_jobs_filter_by_status_applied(self, client, auth_headers, setup_job_data):
        prof_id, job_ids = setup_job_data
        response = client.get("/api/v1/jobs/?applied=true", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        applied_titles = [j["title"] for j in data["items"]]
        assert "QA Auto" in applied_titles
        assert "Backend Dev" not in applied_titles

    def test_get_jobs_filter_by_worth_applying(self, client, auth_headers, setup_job_data):
        prof_id, job_ids = setup_job_data
        response = client.get("/api/v1/jobs/?worth_applying=true", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        # Verify that all returned items have worth_applying == True
        for item in data["items"]:
            assert item["worth_applying"] is True

    def test_apply_to_job(self, client, auth_headers, setup_job_data):
        prof_id, job_ids = setup_job_data
        # QA Auto is job_ids[2] which is already applied, let's mark Backend Dev (job_ids[0]) as applied
        job_to_apply = job_ids[0]

        response = client.patch(
            f"/api/v1/jobs/{job_to_apply}", json={"applied": True}, headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["applied"] is True

        # Unapply it
        response2 = client.patch(
            f"/api/v1/jobs/{job_to_apply}", json={"applied": False}, headers=auth_headers
        )
        assert response2.status_code == 200
        assert response2.json()["applied"] is False

    def test_apply_job_not_found(self, client, auth_headers):
        response = client.patch("/api/v1/jobs/999999", json={"applied": True}, headers=auth_headers)
        assert response.status_code == 404
        assert response.json()["detail"] == "Job not found"

    def test_get_jobs_sort_by_title(self, client, auth_headers, db_session, test_user):
        profile = SearchProfile(user_id=test_user.id, name="Sort By Title")
        db_session.add(profile)
        db_session.flush()

        sj1 = _make_scraped_job(db_session, "sort-a", "Zeta Engineer", "A", "http://zeta")
        sj2 = _make_scraped_job(db_session, "sort-b", "Alpha Engineer", "B", "http://alpha")
        db_session.add_all(
            [
                Job(user_id=test_user.id, search_profile_id=profile.id, scraped_job_id=sj1.id),
                Job(user_id=test_user.id, search_profile_id=profile.id, scraped_job_id=sj2.id),
            ]
        )
        db_session.commit()

        response = client.get("/api/v1/jobs/?sort_by=title&sort_order=asc", headers=auth_headers)
        assert response.status_code == 200
        titles = [item["title"] for item in response.json()["items"]]
        assert titles[:2] == ["Alpha Engineer", "Zeta Engineer"]

    def test_get_jobs_sort_by_publication_date(self, client, auth_headers, db_session, test_user):
        profile = SearchProfile(user_id=test_user.id, name="Sort By Publication")
        db_session.add(profile)
        db_session.flush()

        sj1 = _make_scraped_job(
            db_session,
            "pub-old",
            "Older Posting",
            "A",
            "http://older",
            publication_date=datetime(2024, 1, 10, tzinfo=timezone.utc),
        )
        sj2 = _make_scraped_job(
            db_session,
            "pub-new",
            "Newer Posting",
            "B",
            "http://newer",
            publication_date=datetime(2024, 2, 10, tzinfo=timezone.utc),
        )
        db_session.add_all(
            [
                Job(user_id=test_user.id, search_profile_id=profile.id, scraped_job_id=sj1.id),
                Job(user_id=test_user.id, search_profile_id=profile.id, scraped_job_id=sj2.id),
            ]
        )
        db_session.commit()

        response = client.get(
            "/api/v1/jobs/?sort_by=publication_date&sort_order=desc", headers=auth_headers
        )
        assert response.status_code == 200
        titles = [item["title"] for item in response.json()["items"]]
        assert titles[:2] == ["Newer Posting", "Older Posting"]


def test_jobs_crud_flow(client, auth_headers: dict):
    # 1. List jobs (empty)
    response = client.get("/api/v1/jobs/", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 0


@pytest.mark.parametrize(
    "params,expected_detail",
    [
        ("min_score=80&max_score=20", "min_score cannot be greater than max_score"),
        ("min_distance=100&max_distance=10", "min_distance cannot be greater than max_distance"),
    ],
)
def test_jobs_list_score_distance_cross_validation(client, auth_headers, params, expected_detail):
    response = client.get(f"/api/v1/jobs/?{params}", headers=auth_headers)
    assert response.status_code == 422
    assert expected_detail in response.json()["detail"]

    # 2. Create a job
    job_data = {
        "title": "Integration Test Job",
        "company": "Test Co",
        "platform": "test",
        "platform_job_id": "tp1",
        "external_url": "http://test.com/job1",
    }
    response = client.post("/api/v1/jobs/", json=job_data, headers=auth_headers)
    assert response.status_code == 200
    job_id = response.json()["id"]

    # 3. Update job
    response = client.patch(f"/api/v1/jobs/{job_id}", json={"applied": True}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["applied"] is True

    # 4. List jobs (1 item)
    response = client.get("/api/v1/jobs/", headers=auth_headers)
    assert response.json()["total"] == 1

    # 5. Delete job
    response = client.delete(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert response.status_code == 204

    # 6. Ensure job is gone
    response = client.get("/api/v1/jobs/", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_create_job_rejects_foreign_profile(client, auth_headers, db_session):
    other_user = User(
        username="job_foreign_profile_user",
        hashed_password=get_password_hash("OtherPass123"),
    )
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    other_profile = SearchProfile(user_id=other_user.id, name="Other User Profile")
    db_session.add(other_profile)
    db_session.commit()

    response = client.post(
        "/api/v1/jobs/",
        json={
            "title": "Unauthorized Link",
            "company": "ACME",
            "external_url": "https://example.com/unauthorized-link",
            "search_profile_id": other_profile.id,
        },
        headers=auth_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Unauthorized profile access"


def test_create_job_without_platform_job_id_reuses_same_scraped_job(
    client, auth_headers, db_session
):
    payload = {
        "title": "Stable Manual Job",
        "company": "ACME",
        "external_url": "https://example.com/stable-manual-job",
    }

    first = client.post("/api/v1/jobs/", json=payload, headers=auth_headers)
    second = client.post("/api/v1/jobs/", json=payload, headers=auth_headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["scraped_job_id"] == second.json()["scraped_job_id"]

    scraped_jobs = (
        db_session.query(ScrapedJob).filter(ScrapedJob.title == "Stable Manual Job").all()
    )
    assert len(scraped_jobs) == 1
    assert scraped_jobs[0].platform_job_id.startswith("manual-")


def test_jobs_response_includes_normalized_job_data(client, auth_headers, db_session, test_user):
    profile = SearchProfile(user_id=test_user.id, name="Normalized Response")
    db_session.add(profile)
    db_session.flush()

    scraped = ScrapedJob(
        platform="test",
        platform_job_id="normalized-1",
        title="Bus Driver",
        company="Transit AG",
        external_url="https://example.com/bus-driver",
        normalization_status="normalized",
        normalization_source="llm_normalizer",
        normalized_title="Bus Driver",
        normalized_role_family="Driver",
        normalized_domain="transport",
        normalized_employment_mode="on-site",
        normalized_workload_min=100,
        normalized_workload_max=100,
        normalized_required_languages=[{"code": "de", "level": "B1"}],
        normalized_metadata={"bootstrap": False},
    )
    db_session.add(scraped)
    db_session.flush()
    db_session.add(
        Job(user_id=test_user.id, search_profile_id=profile.id, scraped_job_id=scraped.id)
    )
    db_session.commit()

    response = client.get("/api/v1/jobs/", headers=auth_headers)
    assert response.status_code == 200
    item = next(job for job in response.json()["items"] if job["title"] == "Bus Driver")
    assert item["normalized_job"]["status"] == "normalized"
    assert item["normalized_job"]["domain"] == "transport"
    assert item["normalized_job"]["required_languages"] == [{"code": "de", "level": "B1"}]
