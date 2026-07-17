from unittest.mock import AsyncMock, patch

from backend.inference.service import LocalModelStatus


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
