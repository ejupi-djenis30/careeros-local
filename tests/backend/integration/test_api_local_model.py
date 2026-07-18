from unittest.mock import AsyncMock, patch

from backend.inference.service import (
    LocalModelStatus,
    ManagedModelStatus,
    ModelRemovalResult,
)


def test_local_model_status_endpoint_is_non_blocking(client):
    payload = LocalModelStatus(
        available=False,
        ready=False,
        endpoint="http://127.0.0.1:11434",
        configured_model="qwen3:4b",
        installed_models=[],
        error_code="local_runtime_unreachable",
    )
    with patch(
        "backend.api.routes.local_model.get_local_model_status",
        new=AsyncMock(return_value=payload),
    ):
        response = client.get("/api/v1/local-model/status")

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_local_model_pause_resume_and_remove_endpoints(client, auth_headers):
    paused = ManagedModelStatus(phase="paused", model_key="compact")
    resumed = ManagedModelStatus(phase="downloading_model", model_key="compact")
    removed = ModelRemovalResult(
        model_files=2,
        model_bytes=4096,
        status=ManagedModelStatus(phase="idle"),
    )
    with (
        patch(
            "backend.api.routes.local_model.pause_managed_model_install",
            return_value=paused,
        ),
        patch(
            "backend.api.routes.local_model.resume_managed_model_install",
            new=AsyncMock(return_value=resumed),
        ),
        patch(
            "backend.api.routes.local_model.remove_managed_model",
            new=AsyncMock(return_value=removed),
        ),
    ):
        pause_response = client.post("/api/v1/local-model/pause", headers=auth_headers)
        resume_response = client.post("/api/v1/local-model/resume", headers=auth_headers)
        remove_response = client.delete("/api/v1/local-model", headers=auth_headers)

    assert pause_response.status_code == 200
    assert pause_response.json()["phase"] == "paused"
    assert resume_response.status_code == 200
    assert resume_response.json()["phase"] == "downloading_model"
    assert remove_response.status_code == 200
    assert remove_response.json()["model_files"] == 2
