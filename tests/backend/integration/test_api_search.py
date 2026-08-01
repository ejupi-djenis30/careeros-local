import hashlib
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.services.search_status import release_task, reserve_task


def _career_vault_payload(*, expected_revision: int = 0, skill: str = "Python") -> dict:
    return {
        "expected_revision": expected_revision,
        "display_name": "Private Name",
        "headline": "Platform engineer",
        "summary": "Builds dependable local systems.",
        "email": "private@example.test",
        "phone": "+41 79 111 22 33",
        "birth_date": "1990-01-01",
        "nationality": "Swiss",
        "location": {"city": "Zurich", "country": "CH"},
        "preferences": {
            "target_roles": ["Staff Engineer"],
            "preferred_work_modes": ["hybrid"],
            "job_source_consents": {"job_room": True},
        },
        "facts": [
            {
                "fact_type": "skill",
                "position": 0,
                "verification_status": "confirmed",
                "payload": {"name": skill, "level": "advanced"},
            },
            {
                "fact_type": "achievement",
                "position": 1,
                "verification_status": "draft",
                "payload": {"title": "Unconfirmed claim", "description": "Do not use"},
            },
        ],
        "goals": [],
    }


def test_start_search_requires_ready_local_analysis(client, auth_headers: dict, test_profile):
    from backend.api.deps import require_local_analysis_ready
    from backend.inference.service import LocalModelReadiness
    from backend.main import app

    previous_override = app.dependency_overrides.pop(require_local_analysis_ready, None)
    unavailable = LocalModelReadiness(
        ready=False,
        runtime="ollama",
        configured_model="compact-local",
        error_code="local_runtime_unreachable",
        checks=[],
    )
    try:
        with patch(
            "backend.inference.service.check_local_model_readiness",
            new=AsyncMock(return_value=unavailable),
        ):
            response = client.post(
                "/api/v1/search/start",
                json={"id": test_profile["id"], "name": "Blocked search"},
                headers=auth_headers,
            )
    finally:
        if previous_override is not None:
            app.dependency_overrides[require_local_analysis_ready] = previous_override

    assert response.status_code == 428
    assert response.json()["detail"] == {
        "code": "local_model_required",
        "message": "A ready local model is required for analysis",
        "model_error_code": "local_runtime_unreachable",
    }


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


def test_new_search_defaults_to_career_vault_and_persists_private_snapshot_metadata(
    client, auth_headers: dict
):
    vault = client.put(
        "/api/v1/career-profile",
        json=_career_vault_payload(),
        headers=auth_headers,
    )
    assert vault.status_code == 200, vault.text
    confirmed_fact_id = vault.json()["facts"][0]["id"]

    with patch("backend.services.search_service.SearchService.run_search"):
        started = client.post(
            "/api/v1/search/start",
            json={"name": "Vault-backed search", "role_description": "Platform engineer"},
            headers=auth_headers,
        )
    assert started.status_code == 200, started.text
    start_body = started.json()
    assert start_body["profile_source"] == "career_vault"
    assert len(start_body["source_snapshot_sha256"]) == 64
    release_task(start_body["profile_id"])

    profiles = client.get("/api/v1/profiles/", headers=auth_headers)
    assert profiles.status_code == 200, profiles.text
    history = next(item for item in profiles.json() if item["id"] == start_body["profile_id"])
    snapshot = json.loads(history["cv_content"])
    assert history["profile_source"] == "career_vault"
    assert history["career_profile_id"] == vault.json()["id"]
    assert history["career_profile_revision"] == 1
    assert history["career_fact_ids"] == [confirmed_fact_id]
    assert history["source_snapshot_sha256"] == start_body["source_snapshot_sha256"]
    assert (
        hashlib.sha256(history["cv_content"].encode("utf-8")).hexdigest()
        == history["source_snapshot_sha256"]
    )
    assert [fact["id"] for fact in snapshot["facts"]] == [confirmed_fact_id]
    assert "private@example.test" not in history["cv_content"]
    assert "+41 79 111 22 33" not in history["cv_content"]
    assert "1990-01-01" not in history["cv_content"]
    assert "Swiss" not in history["cv_content"]
    assert "Unconfirmed claim" not in history["cv_content"]


def test_career_vault_search_rejects_missing_vault_or_confirmed_facts(client, auth_headers: dict):
    missing = client.post(
        "/api/v1/search/start",
        json={"name": "Missing Vault", "role_description": "Engineer"},
        headers=auth_headers,
    )
    assert missing.status_code == 422
    assert missing.json()["detail"] == "Career Vault search requires a saved Career Vault profile."

    payload = _career_vault_payload()
    payload["facts"][0]["verification_status"] = "draft"
    created = client.put("/api/v1/career-profile", json=payload, headers=auth_headers)
    assert created.status_code == 200, created.text
    unconfirmed = client.post(
        "/api/v1/search/start",
        json={
            "name": "Unconfirmed Vault",
            "role_description": "Engineer",
            "profile_source": "career_vault",
        },
        headers=auth_headers,
    )
    assert unconfirmed.status_code == 422
    assert "at least one confirmed" in unconfirmed.json()["detail"]


def test_uploaded_cv_remains_the_implicit_legacy_source(client, auth_headers: dict):
    cv_content = "Python and FastAPI delivery."
    with patch("backend.services.search_service.SearchService.run_search"):
        started = client.post(
            "/api/v1/search/start",
            json={
                "name": "Legacy upload",
                "role_description": "Backend engineer",
                "cv_content": cv_content,
            },
            headers=auth_headers,
        )
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["profile_source"] == "uploaded_cv"
    assert body["source_snapshot_sha256"] == hashlib.sha256(cv_content.encode("utf-8")).hexdigest()
    release_task(body["profile_id"])

    missing_upload = client.post(
        "/api/v1/search/start",
        json={
            "name": "Empty upload",
            "role_description": "Backend engineer",
            "profile_source": "uploaded_cv",
        },
        headers=auth_headers,
    )
    assert missing_upload.status_code == 422
    assert missing_upload.json()["detail"] == "Uploaded CV search requires non-empty cv_content."


def test_rerun_keeps_the_original_career_vault_snapshot(client, auth_headers: dict):
    created = client.put(
        "/api/v1/career-profile",
        json=_career_vault_payload(),
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text

    with patch("backend.services.search_service.SearchService.run_search"):
        initial = client.post(
            "/api/v1/search/start",
            json={
                "name": "Immutable campaign",
                "role_description": "Platform engineer",
                "profile_source": "career_vault",
            },
            headers=auth_headers,
        )
    assert initial.status_code == 200, initial.text
    initial_body = initial.json()
    release_task(initial_body["profile_id"])
    before = client.get("/api/v1/profiles/", headers=auth_headers).json()
    original = next(item for item in before if item["id"] == initial_body["profile_id"])

    update = _career_vault_payload(expected_revision=1, skill="Rust")
    update["facts"][0]["id"] = created.json()["facts"][0]["id"]
    update["facts"][1]["id"] = created.json()["facts"][1]["id"]
    changed = client.put("/api/v1/career-profile", json=update, headers=auth_headers)
    assert changed.status_code == 200, changed.text
    assert changed.json()["revision"] == 2

    with patch("backend.services.search_service.SearchService.run_search"):
        rerun = client.post(
            "/api/v1/search/start",
            json={
                "id": initial_body["profile_id"],
                "profile_source": "career_vault",
                "cv_content": "A caller must not replace the saved snapshot",
            },
            headers=auth_headers,
        )
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()["source_snapshot_sha256"] == initial_body["source_snapshot_sha256"]
    release_task(initial_body["profile_id"])

    after = client.get("/api/v1/profiles/", headers=auth_headers).json()
    persisted = next(item for item in after if item["id"] == initial_body["profile_id"])
    assert persisted["cv_content"] == original["cv_content"]
    assert persisted["career_profile_revision"] == 1
    assert persisted["career_fact_ids"] == original["career_fact_ids"]
    assert "Rust" not in persisted["cv_content"]
    assert "caller must not replace" not in persisted["cv_content"]


def test_start_search_is_rejected_before_provider_work_in_offline_mode(
    client, auth_headers: dict, test_profile
):
    with (
        patch("backend.api.routes.search.settings.OFFLINE_MODE", True),
        patch("backend.api.routes.search.reserve_task") as mock_reserve,
    ):
        response = client.post(
            "/api/v1/search/start",
            json={"id": test_profile["id"], "name": "Offline search"},
            headers=auth_headers,
        )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Live job-source access is disabled while offline mode is active"
    )
    mock_reserve.assert_not_called()


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
        mock_settings.OFFLINE_MODE = False

        response = client.post(
            "/api/v1/search/start",
            json={"id": profile_id, "name": "Blocked Search"},
            headers=auth_headers,
        )

    assert response.status_code == 429
    assert "Too many active searches" in response.json()["detail"]
