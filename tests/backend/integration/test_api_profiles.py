import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from backend.models import SearchProfile, User
from backend.repositories.profile_repository import ProfileRepository
from backend.services.auth import get_password_hash


class TestAdvancedProfilesAPI:
    def test_get_profiles_empty_or_populated(self, client, auth_headers):
        response = client.get("/api/v1/profiles/", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_create_profile_valid(self, client, auth_headers):
        payload = {
            "name": "Integration Test Profile Full",
            "role_description": "Senior DevOps Engineer",
            "cv_content": "Docker, Kubernetes, AWS, Python",
            "search_strategy": "Ignore junior roles",
            "location_filter": "Zurich",
            "max_distance": 50,
            "workload_filter": "80-100",
            "max_queries": 5,
            "scrape_mode": "sequential",
        }
        # Patch out the background search so it doesn't attempt a real DB/LLM call
        with patch(
            "backend.services.search_service.SearchService.run_search",
            new_callable=AsyncMock,
        ):
            response = client.post("/api/v1/search/start", json=payload, headers=auth_headers)
        assert response.status_code == 200
        assert "profile_id" in response.json()

    def test_get_profiles_unauthorized(self, client):
        response = client.get("/api/v1/profiles/")
        assert response.status_code == 401  # Unauthorized missing token

    def test_create_profile_validation_failure(self, client, auth_headers):
        # Invalid data types
        payload = {
            "name": 12345,  # Should be explicitly string or coerced
            "max_distance": "NOT A NUMBER",
        }
        response = client.post("/api/v1/search/start", json=payload, headers=auth_headers)
        assert response.status_code == 422  # Unprocessable Entity

    def test_create_profile_accepts_large_numeric_values(self, client, auth_headers):
        payload = {
            "name": "High Limit Profile",
            "role_description": "Platform Engineer",
            "cv_content": "Python, Docker, Kubernetes",
            "location_filter": "Zurich",
            "posted_within_days": 999999,
            "max_distance": 999999,
            "schedule_enabled": True,
            "schedule_interval_hours": 999999,
            "max_queries": 999999,
        }

        response = client.post("/api/v1/profiles/", json=payload, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["posted_within_days"] == 999999
        assert data["max_distance"] == 999999
        assert data["schedule_interval_hours"] == 999999
        assert data["max_queries"] == 999999

    def test_delete_profile_cascades(self, client, auth_headers, db_session, test_user):
        from backend.models import Job, ScrapedJob, SearchProfile

        # 1. Create a profile
        print("\n[TEST] Creating profile...")
        p = SearchProfile(user_id=test_user.id, name="ToDelete")
        db_session.add(p)
        db_session.commit()
        profile_id = p.id
        print(f"[TEST] Profile ID: {profile_id}")

        # 2. Create a scraped job
        print("[TEST] Creating scraped job...")
        sj = ScrapedJob(
            platform="test", platform_job_id="del1", title="T", company="C", external_url="H"
        )
        db_session.add(sj)
        db_session.commit()
        scraped_id = sj.id
        print(f"[TEST] Scraped Job ID: {scraped_id}")

        # 3. Create a job for that profile
        print("[TEST] Creating user job...")
        j = Job(user_id=test_user.id, search_profile_id=profile_id, scraped_job_id=scraped_id)
        db_session.add(j)
        db_session.commit()
        job_id = j.id
        print(f"[TEST] Job ID: {job_id}")

        # 4. Delete profile via API
        print("[TEST] Calling DELETE API...")
        response = client.delete(f"/api/v1/profiles/{profile_id}", headers=auth_headers)
        print(f"[TEST] API Response: {response.status_code}")
        assert response.status_code == 204

        # 5. Verify Job is gone, but ScrapedJob remains
        print("[TEST] Verifying cascade...")
        db_session.expire_all()
        assert db_session.get(SearchProfile, profile_id) is None
        assert db_session.get(Job, job_id) is None
        assert db_session.get(ScrapedJob, scraped_id) is not None
        print("[TEST] Success!")


def test_profiles_crud_flow(client, auth_headers: dict):
    # 1. Create profile
    profile_data = {
        "name": "Test Profile",
        "role_description": "DevOps",
        "search_strategy": "Aggressive",
    }
    response = client.post("/api/v1/profiles/", json=profile_data, headers=auth_headers)
    assert response.status_code == 200
    profile_id = response.json()["id"]

    # 2. Get profiles
    response = client.get("/api/v1/profiles/", headers=auth_headers)
    assert len(response.json()) >= 1

    # 3. Toggle schedule
    response = client.patch(
        f"/api/v1/profiles/{profile_id}/schedule",
        json={"enabled": True, "interval_hours": 24},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["schedule_enabled"] is True


def test_profile_receipt_is_read_only_and_user_scoped(client, auth_headers, db_session, test_user):
    owner_profile = SearchProfile(user_id=test_user.id, name="Owner receipt")
    other_user = User(
        username="receipt_other_user",
        hashed_password=get_password_hash("OtherPass123"),
    )
    db_session.add_all([owner_profile, other_user])
    db_session.flush()
    other_profile = SearchProfile(user_id=other_user.id, name="Other receipt")
    db_session.add(other_profile)
    db_session.commit()

    started_at = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
    finished_at = started_at + timedelta(minutes=2)
    repo = ProfileRepository(db_session)
    for profile, jobs_found in ((owner_profile, 3), (other_profile, 99)):
        assert repo.update_search_status(
            profile.id,
            {
                "state": "done",
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "updated_at": finished_at.isoformat(),
                "jobs_found": jobs_found,
                "provider_successes": 1,
            },
        )

    owner_response = client.get("/api/v1/profiles/", headers=auth_headers)
    assert owner_response.status_code == 200
    owner_items = owner_response.json()
    assert [item["id"] for item in owner_items] == [owner_profile.id]
    assert owner_items[0]["last_search_state"] == "done"
    assert owner_items[0]["search_run_count"] == 1
    assert owner_items[0]["last_search_summary"]["counts"]["jobs_found"] == 3
    assert "99" not in str(owner_items[0]["last_search_summary"])

    login = client.post(
        "/api/v1/auth/login",
        data={"username": other_user.username, "password": "OtherPass123"},
    )
    assert login.status_code == 200
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    other_items = client.get("/api/v1/profiles/", headers=other_headers).json()
    assert [item["id"] for item in other_items] == [other_profile.id]
    assert other_items[0]["last_search_summary"]["counts"]["jobs_found"] == 99

    attempted_write = client.post(
        "/api/v1/profiles/",
        json={
            "name": "Cannot forge receipt",
            "last_search_state": "done",
            "search_run_count": 500,
            "last_search_summary": {"private": "forged"},
        },
        headers=auth_headers,
    )
    assert attempted_write.status_code == 200
    assert attempted_write.json()["last_search_state"] is None
    assert attempted_write.json()["search_run_count"] == 0
    assert attempted_write.json()["last_search_summary"] is None


def test_profile_overview_is_ordered_paginated_lightweight_and_aggregates_all_profiles(
    client,
    auth_headers,
    db_session,
    test_user,
):
    base_time = datetime(2026, 7, 1, tzinfo=timezone.utc)
    profiles = []
    for index in range(105):
        is_latest_success = index == 7
        profiles.append(
            SearchProfile(
                user_id=test_user.id,
                name=f"Profile {index:03}",
                role_description=f"Role {index}",
                location_filter="Zurich",
                schedule_enabled=index % 2 == 0,
                schedule_interval_hours=12,
                is_history=index % 3 == 0,
                advanced_preferences={
                    "preferred_languages": ["en", "de"],
                    "remote_only": True,
                    "salary_min_chf": 120_000,
                    "unlisted_large_value": "must-not-be-returned",
                },
                cv_content=f"PRIVATE_CV_{index}",
                cached_cv_summary=f"PRIVATE_CACHE_{index}",
                cached_queries={"private": f"QUERY_CACHE_{index}"},
                cached_profile_snapshot=f"PRIVATE_SNAPSHOT_{index}",
                profile_normalized_skills=[f"PRIVATE_NORMALIZED_{index}"],
                created_at=base_time + timedelta(minutes=index),
                search_run_count=3 if is_latest_success else 0,
                last_search_state="done" if is_latest_success else None,
                last_search_started_at=(
                    base_time + timedelta(days=2) if is_latest_success else None
                ),
                last_search_completed_at=(
                    base_time + timedelta(days=2, minutes=5) if is_latest_success else None
                ),
                last_search_summary=(
                    {
                        "schema_version": 1,
                        "started_at": "2026-07-03T00:00:00+00:00",
                        "finished_at": "2026-07-03T00:05:00+00:00",
                        "duration_ms": 300_000,
                        "counts": {"jobs_found": 17, "jobs_new": 4},
                        "providers": {
                            "status": "succeeded",
                            "successful_requests": 2,
                            "failed_requests": 0,
                            "queries_without_provider": 0,
                        },
                        "private": "PRIVATE_RECEIPT_VALUE",
                    }
                    if is_latest_success
                    else None
                ),
            )
        )

    other_user = User(
        username="overview-other",
        hashed_password=get_password_hash("Otherpass1"),
    )
    db_session.add(other_user)
    db_session.flush()
    db_session.add(
        SearchProfile(
            user_id=other_user.id,
            name="FOREIGN_PROFILE",
            created_at=base_time + timedelta(days=20),
            search_run_count=90,
            last_search_state="done",
            last_search_started_at=base_time + timedelta(days=20),
            last_search_completed_at=base_time + timedelta(days=20, minutes=1),
            last_search_summary={"counts": {"jobs_found": 9999}},
        )
    )
    db_session.add_all(profiles)
    db_session.commit()

    first = client.get(
        "/api/v1/profiles/overview?page=1&page_size=20",
        headers=auth_headers,
    )
    assert first.status_code == 200
    payload = first.json()
    assert payload["page"] == 1
    assert payload["page_size"] == 20
    assert payload["total_pages"] == 6
    assert payload["aggregate"]["total_profiles"] == 105
    assert payload["aggregate"]["total_successful_runs"] == 3
    assert payload["aggregate"]["latest_successful_jobs_found"] == 17
    assert payload["aggregate"]["latest_successful_completed_at"] is not None
    assert len(payload["items"]) == 20
    assert [item["name"] for item in payload["items"]] == [
        f"Profile {index:03}" for index in range(104, 84, -1)
    ]
    assert payload["items"][0]["preferred_languages"] == ["en", "de"]
    assert payload["items"][0]["remote_only"] is True
    assert payload["items"][0]["salary_min_chf"] == 120_000

    serialized = json.dumps(payload)
    for forbidden in (
        "cv_content",
        "cached_cv_summary",
        "cached_queries",
        "cached_profile_snapshot",
        "profile_normalized_skills",
        "PRIVATE_",
        "unlisted_large_value",
        "FOREIGN_PROFILE",
        "9999",
    ):
        assert forbidden not in serialized

    final_page = client.get(
        "/api/v1/profiles/overview?page=6&page_size=20",
        headers=auth_headers,
    )
    assert final_page.status_code == 200
    assert len(final_page.json()["items"]) == 5
    assert final_page.json()["aggregate"]["total_profiles"] == 105


def test_profile_overview_enforces_pagination_bounds(client, auth_headers):
    assert (
        client.get(
            "/api/v1/profiles/overview?page=0&page_size=20",
            headers=auth_headers,
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/profiles/overview?page=1&page_size=201",
            headers=auth_headers,
        ).status_code
        == 422
    )
