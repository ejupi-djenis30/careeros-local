from unittest.mock import AsyncMock, patch


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
