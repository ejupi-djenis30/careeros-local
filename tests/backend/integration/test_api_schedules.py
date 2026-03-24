import pytest
from fastapi.testclient import TestClient

def test_schedules_api(client: TestClient, auth_headers: dict):
    # 1. Get scheduler status
    response = client.get("/api/v1/schedules/status", headers=auth_headers)
    assert response.status_code == 200
    assert "running" in response.json()

    # 2. List schedules (should be allowed even if empty)
    response = client.get("/api/v1/schedules/", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
