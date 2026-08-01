import asyncio
import logging
import os
import tempfile
import threading
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.api import api_router
from backend.api.deps import limiter
from backend.api.middleware import (
    PRIVATE_NO_STORE_HEADERS,
    CanonicalTrustedHostMiddleware,
    PrivatePathNoStoreMiddleware,
    RequestBodyLimitMiddleware,
    VaultActivityMiddleware,
    is_private_path,
)
from backend.career.activity import vault_activity_gate
from backend.core.config import settings
from backend.core.diagnostics import (
    FailureCode,
    diagnose_failure,
    log_failure,
    public_status_message,
)
from backend.core.exceptions import CoreException
from backend.core.logging import configure_logging
from backend.desktop.settings import DesktopRuntimeSettings

# ─── Logging ───
configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)
desktop_runtime = DesktopRuntimeSettings.from_environment()
PRIVATE_API_PREFIX = settings.API_V1_STR


def _api_documentation_urls(
    environment: Literal["development", "test", "production"],
    api_v1_prefix: str,
) -> tuple[str | None, str | None, str | None]:
    """Expose local developer docs without shipping CDN-backed production pages."""
    if environment == "production":
        return None, None, None
    return f"{api_v1_prefix}/openapi.json", "/docs", "/redoc"


# ─── Lifespan ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    # Startup: create DB tables
    # Moved to backend/pre_start.py to avoid race conditions with multiple workers

    # Startup: no request can race this single-worker cleanup. Remove only
    # atomic-write temporaries in the app-owned asset/resume namespaces.
    from backend.storage.atomic import cleanup_stale_atomic_writes

    cleanup_stale_atomic_writes()

    # Reconcile files whose process stopped between durable publication and the
    # authoritative CareerAsset commit. This runs before requests or scheduled
    # work can race the SQLite writer reservation.
    from backend.career.asset_publication import begin_asset_publication_write
    from backend.db.base import SessionLocal

    with SessionLocal() as recovery_db:
        begin_asset_publication_write(recovery_db)
        recovery_db.rollback()

    # Startup: start scheduler
    from backend.services.scheduler import start_scheduler, stop_scheduler

    start_scheduler()

    managed_start_task: asyncio.Task[None] | None = None
    managed_start_cancelled: threading.Event | None = None
    manager = None
    if desktop_runtime.enabled:
        from backend.inference.managed_runtime import (
            RuntimeStartCancelled,
            get_managed_runtime,
        )

        runtime_manager = get_managed_runtime()
        manager = runtime_manager
        snapshot = runtime_manager.snapshot()
        if snapshot.runtime_installed and snapshot.model_installed:
            start_cancelled = threading.Event()
            managed_start_cancelled = start_cancelled

            async def start_managed_runtime() -> None:
                try:
                    await asyncio.to_thread(
                        runtime_manager.start,
                        cancelled=start_cancelled,
                    )
                except RuntimeStartCancelled:
                    return
                except Exception as exc:
                    diagnostic = diagnose_failure(
                        exc,
                        FailureCode.RUNTIME_POLICY_FALLBACK,
                    )
                    log_failure(logger, diagnostic, level=logging.WARNING)

            managed_start_task = asyncio.create_task(start_managed_runtime())

    try:
        yield
    finally:
        shutdown_cancelled = False

        # Stop new scheduled work before snapshotting and joining in-flight tasks.
        try:
            stop_scheduler()
        except Exception as exc:
            diagnostic = diagnose_failure(exc, FailureCode.SERVER_SHUTDOWN)
            log_failure(logger, diagnostic, level=logging.WARNING)

        # Shutdown: cancel in-flight search tasks after every producer is stopped.
        from backend.services.search_status import get_all_active_tasks, update_status

        try:
            active = get_all_active_tasks()
        except Exception as exc:
            diagnostic = diagnose_failure(exc, FailureCode.SERVER_SHUTDOWN)
            log_failure(logger, diagnostic, level=logging.WARNING)
            active = {}
        if active:
            logger.info("Graceful shutdown: cancelling %d active search task(s)…", len(active))
            for pid, task in active.items():
                try:
                    if not task.done():
                        task.cancel()
                        update_status(
                            pid,
                            state="error",
                            terminal_reason="server_shutdown",
                            error=public_status_message(FailureCode.SERVER_SHUTDOWN),
                        )
                except Exception as exc:
                    diagnostic = diagnose_failure(exc, FailureCode.SERVER_SHUTDOWN)
                    log_failure(logger, diagnostic, level=logging.WARNING)
            # Give tasks a moment to handle CancelledError and run their finally blocks.
            try:
                await asyncio.gather(*active.values(), return_exceptions=True)
            except asyncio.CancelledError:
                shutdown_cancelled = True

        from backend.inference.managed_runtime import (
            quiesce_managed_runtime_installation,
            stop_managed_runtime,
        )

        if manager is not None:
            if managed_start_cancelled is not None:
                try:
                    manager.cancel_startup(managed_start_cancelled)
                except Exception as exc:
                    diagnostic = diagnose_failure(exc, FailureCode.SERVER_SHUTDOWN)
                    log_failure(logger, diagnostic, level=logging.WARNING)
            # Interrupt a health wait before joining it, and prevent a start that is
            # still hashing assets from spawning after shutdown begins.
            try:
                manager.stop()
            except Exception as exc:
                diagnostic = diagnose_failure(exc, FailureCode.SERVER_SHUTDOWN)
                log_failure(logger, diagnostic, level=logging.WARNING)
            try:
                await quiesce_managed_runtime_installation()
            except asyncio.CancelledError:
                shutdown_cancelled = True
            except Exception as exc:
                diagnostic = diagnose_failure(exc, FailureCode.SERVER_SHUTDOWN)
                log_failure(logger, diagnostic, level=logging.WARNING)
        if managed_start_task is not None:
            while not managed_start_task.done():
                try:
                    await asyncio.shield(managed_start_task)
                except asyncio.CancelledError:
                    current = asyncio.current_task()
                    shutdown_cancelled = (
                        shutdown_cancelled or current is not None and current.cancelling() > 0
                    )
            await asyncio.gather(managed_start_task, return_exceptions=True)
        try:
            stop_managed_runtime()
        except Exception as exc:
            diagnostic = diagnose_failure(exc, FailureCode.SERVER_SHUTDOWN)
            log_failure(logger, diagnostic, level=logging.WARNING)
        if shutdown_cancelled:
            raise asyncio.CancelledError


# ─── App ───
openapi_url, docs_url, redoc_url = _api_documentation_urls(
    settings.ENVIRONMENT,
    settings.API_V1_STR,
)
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=openapi_url,
    docs_url=docs_url,
    redoc_url=redoc_url,
    lifespan=lifespan,
)


def rate_limit_exception_handler(request: Request, exc: Exception) -> Response:
    """Adapt SlowAPI's narrow handler to Starlette's exception-handler protocol."""
    if not isinstance(exc, RateLimitExceeded):
        raise exc
    return _rate_limit_exceeded_handler(request, exc)


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # Disable obsolete browser XSS auditors; CSP and output encoding provide
    # the modern boundary without legacy filter-induced content rewriting.
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), display-capture=(), payment=(), usb=()"
    )
    return response


# ─── Basic Production Middlewares ───
# Do not dynamically compress API responses. Authenticated payloads can contain
# attacker-influenced and secret values, so a global compressor would create a
# BREACH-style length oracle. The distribution proxy compresses fingerprinted
# public assets instead.
app.add_middleware(CanonicalTrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_bytes=settings.HTTP_REQUEST_BODY_MAX_BYTES,
    route_max_bytes={
        ("POST", f"{settings.API_V1_STR}/portability/inspect"): (
            settings.PORTABLE_ARCHIVE_REQUEST_BODY_MAX_BYTES
        ),
        ("POST", f"{settings.API_V1_STR}/portability/restore"): (
            settings.PORTABLE_ARCHIVE_REQUEST_BODY_MAX_BYTES
        ),
    },
)

# ─── CORS ───
if settings.cors_origins_list:
    logger.info("Configuring CORS origin_count=%d", len(settings.cors_origins_list))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.cors_origins_list],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Content-SHA256"],
    )
else:
    logger.warning("CORS_ORIGINS is empty — CORS middleware not added!")

if desktop_runtime.enabled:
    from backend.desktop.session import DesktopSessionMiddleware

    app.add_middleware(
        DesktopSessionMiddleware,
        token=desktop_runtime.session_token,
    )

app.add_middleware(
    VaultActivityMiddleware,
    path_prefix=PRIVATE_API_PREFIX,
    gate=vault_activity_gate,
)

# This must be registered last so every API response, including TrustedHost,
# CORS and DesktopSession early exits, is private even without the Nginx proxy.
app.add_middleware(
    PrivatePathNoStoreMiddleware,
    path_prefix=PRIVATE_API_PREFIX,
)


# ─── Exception Handlers ───
def _cors_headers_for(request) -> dict:
    """Return CORS headers for the request origin, if it is an allowed origin.
    Exception handlers bypass CORSMiddleware, so we must add headers manually."""
    origin = request.headers.get("origin", "")
    if not origin or not settings.cors_origins_list:
        return {}
    allowed = [str(o) for o in settings.cors_origins_list]
    if origin in allowed:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        }
    return {}


def _exception_headers_for(request, extra: dict | None = None) -> dict:
    """Preserve CORS/explicit headers and force private responses to be non-cacheable."""
    headers = {
        **_cors_headers_for(request),
        **(extra or {}),
    }
    if is_private_path(request.url.path, path_prefix=PRIVATE_API_PREFIX):
        headers.update(PRIVATE_NO_STORE_HEADERS)
    return headers


def _public_validation_errors(errors: list[dict]) -> list[dict]:
    """Keep useful validation detail without serializing raw inputs or contexts."""
    public_errors = []
    for item in errors:
        error_type = str(item.get("type", "value_error"))
        location = list(item.get("loc", ()))
        if error_type == "extra_forbidden" and location:
            location[-1] = "field"
        public_errors.append(
            {
                "type": error_type,
                "loc": location,
                "msg": str(item.get("msg", "Invalid request value")),
            }
        )
    return public_errors


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=_exception_headers_for(request, exc.headers),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    from fastapi.encoders import jsonable_encoder

    errors = exc.errors()
    public_errors = _public_validation_errors(errors)
    safe_types = sorted({str(item.get("type", "unknown")) for item in errors})
    logger.warning(
        "request_validation_failed count=%d types=%s",
        len(errors),
        safe_types,
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": jsonable_encoder(public_errors),
            "message": "Validation Error",
        },
        headers=_exception_headers_for(request),
    )


@app.exception_handler(CoreException)
async def core_exception_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "message": "Application Error"},
        headers=_exception_headers_for(request),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    diagnostic = diagnose_failure(exc, FailureCode.HTTP_REQUEST_FAILED)
    log_failure(logger, diagnostic)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
        headers=_exception_headers_for(request),
    )


def _check_db_status() -> str:
    """Return 'connected' or 'unavailable' depending on whether the DB is reachable."""
    from sqlalchemy import text

    from backend.db.base import SessionLocal

    db = None
    try:
        db = SessionLocal()
    except Exception as exc:
        diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_OPERATION_FAILED)
        log_failure(logger, diagnostic, level=logging.WARNING)
        return "unavailable"

    try:
        db.execute(text("SELECT 1"))
        return "connected"
    except Exception as exc:
        diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_OPERATION_FAILED)
        log_failure(logger, diagnostic, level=logging.WARNING)
        return "unavailable"
    finally:
        if db is not None:
            db.close()


def _check_storage_status() -> str:
    """Verify that the configured local data directory is writable."""
    from backend.storage.atomic import data_root

    try:
        root = data_root()
        handle, probe = tempfile.mkstemp(prefix=".health-", dir=root)
        try:
            os.write(handle, b"ok")
            os.fsync(handle)
        finally:
            os.close(handle)
            Path(probe).unlink(missing_ok=True)
        return "writable"
    except Exception as exc:
        diagnostic = diagnose_failure(exc, FailureCode.LOCAL_RESOURCE_LOAD_FAILED)
        log_failure(logger, diagnostic, level=logging.WARNING)
        return "unavailable"


@lru_cache(maxsize=1)
def _expected_migration_heads() -> frozenset[str]:
    from backend.migrations.resources import current_migration_head

    return frozenset({current_migration_head()})


def _check_migration_status() -> str:
    """Return current/outdated/unavailable without exposing schema identifiers."""
    from alembic.migration import MigrationContext

    from backend.db.base import engine

    try:
        with engine.connect() as connection:
            current = frozenset(MigrationContext.configure(connection).get_current_heads())
        return "current" if current == _expected_migration_heads() else "outdated"
    except Exception as exc:
        diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_OPERATION_FAILED)
        log_failure(logger, diagnostic, level=logging.WARNING)
        return "unavailable"


# ─── Routes ───
app.include_router(api_router, prefix=settings.API_V1_STR)


def _openapi_schema() -> dict:
    """Describe the two desktop authentication factors as one AND requirement."""
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )
    automation_paths = (
        f"{settings.API_V1_STR}/automation/grants",
        f"{settings.API_V1_STR}/automation/grants/{{grant_id}}/revoke",
    )
    for path in automation_paths:
        for operation in schema["paths"].get(path, {}).values():
            if isinstance(operation, dict) and "responses" in operation:
                operation["security"] = [
                    {
                        "desktopSession": [],
                        "OAuth2PasswordBearer": [],
                    }
                ]
    app.openapi_schema = schema
    return schema


setattr(app, "openapi", _openapi_schema)


def _readiness_statuses() -> tuple[str, str, str]:
    return (
        _check_db_status(),
        _check_storage_status(),
        _check_migration_status(),
    )


async def _joined_readiness_statuses() -> tuple[str, str, str]:
    """Keep the gate permit until the real probe thread exits, even on cancellation."""

    worker = asyncio.create_task(asyncio.to_thread(_readiness_statuses))
    caller_cancelled = False
    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            caller_cancelled = True
    statuses = await worker
    if caller_cancelled:
        raise asyncio.CancelledError
    return statuses


@app.get(f"{settings.API_V1_STR}/health")
async def health():
    """Backward-compatible alias for readiness."""
    return await health_ready()


@app.get(f"{settings.API_V1_STR}/health/ready")
async def health_ready():
    async with vault_activity_gate.try_reader() as acquired:
        if not acquired:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "maintenance",
                    "code": "vault_maintenance_pending",
                    "database": "not_checked",
                    "storage": "not_checked",
                    "migrations": "not_checked",
                },
            )
        db_status, storage_status, migration_status = await _joined_readiness_statuses()
    content = {
        "status": "ready"
        if (
            db_status == "connected"
            and storage_status == "writable"
            and migration_status == "current"
        )
        else "degraded",
        "database": db_status,
        "storage": storage_status,
        "migrations": migration_status,
    }
    if content["status"] != "ready":
        return JSONResponse(status_code=503, content=content)
    return content


@app.get(f"{settings.API_V1_STR}/health/live")
async def health_live():
    return {"status": "alive"}


@app.get(f"{settings.API_V1_STR}/health/model")
async def health_model():
    from backend.inference.service import get_local_model_status

    status = await get_local_model_status()
    return {
        "status": "ready" if status.ready else "unavailable",
        "available": status.available,
        "ready": status.ready,
        "configured_model": status.configured_model,
        "error_code": status.error_code,
    }


@app.get("/")
async def root():
    return {
        "message": "CareerOS Local API",
        "status": "online",
    }
