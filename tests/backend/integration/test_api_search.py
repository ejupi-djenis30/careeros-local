import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

class TestAdvancedSearchAPI:
    def test_get_search_status_all(self, client, auth_headers):
        response = client.get("/api/v1/search/status/all", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_upload_cv_unsupported_format(self, client, auth_headers):
        # Create a dummy image file which is unsupported
        files = {
            "file": ("image.png", b"dummy image content", "image/png")
        }
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
        "search_strategy": "Aggressive"
    }
    response = client.post("/api/v1/profiles/", json=profile_data, headers=auth_headers)
    return response.json()

def test_start_search_authorized(client, auth_headers: dict, test_profile):
    profile_id = test_profile["id"]
    # Mock search service run_search
    with patch("backend.services.search_service.SearchService.run_search") as mock_run:
        response = client.post(
            "/api/v1/search/start",
            json={"id": profile_id, "name": "Test Search"},
            headers=auth_headers
        )
        assert response.status_code == 200
        assert "profile_id" in response.json()

def test_stop_search_authorized(client: TestClient, auth_headers: dict, test_profile):
    profile_id = test_profile["id"]
    response = client.post(f"/api/v1/search/stop/{profile_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Search stopped successfully"

def test_search_unauthorized_access(client, auth_headers, db_session):
    # 1. Create a profile belonging to another user (we only have one test user in conftest)
    # We can just manually insert a profile with a different user_id
    from backend.models import SearchProfile
    other_profile = SearchProfile(
        user_id=999,
        name="Other User Profile",
        role_description="Hacker",
        cv_content="None"
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
