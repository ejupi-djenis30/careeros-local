import pytest
from fastapi.testclient import TestClient
from backend.main import app
from unittest.mock import patch, MagicMock
from backend.core.exceptions import CoreException

client = TestClient(app, raise_server_exceptions=False)

def test_health():
    with patch("backend.db.base.SessionLocal") as mock_session:
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"

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
    from backend.main import lifespan
    import asyncio
    from unittest.mock import patch, PropertyMock
    with patch("backend.services.scheduler.start_scheduler") as mock_start, \
         patch("backend.services.scheduler.stop_scheduler") as mock_stop:
        
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
    import backend.main
    from backend.core.config import Settings
    from unittest.mock import patch, PropertyMock
    
    with patch("backend.core.config.Settings.cors_origins_list", new_callable=PropertyMock) as mock_cors:
        mock_cors.return_value = []
        # Reloading module with patched settings hits line 78
        try:
           importlib.reload(backend.main)
        finally:
           # Restore it so other tests don't break if dependent on cors_origins
           importlib.reload(backend.main)
