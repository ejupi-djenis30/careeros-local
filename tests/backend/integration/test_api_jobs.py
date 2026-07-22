from datetime import datetime, timezone

import pytest

from backend.ai.audit import fingerprint_output
from backend.ai.match_evidence import (
    candidate_evidence_document,
    job_evidence_document,
    match_input_fingerprint,
)
from backend.ai.match_policy import derive_match_outcome, derive_match_presentation
from backend.ai.matching import _materialize_match_citations
from backend.ai.models import AIExecution
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


def _make_receipt_verified_job(db_session, test_user, profile, scraped_job):
    job = Job(
        user_id=test_user.id,
        search_profile_id=profile.id,
        scraped_job_id=scraped_job.id,
    )
    db_session.add(job)
    db_session.flush()

    candidate = candidate_evidence_document(
        {
            "cv_content": profile.cv_content,
            "role_description": profile.role_description,
            "search_strategy": profile.search_strategy,
        }
    )
    listing = job_evidence_document(
        {
            "title": scraped_job.title,
            "company": scraped_job.company,
            "location": scraped_job.location,
            "workload": scraped_job.workload,
            "description": scraped_job.description,
        },
        0,
        description_limit=1800,
    )
    dimensions = {
        "skill": 80,
        "experience": 80,
        "intent": 80,
        "language": 80,
        "location": 80,
        "transferability": 80,
        "qualification": 80,
    }
    contract_row = {
        "skill_match_score": dimensions["skill"],
        "experience_match_score": dimensions["experience"],
        "intent_match_score": dimensions["intent"],
        "language_match_score": dimensions["language"],
        "location_match_score": dimensions["location"],
        "transferability_score": dimensions["transferability"],
        "qualification_gap_score": dimensions["qualification"],
    }
    row_fingerprint = fingerprint_output(contract_row)
    output_fingerprint = fingerprint_output({"results": [contract_row]})
    input_fingerprint = match_input_fingerprint(candidate, listing)
    execution = AIExecution(
        user_id=test_user.id,
        task="job_match",
        contract_version="1.1.0",
        model_id="ollama/test-model",
        input_fingerprint="f" * 64,
        output_fingerprint=output_fingerprint,
        row_fingerprints=[row_fingerprint],
        row_input_fingerprints=[input_fingerprint],
        evidence_count=2,
        accepted=True,
        repair_count=0,
        validation_codes=[],
        duration_ms=1,
    )
    db_session.add(execution)
    db_session.flush()

    citations = _materialize_match_citations(
        candidate=candidate,
        job=listing,
        dimension_scores=dimensions,
    )
    affinity_score, recommendation, worth_applying = derive_match_outcome(dimensions, citations)
    summary, red_flags = derive_match_presentation(recommendation, citations)
    job.affinity_score = affinity_score
    job.affinity_analysis = summary
    job.worth_applying = worth_applying
    job.skill_match_score = dimensions["skill"]
    job.experience_match_score = dimensions["experience"]
    job.intent_match_score = dimensions["intent"]
    job.language_match_score = dimensions["language"]
    job.location_match_score = dimensions["location"]
    job.transferability_score = dimensions["transferability"]
    job.qualification_gap_score = dimensions["qualification"]
    job.analysis_structured = {
        "recommendation": recommendation,
        "evidence_citations": citations,
    }
    job.analysis_provenance = "local_model_validated"
    job.analysis_model_id = execution.model_id
    job.analysis_contract_version = execution.contract_version
    job.analysis_validated_at = datetime.now(timezone.utc)
    job.analysis_execution_id = execution.id
    job.analysis_output_fingerprint = output_fingerprint
    job.analysis_execution_row_index = 0
    job.analysis_row_fingerprint = row_fingerprint
    job.analysis_input_fingerprint = input_fingerprint
    job.red_flags = red_flags
    db_session.commit()
    return job


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

    def test_untrusted_analysis_cannot_change_filters_order_pagination_or_stats(
        self, client, auth_headers, db_session, test_user
    ):
        profile = SearchProfile(
            user_id=test_user.id,
            name="Receipt-aware queries",
            cv_content=(
                "Python engineer with eight years of experience building local services. "
                "English C2. Based in Zurich with a bachelor degree."
            ),
            role_description="Python engineer in Zurich",
            search_strategy="Find local Python backend roles",
        )
        db_session.add(profile)
        db_session.flush()
        trusted_listing = _make_scraped_job(
            db_session,
            "receipt-trusted",
            "Python Engineer",
            "Trusted Co",
            "https://example.test/trusted",
        )
        trusted_listing.description = (
            "Build Python services with an experienced team in Zurich. "
            "English B2 and a bachelor degree are required."
        )
        trusted_listing.location = "Zurich"
        trusted_job = _make_receipt_verified_job(db_session, test_user, profile, trusted_listing)

        forged_listing = _make_scraped_job(
            db_session,
            "receipt-forged",
            "Forged score role",
            "Untrusted Co",
            "https://example.test/forged",
        )
        forged_job = Job(
            user_id=test_user.id,
            search_profile_id=profile.id,
            scraped_job_id=forged_listing.id,
            affinity_score=100,
            affinity_analysis="Unsigned perfect fit",
            worth_applying=True,
            analysis_provenance="local_model_validated",
            analysis_model_id="ollama/forged",
            analysis_contract_version="1.1.0",
            analysis_validated_at=datetime.now(timezone.utc),
            analysis_execution_id=trusted_job.analysis_execution_id,
            analysis_output_fingerprint=trusted_job.analysis_output_fingerprint,
            analysis_execution_row_index=0,
            analysis_row_fingerprint=trusted_job.analysis_row_fingerprint,
            analysis_input_fingerprint=trusted_job.analysis_input_fingerprint,
        )
        db_session.add(forged_job)
        db_session.commit()

        scope = f"search_profile_id={profile.id}"
        first_page = client.get(
            f"/api/v1/jobs/?{scope}&sort_by=affinity_score&sort_order=desc&page_size=1",
            headers=auth_headers,
        )
        assert first_page.status_code == 200, first_page.text
        first_data = first_page.json()
        assert first_data["total"] == 2
        assert first_data["pages"] == 2
        assert first_data["avg_score"] == 80
        assert [item["id"] for item in first_data["items"]] == [trusted_job.id]
        assert first_data["items"][0]["analysis_verified"] is True

        second_page = client.get(
            f"/api/v1/jobs/?{scope}&sort_by=affinity_score&sort_order=desc&page=2&page_size=1",
            headers=auth_headers,
        ).json()
        assert [item["id"] for item in second_page["items"]] == [forged_job.id]
        assert second_page["items"][0]["analysis_verified"] is False
        assert second_page["items"][0]["affinity_score"] is None
        assert second_page["items"][0]["worth_applying"] is False

        above_trusted_score = client.get(
            f"/api/v1/jobs/?{scope}&min_score=90", headers=auth_headers
        ).json()
        assert above_trusted_score["total"] == 0
        assert above_trusted_score["items"] == []
        assert above_trusted_score["avg_score"] == 0

        trusted_range = client.get(
            f"/api/v1/jobs/?{scope}&min_score=75&max_score=85", headers=auth_headers
        ).json()
        assert trusted_range["total"] == 1
        assert [item["id"] for item in trusted_range["items"]] == [trusted_job.id]
        assert trusted_range["avg_score"] == 80

        trusted_recommendations = client.get(
            f"/api/v1/jobs/?{scope}&worth_applying=true", headers=auth_headers
        ).json()
        assert trusted_recommendations["total"] == 1
        assert [item["id"] for item in trusted_recommendations["items"]] == [trusted_job.id]


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


@pytest.mark.parametrize("field", ["affinity_score", "affinity_analysis", "worth_applying"])
def test_manual_job_creation_rejects_analysis_fields(client, auth_headers, field):
    payload = {
        "title": "Manual capture",
        "company": "ACME",
        "external_url": "https://example.com/manual-capture",
        field: 91 if field == "affinity_score" else (True if field == "worth_applying" else "fit"),
    }

    response = client.post("/api/v1/jobs/", json=payload, headers=auth_headers)

    assert response.status_code == 422


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
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["scraped_job_id"] == second.json()["scraped_job_id"]

    scraped_jobs = (
        db_session.query(ScrapedJob).filter(ScrapedJob.title == "Stable Manual Job").all()
    )
    assert len(scraped_jobs) == 1
    assert scraped_jobs[0].platform_job_id.startswith("manual-")


def test_manual_job_namespace_is_private_per_user_and_ignores_spoofed_id(
    client, auth_headers, db_session
):
    payload = {
        "title": "Private manual role",
        "company": "Private company",
        "external_url": "https://example.com/private-manual-role",
        "platform": "manual",
        "platform_job_id": "shared-spoofed-id",
    }
    first = client.post("/api/v1/jobs/", json=payload, headers=auth_headers)
    assert first.status_code == 200, first.text

    other = User(
        username="manual_namespace_other",
        hashed_password=get_password_hash("OtherPass123"),
    )
    db_session.add(other)
    db_session.commit()
    login = client.post(
        "/api/v1/auth/login",
        data={"username": other.username, "password": "OtherPass123"},
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    second = client.post("/api/v1/jobs/", json=payload, headers=other_headers)
    assert second.status_code == 200, second.text

    assert first.json()["scraped_job_id"] != second.json()["scraped_job_id"]
    assert first.json()["platform_job_id"] != second.json()["platform_job_id"]
    assert first.json()["platform_job_id"].startswith("manual-")
    assert second.json()["platform_job_id"].startswith("manual-")
    assert "shared-spoofed-id" not in {
        first.json()["platform_job_id"],
        second.json()["platform_job_id"],
    }
    first_visible = client.get("/api/v1/jobs/", headers=auth_headers).json()["items"]
    second_visible = client.get("/api/v1/jobs/", headers=other_headers).json()["items"]
    assert [item["id"] for item in first_visible] == [first.json()["id"]]
    assert [item["id"] for item in second_visible] == [second.json()["id"]]


def test_provider_listing_source_query_is_scoped_per_user(client, auth_headers, db_session):
    shared_listing = {
        "title": "Shared provider role",
        "company": "Shared company",
        "external_url": "https://example.test/shared-provider-role",
        "platform": "job-room",
        "platform_job_id": "shared-provider-id",
    }
    first = client.post(
        "/api/v1/jobs/",
        json={**shared_listing, "source_query": "private python query"},
        headers=auth_headers,
    )
    assert first.status_code == 200, first.text

    other = User(
        username="source_query_other",
        hashed_password=get_password_hash("OtherPass123"),
    )
    db_session.add(other)
    db_session.commit()
    login = client.post(
        "/api/v1/auth/login",
        data={"username": other.username, "password": "OtherPass123"},
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    second = client.post(
        "/api/v1/jobs/",
        json={**shared_listing, "source_query": "private java query"},
        headers=other_headers,
    )
    assert second.status_code == 200, second.text

    assert first.json()["scraped_job_id"] == second.json()["scraped_job_id"]
    assert first.json()["source_query"] == "private python query"
    assert second.json()["source_query"] == "private java query"
    assert "source_query" not in ScrapedJob.__table__.columns

    first_visible = client.get("/api/v1/jobs/", headers=auth_headers).json()["items"]
    second_visible = client.get("/api/v1/jobs/", headers=other_headers).json()["items"]
    assert [item["source_query"] for item in first_visible] == ["private python query"]
    assert [item["source_query"] for item in second_visible] == ["private java query"]

    persisted = (
        db_session.query(Job)
        .filter(Job.scraped_job_id == first.json()["scraped_job_id"])
        .order_by(Job.user_id)
        .all()
    )
    assert {job.source_query for job in persisted} == {
        "private python query",
        "private java query",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {
            "title": "Role",
            "company": "Company",
            "external_url": "https://example.test/role",
            "unexpected": "not accepted",
        },
        {
            "title": "R" * 241,
            "company": "Company",
            "external_url": "https://example.test/role",
        },
        {
            "title": "Role",
            "company": "Company",
            "external_url": "https://example.test/role",
            "raw_metadata": {str(index): index for index in range(101)},
        },
    ],
)
def test_manual_job_import_schema_is_bounded_and_forbids_extra(client, auth_headers, payload):
    assert client.post("/api/v1/jobs/", json=payload, headers=auth_headers).status_code == 422


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
