from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.core.exceptions import CoreException
from backend.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_health():
    with (
        patch("backend.db.base.SessionLocal") as mock_session,
        patch("backend.main._check_migration_status", return_value="current"),
    ):
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"
        assert data["storage"] == "writable"
        assert data["migrations"] == "current"


def test_health_returns_503_when_database_unavailable():
    with patch("backend.main._check_db_status", return_value="unavailable"):
        response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_health_live_ignores_database_state():
    with patch("backend.main._check_db_status", return_value="unavailable"):
        response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_checks_database_and_storage_independently():
    with (
        patch("backend.main._check_db_status", return_value="connected"),
        patch("backend.main._check_storage_status", return_value="unavailable"),
        patch("backend.main._check_migration_status", return_value="current"),
    ):
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "database": "connected",
        "storage": "unavailable",
        "migrations": "current",
    }


def test_readiness_rejects_an_outdated_schema():
    with (
        patch("backend.main._check_db_status", return_value="connected"),
        patch("backend.main._check_storage_status", return_value="writable"),
        patch("backend.main._check_migration_status", return_value="outdated"),
    ):
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["migrations"] == "outdated"


def test_migration_status_handles_probe_failure():
    from backend.main import _check_migration_status

    with patch("backend.db.base.engine.connect", side_effect=RuntimeError("cannot connect")):
        assert _check_migration_status() == "unavailable"


def test_model_health_is_non_blocking_when_runtime_is_unavailable():
    from backend.inference.service import LocalModelStatus

    status = LocalModelStatus(
        available=False,
        ready=False,
        endpoint="http://127.0.0.1:11434",
        configured_model="qwen3:4b",
        installed_models=[],
        error_code="local_runtime_unreachable",
    )
    with patch("backend.inference.service.get_local_model_status", return_value=status):
        response = client.get("/api/v1/health/model")
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["ready"] is False


def test_check_db_status_handles_session_creation_failure():
    from backend.main import _check_db_status

    with patch("backend.db.base.SessionLocal", side_effect=RuntimeError("cannot connect")):
        assert _check_db_status() == "unavailable"


def test_root_db_success():
    with patch("backend.db.base.SessionLocal") as mock_session:
        # Mock successful execute
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["database"] == "connected"


def test_root_db_failure():
    with patch("backend.db.base.SessionLocal") as mock_session:
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("DB Error")
        mock_session.return_value = mock_db
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["database"] == "unavailable"


def test_404_handler():
    response = client.get("/nonexistent/endpoint/123")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_validation_handler():
    # Trigger 422 using an unprotected route missing fields
    response = client.post("/api/v1/auth/register", json={})
    assert response.status_code == 422
    assert "Validation Error" in response.json()["message"]


@app.get("/test-core-exception")
def raise_core_exception():
    raise CoreException("Test core exception")


@app.get("/test-generic-exception")
def raise_generic_exception():
    raise Exception("Test generic exception")


def test_core_exception_handler():
    response = client.get("/test-core-exception")
    assert response.status_code == 400
    assert response.json()["message"] == "Application Error"


def test_generic_exception_handler():
    response = client.get("/test-generic-exception")
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal Server Error"


def test_lifespan():
    import asyncio
    from unittest.mock import patch

    from backend.main import lifespan

    with (
        patch("backend.services.scheduler.start_scheduler") as mock_start,
        patch("backend.services.scheduler.stop_scheduler") as mock_stop,
    ):

        async def run_lifespan():
            # Use async context manager protocol
            ctx = lifespan(app)
            await ctx.__aenter__()
            mock_start.assert_called_once()
            await ctx.__aexit__(None, None, None)
            mock_stop.assert_called_once()

        asyncio.run(run_lifespan())


def test_cors_empty():
    import importlib
    from unittest.mock import PropertyMock, patch

    import backend.main

    with patch(
        "backend.core.config.Settings.cors_origins_list", new_callable=PropertyMock
    ) as mock_cors:
        mock_cors.return_value = []
        # Reloading module with patched settings hits line 78
        try:
            importlib.reload(backend.main)
        finally:
            # Restore it so other tests don't break if dependent on cors_origins
            importlib.reload(backend.main)
