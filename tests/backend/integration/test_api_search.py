from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.services.search_status import release_task, reserve_task


class TestAdvancedSearchAPI:
    def test_get_search_status_all(self, client, auth_headers):
        response = client.get("/api/v1/search/status/all", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_upload_cv_unsupported_format(self, client, auth_headers):
        # Create a dummy image file which is unsupported
        files = {"file": ("image.png", b"dummy image content", "image/png")}
        response = client.post("/api/v1/search/upload-cv", headers=auth_headers, files=files)
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    def test_upload_cv_text_format(self, client, auth_headers):
        files = {
            "file": ("resume.txt", b"Here is my curriculum vitae: I am an engineer.", "text/plain")
        }
        response = client.post("/api/v1/search/upload-cv", headers=auth_headers, files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "resume.txt"
        assert "engineer" in data["text"]


@pytest.fixture
def test_profile(client, auth_headers):
    profile_data = {
        "name": "Search Test Profile",
        "role_description": "Dev",
        "search_strategy": "Aggressive",
    }
    response = client.post("/api/v1/profiles/", json=profile_data, headers=auth_headers)
    return response.json()


def test_start_search_authorized(client, auth_headers: dict, test_profile):
    profile_id = test_profile["id"]
    # Mock search service run_search
    with patch("backend.services.search_service.SearchService.run_search") as mock_run:
        response = client.post(
            "/api/v1/search/start",
            json={
                "id": profile_id,
                "name": "Test Search",
                "force_regenerate_cv_summary": True,
                "force_regenerate_queries": True,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert "profile_id" in response.json()
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs["force_regenerate_cv_summary"] is True
        assert kwargs["force_regenerate_queries"] is True


def test_start_search_accepts_large_numeric_values_without_clamping(
    client, auth_headers: dict, db_session
):
    from backend.models import SearchProfile

    payload = {
        "name": "Large Numeric Search",
        "role_description": "Backend Engineer",
        "cv_content": "FastAPI, PostgreSQL, Docker",
        "location_filter": "Zurich",
        "posted_within_days": 999999,
        "max_distance": 999999,
        "schedule_enabled": True,
        "schedule_interval_hours": 999999,
        "max_queries": 999999,
        "max_occupation_queries": 999999,
        "max_keyword_queries": 0,
    }

    with patch("backend.services.search_service.SearchService.run_search"):
        response = client.post("/api/v1/search/start", json=payload, headers=auth_headers)

    assert response.status_code == 200
    profile_id = response.json()["profile_id"]
    profile = db_session.get(SearchProfile, profile_id)
    assert profile is not None
    assert profile.posted_within_days == 999999
    assert profile.max_distance == 999999
    assert profile.schedule_interval_hours == 999999
    assert profile.max_queries == 999999
    assert profile.max_occupation_queries == 999999


def test_stop_search_authorized(client: TestClient, auth_headers: dict, test_profile):
    profile_id = test_profile["id"]
    response = client.post(f"/api/v1/search/stop/{profile_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Search stopped successfully"


def test_search_unauthorized_access(client, auth_headers, db_session):
    # 1. Create another user to satisfy foreign key constraints
    from backend.models import User
    from backend.services.auth import get_password_hash

    other_user = User(
        username="otheruser_" + str(datetime.now().timestamp()),  # Avoid collisions
        hashed_password=get_password_hash("OtherPass123!"),
    )
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    # 2. Create a profile belonging to that user
    from backend.models import SearchProfile

    other_profile = SearchProfile(
        user_id=other_user.id,
        name="Other User Profile",
        role_description="Hacker",
        cv_content="None",
    )
    db_session.add(other_profile)
    db_session.commit()

    # 2. Try to stop it with our current user
    response = client.post(f"/api/v1/search/stop/{other_profile.id}", headers=auth_headers)
    assert response.status_code == 403

    # 3. Try to start search with that ID
    payload = {"id": other_profile.id, "role_description": "New Role"}
    response = client.post("/api/v1/search/start", json=payload, headers=auth_headers)
    assert response.status_code == 403


def test_get_search_status(client: TestClient, auth_headers: dict, test_profile):
    profile_id = test_profile["id"]
    response = client.get(f"/api/v1/search/status/{profile_id}", headers=auth_headers)
    assert response.status_code == 200


def test_start_search_conflict_when_profile_already_reserved(
    client, auth_headers: dict, test_profile
):
    profile_id = test_profile["id"]
    assert reserve_task(profile_id) is True

    try:
        response = client.post(
            "/api/v1/search/start",
            json={"id": profile_id, "name": "Conflicting Search"},
            headers=auth_headers,
        )
    finally:
        release_task(profile_id)

    assert response.status_code == 409
    assert response.json()["detail"] == "A search is already running for this profile"


def test_start_search_rejects_when_user_has_too_many_active_searches(
    client, auth_headers: dict, test_profile
):
    profile_id = test_profile["id"]
    with (
        patch("backend.api.routes.search.get_all_statuses") as mock_statuses,
        patch("backend.api.routes.search.settings") as mock_settings,
    ):
        mock_statuses.return_value = {
            100: {"state": "searching"},
            101: {"state": "analyzing"},
        }
        mock_settings.MAX_CONCURRENT_SEARCHES_PER_USER = 2

        response = client.post(
            "/api/v1/search/start",
            json={"id": profile_id, "name": "Blocked Search"},
            headers=auth_headers,
        )

    assert response.status_code == 429
    assert "Too many active searches" in response.json()["detail"]
