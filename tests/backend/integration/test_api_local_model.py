from unittest.mock import AsyncMock, patch

from backend.inference.service import (
    LocalModelReadiness,
    LocalModelReadinessCheck,
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
    assert response.json()["analysis_required"] is True
    assert response.json()["privacy_boundary"] == "local-only"


def test_authenticated_readiness_endpoint_returns_stable_diagnostics(client, auth_headers):
    payload = LocalModelReadiness(
        ready=True,
        runtime="llama.cpp",
        configured_model="compact",
        model_id="llama.cpp/compact",
        checks=[
            LocalModelReadinessCheck(code="endpoint_allowed", status="passed"),
            LocalModelReadinessCheck(code="runtime_reachable", status="passed"),
            LocalModelReadinessCheck(code="model_available", status="passed"),
            LocalModelReadinessCheck(code="structured_output", status="passed"),
        ],
    )
    with patch(
        "backend.api.routes.local_model.check_local_model_readiness",
        new=AsyncMock(return_value=payload),
    ):
        response = client.post("/api/v1/local-model/readiness", headers=auth_headers, json={})

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["model_id"] == "llama.cpp/compact"
    assert [item["code"] for item in response.json()["checks"]] == [
        "endpoint_allowed",
        "runtime_reachable",
        "model_available",
        "structured_output",
    ]


def test_readiness_endpoint_requires_authentication(client):
    response = client.post("/api/v1/local-model/readiness", json={})
    assert response.status_code == 401


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
