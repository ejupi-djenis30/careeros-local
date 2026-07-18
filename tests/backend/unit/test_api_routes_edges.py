import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api.deps import get_current_user_id, get_db
from backend.main import app

client = TestClient(app)


# --- AUTH ROUTES ---
def test_auth_refresh_missing_token():
    client.cookies.clear()
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


def test_auth_refresh_invalid_token():
    client.cookies.clear()
    client.cookies.set(
        "careeros_refresh_token", "invalid", domain="testserver.local", path="/"
    )
    with patch("backend.api.routes.auth.decode_refresh_token", return_value=None):
        response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert "Invalid refresh token" in response.json()["detail"]


def test_auth_refresh_user_vanished():
    client.cookies.clear()
    client.cookies.set(
        "careeros_refresh_token", "valid", domain="testserver.local", path="/"
    )
    with (
        patch("backend.api.routes.auth.decode_refresh_token", return_value={"sub": "testuser"}),
        patch("backend.api.routes.auth.get_db"),
    ):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        app.dependency_overrides[get_db] = lambda: mock_session
        try:
            response = client.post("/api/v1/auth/refresh")
            assert response.status_code == 401
            assert "User vanished" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()


def test_auth_logout():
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully"


def test_auth_deps_invalid_decode():
    from fastapi import HTTPException

    from backend.api.deps import get_current_user_id

    with patch("backend.api.deps.decode_access_token", side_effect=Exception):
        with pytest.raises(HTTPException) as exc:
            get_current_user_id("token", MagicMock())
        assert exc.value.status_code == 401


def test_auth_deps_none_payload():
    from fastapi import HTTPException

    from backend.api.deps import get_current_user_id

    with patch("backend.api.deps.decode_access_token", return_value=None):
        with pytest.raises(HTTPException):
            get_current_user_id("token", MagicMock())


def test_auth_deps_missing_sub():
    from fastapi import HTTPException

    from backend.api.deps import get_current_user_id

    with patch("backend.api.deps.decode_access_token", return_value={}):
        with pytest.raises(HTTPException):
            get_current_user_id("token", MagicMock())


def test_auth_deps_user_not_found():
    from fastapi import HTTPException

    from backend.api.deps import get_current_user_id

    with patch("backend.api.deps.decode_access_token", return_value={"sub": "user"}):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(HTTPException):
            get_current_user_id("token", mock_db)


# --- PROFILES ROUTE ---
def test_profiles_update():
    from backend.api.deps import get_current_user_id, get_db, profile_service_dep

    app.dependency_overrides[get_current_user_id] = lambda: 1
    app.dependency_overrides[get_db] = lambda: MagicMock()
    mock_service = MagicMock()
    mock_service.update_profile.return_value = {
        "id": 1,
        "name": "updated",
        "role_description": "test",
        "location_filter": "test",
        "created_at": "2024-01-01T00:00:00",
    }
    app.dependency_overrides[profile_service_dep] = lambda: mock_service
    try:
        response = client.patch(
            "/api/v1/profiles/1", json={"name": "updated", "role_description": "test"}
        )
        assert response.status_code == 200
        mock_service.update_profile.assert_called_once()
    finally:
        app.dependency_overrides.clear()


# --- JOBS ROUTE ---
def test_jobs_delete():
    from backend.api.deps import get_current_user_id, get_db, job_service_dep

    app.dependency_overrides[get_current_user_id] = lambda: 1
    app.dependency_overrides[get_db] = lambda: MagicMock()
    mock_service = MagicMock()
    app.dependency_overrides[job_service_dep] = lambda: mock_service
    try:
        response = client.delete("/api/v1/jobs/1")
        assert response.status_code == 204
        mock_service.delete_job.assert_called_once_with(1, 1)
    finally:
        app.dependency_overrides.clear()


# --- SEARCH ROUTE ---
def test_search_upload_file_too_large():
    app.dependency_overrides[get_current_user_id] = lambda: 1

    # Create a dummy file object that looks large
    # FastAPI UploadFile relies on actual content length if injected natively,
    # but since this relies on standard POST we need to mock the file size check directly
    with patch("backend.api.routes.search.extract_text_from_file"):
        large_file = io.BytesIO(b"A" * (11 * 1024 * 1024))  # 11MB
        response = client.post(
            "/api/v1/search/upload-cv", files={"file": ("test.pdf", large_file, "application/pdf")}
        )
        assert response.status_code == 400
        assert "File too large" in response.json()["detail"]
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_search_start_with_empty_fields_and_default_name():
    from backend.api.routes.search import start_search

    mock_repo = MagicMock()
    mock_repo.create.return_value = MagicMock(id=1)

    class FakeRequest:
        id = None
        max_queries = ""
        posted_within_days = ""
        max_distance = ""
        schedule_interval_hours = ""
        name = "Default Profile"
        role_description = "dev"
        location_filter = "zurich"
        search_strategy = "broad"
        force_regenerate_cv_summary = False
        force_regenerate_queries = False

        def model_dump(self, exclude_unset=True):
            return {
                "name": self.name,
                "role_description": self.role_description,
                "location_filter": self.location_filter,
                "search_strategy": self.search_strategy,
                "max_queries": "",
                "posted_within_days": "",
                "max_distance": "",
                "schedule_interval_hours": "",
                "force_regenerate_cv_summary": False,
                "force_regenerate_queries": False,
            }

    with (
        patch("backend.api.routes.search.ProfileRepository", return_value=mock_repo),
        patch("backend.api.routes.search.cancel_task"),
        patch("backend.api.routes.search.reserve_task", return_value="token-1"),
    ):
        req = FakeRequest()
        bg_tasks = MagicMock()
        mock_db = MagicMock()
        mock_request = MagicMock()

        res = await start_search(mock_request, req, bg_tasks, mock_db, user_id=1)

        create_args = mock_repo.create.call_args[0][0]
        assert create_args["max_distance"] is None
        assert "Search " in create_args["name"]
        assert res["message"] == "Search started"


def test_search_status_not_found():
    app.dependency_overrides[get_current_user_id] = lambda: 1
    from backend.db.base import get_db

    mock_session = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_session

    with patch("backend.api.routes.search.ProfileRepository") as mock_repo_class:
        mock_repo = MagicMock()
        # Profile not found or wrong user
        mock_profile = MagicMock()
        mock_profile.user_id = 999
        mock_repo.get.return_value = mock_profile
        mock_repo_class.return_value = mock_repo

        response = client.get("/api/v1/search/status/1")
        assert response.status_code == 404
        assert "Profile not found or unauthorized" in response.json()["detail"]

    app.dependency_overrides.clear()
