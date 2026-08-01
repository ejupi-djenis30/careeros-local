from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.core.exceptions import CoreException
from backend.main import _api_documentation_urls, app

client = TestClient(app, raise_server_exceptions=False)


def test_api_documentation_is_local_development_only():
    assert _api_documentation_urls("production", "/api/v1") == (None, None, None)
    assert _api_documentation_urls("development", "/api/v1") == (
        "/api/v1/openapi.json",
        "/docs",
        "/redoc",
    )
    assert _api_documentation_urls("test", "/api/v1") == (
        "/api/v1/openapi.json",
        "/docs",
        "/redoc",
    )
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/api/v1/openapi.json").status_code == 200


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


def test_readiness_fails_fast_without_db_checks_during_vault_maintenance():
    class MaintenanceGate:
        @asynccontextmanager
        async def try_reader(self):
            yield False

    with (
        patch("backend.main.vault_activity_gate", MaintenanceGate()),
        patch(
            "backend.main._check_db_status",
            side_effect=AssertionError("readiness must not enter the database"),
        ),
    ):
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "maintenance",
        "code": "vault_maintenance_pending",
        "database": "not_checked",
        "storage": "not_checked",
        "migrations": "not_checked",
    }


def test_api_security_headers_disable_unused_browser_capabilities():
    response = client.get("/api/v1/health/live")

    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-xss-protection"] == "0"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == (
        "camera=(), microphone=(), geolocation=(), display-capture=(), payment=(), usb=()"
    )


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


def test_root_is_static_and_never_touches_database():
    with patch("backend.db.base.SessionLocal", side_effect=AssertionError("database probe")):
        response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "message": "CareerOS Local API",
        "status": "online",
    }


def test_404_handler():
    response = client.get("/nonexistent/endpoint/123")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_validation_handler(caplog):
    # Trigger 422 using an unprotected route missing fields
    response = client.post("/api/v1/auth/register", json={})
    assert response.status_code == 422
    assert "Validation Error" in response.json()["message"]
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert "/api/v1/auth/register" not in caplog.text


@app.get("/test-core-exception")
def raise_core_exception():
    raise CoreException("Test core exception")


@app.get("/test-generic-exception")
def raise_generic_exception():
    raise Exception("Test generic exception")


@app.get("/api/v1/automation/grants/test-generic-exception")
def raise_private_generic_exception():
    raise Exception("Private test exception")


@app.get("/api/v1/test-large-private-response")
def return_large_private_response():
    return {"private_payload": "x" * 4096}


@app.get("/test-http-exception-headers")
def raise_http_exception_with_headers():
    raise HTTPException(
        status_code=403,
        detail="Denied",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "WWW-Authenticate": "Bearer",
        },
    )


def test_core_exception_handler():
    response = client.get("/test-core-exception")
    assert response.status_code == 400
    assert response.json()["message"] == "Application Error"


def test_generic_exception_handler():
    response = client.get("/test-generic-exception")
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal Server Error"


def test_api_generic_exception_handler_forces_no_store_headers():
    response = client.get("/api/v1/automation/grants/test-generic-exception")

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal Server Error"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"


def test_large_api_response_is_never_dynamically_compressed():
    response = client.get(
        "/api/v1/test-large-private-response",
        headers={"Accept-Encoding": "gzip"},
    )

    assert response.status_code == 200
    assert len(response.content) > 1000
    assert "content-encoding" not in response.headers


def test_http_exception_handler_preserves_security_headers():
    response = client.get("/test-http-exception-headers")

    assert response.status_code == 403
    assert response.json() == {"detail": "Denied"}
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["www-authenticate"] == "Bearer"


def test_lifespan():
    import asyncio
    from unittest.mock import patch

    from backend.main import lifespan

    shutdown_order = []
    with (
        patch("backend.services.scheduler.start_scheduler") as mock_start,
        patch(
            "backend.services.scheduler.stop_scheduler",
            side_effect=lambda: shutdown_order.append("scheduler_stopped"),
        ) as mock_stop,
        patch(
            "backend.services.search_status.get_all_active_tasks",
            side_effect=lambda: shutdown_order.append("tasks_snapshotted") or {},
        ),
    ):

        async def run_lifespan():
            # Use async context manager protocol
            ctx = lifespan(app)
            await ctx.__aenter__()
            mock_start.assert_called_once()
            await ctx.__aexit__(None, None, None)
            mock_stop.assert_called_once()
            assert shutdown_order == ["scheduler_stopped", "tasks_snapshotted"]

        asyncio.run(run_lifespan())


def test_lifespan_runs_shutdown_cleanup_when_context_body_fails():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import patch

    import pytest

    from backend.main import lifespan

    order = []

    async def run_lifespan():
        with (
            patch("backend.main.desktop_runtime", SimpleNamespace(enabled=False)),
            patch("backend.services.scheduler.start_scheduler"),
            patch(
                "backend.services.scheduler.stop_scheduler",
                side_effect=lambda: order.append("scheduler_stopped"),
            ),
            patch(
                "backend.services.search_status.get_all_active_tasks",
                side_effect=lambda: order.append("tasks_snapshotted") or {},
            ),
            patch(
                "backend.inference.managed_runtime.stop_managed_runtime",
                side_effect=lambda: order.append("runtime_stopped"),
            ),
        ):
            with pytest.raises(RuntimeError, match="lifespan body failed"):
                async with lifespan(app):
                    raise RuntimeError("lifespan body failed")

    asyncio.run(run_lifespan())

    assert order == ["scheduler_stopped", "tasks_snapshotted", "runtime_stopped"]


def test_lifespan_observes_status_failure_without_blocking_shutdown(caplog):
    import asyncio
    import logging
    from types import SimpleNamespace
    from unittest.mock import patch

    from backend.main import lifespan

    private_marker = "PRIVATE-SHUTDOWN-STATUS-DETAIL"
    caplog.set_level(logging.WARNING, logger="backend.main")

    async def run_lifespan():
        active_task = asyncio.create_task(asyncio.Event().wait())
        with (
            patch("backend.main.desktop_runtime", SimpleNamespace(enabled=False)),
            patch("backend.services.scheduler.start_scheduler"),
            patch("backend.services.scheduler.stop_scheduler"),
            patch(
                "backend.services.search_status.get_all_active_tasks",
                return_value={17: active_task},
            ),
            patch(
                "backend.services.search_status.update_status",
                side_effect=RuntimeError(private_marker),
            ),
            patch("backend.inference.managed_runtime.stop_managed_runtime") as mock_stop_runtime,
        ):
            async with lifespan(app):
                pass

        assert active_task.cancelled()
        mock_stop_runtime.assert_called_once()

    asyncio.run(run_lifespan())

    assert "code=server_shutdown" in caplog.text
    assert "exception_type=RuntimeError" in caplog.text
    assert private_marker not in caplog.text


def test_lifespan_interrupts_managed_runtime_start_before_joining_it():
    import asyncio
    import threading
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from backend.main import lifespan

    order = []
    start_entered = threading.Event()
    allow_start_return = threading.Event()
    manager = MagicMock()
    manager.snapshot.return_value = SimpleNamespace(
        runtime_installed=True,
        model_installed=True,
    )

    def blocked_start(*, cancelled):
        order.append("runtime_start_entered")
        start_entered.set()
        assert allow_start_return.wait(timeout=2)
        assert cancelled.is_set()
        order.append("runtime_start_cancelled")

    async def quiesce_installer():
        order.append("installer_quiesced")
        allow_start_return.set()

    manager.start.side_effect = blocked_start
    manager.cancel_startup.side_effect = lambda event: (
        order.append("runtime_start_cancel_requested"),
        event.set(),
    )
    manager.stop.side_effect = lambda: order.append("runtime_stop_requested")

    with (
        patch("backend.main.desktop_runtime", SimpleNamespace(enabled=True)),
        patch("backend.services.scheduler.start_scheduler"),
        patch("backend.services.scheduler.stop_scheduler"),
        patch("backend.services.search_status.get_all_active_tasks", return_value={}),
        patch("backend.inference.managed_runtime.get_managed_runtime", return_value=manager),
        patch(
            "backend.inference.managed_runtime.stop_managed_runtime",
            side_effect=lambda: order.append("runtime_stopped_final"),
        ),
        patch(
            "backend.inference.managed_runtime.quiesce_managed_runtime_installation",
            side_effect=quiesce_installer,
        ),
    ):

        async def run_lifespan():
            async with lifespan(app):
                assert await asyncio.to_thread(start_entered.wait, 1)

        asyncio.run(run_lifespan())

    assert order == [
        "runtime_start_entered",
        "runtime_start_cancel_requested",
        "runtime_stop_requested",
        "installer_quiesced",
        "runtime_start_cancelled",
        "runtime_stopped_final",
    ]


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
