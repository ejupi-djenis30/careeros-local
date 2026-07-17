import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.api import api_router
from backend.api.deps import limiter
from backend.core.config import settings
from backend.core.exceptions import CoreException
from backend.core.logging import configure_logging
from backend.desktop.settings import DesktopRuntimeSettings

# ─── Logging ───
configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)
desktop_runtime = DesktopRuntimeSettings.from_environment()


# ─── Lifespan ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    # Startup: create DB tables
    # Moved to backend/pre_start.py to avoid race conditions with multiple workers

    # Startup: start scheduler
    from backend.services.scheduler import start_scheduler, stop_scheduler

    start_scheduler()

    yield

    # Shutdown: cancel any in-flight search tasks, then stop scheduler
    from backend.services.search_status import get_all_active_tasks, update_status

    active = get_all_active_tasks()
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
                        error="Server shutdown",
                    )
            except Exception:
                pass
        # Give tasks a moment to handle CancelledError and run their finally blocks
        await asyncio.gather(*active.values(), return_exceptions=True)

    stop_scheduler()


# ─── App ───
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
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
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


# ─── Basic Production Middlewares ───
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

# ─── CORS ───
if settings.cors_origins_list:
    logger.info(f"Configuring CORS with origins: {settings.cors_origins_list}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.cors_origins_list],
        allow_origin_regex=settings.CORS_ALLOW_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    logger.warning("CORS_ORIGINS is empty — CORS middleware not added!")

if desktop_runtime.enabled:
    from backend.desktop.session import DesktopSessionMiddleware

    app.add_middleware(
        DesktopSessionMiddleware,
        token=desktop_runtime.session_token,
    )


# ─── Exception Handlers ───
def _cors_headers_for(request) -> dict:
    """Return CORS headers for the request origin, if it is an allowed origin.
    Exception handlers bypass CORSMiddleware, so we must add headers manually."""
    origin = request.headers.get("origin", "")
    if not origin or not settings.cors_origins_list:
        return {}
    allowed = [str(o) for o in settings.cors_origins_list]
    if origin in allowed or "*" in allowed:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        }
    return {}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=_cors_headers_for(request),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    from fastapi.encoders import jsonable_encoder

    errors = exc.errors()
    safe_types = sorted({str(item.get("type", "unknown")) for item in errors})
    logger.warning(
        "request_validation_failed path=%s count=%d types=%s",
        request.url.path,
        len(errors),
        safe_types,
    )
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors()), "message": "Validation Error"},
        headers=_cors_headers_for(request),
    )


@app.exception_handler(CoreException)
async def core_exception_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "message": "Application Error"},
        headers=_cors_headers_for(request),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    logger.error(
        "unhandled_exception method=%s path=%s exception_type=%s",
        request.method,
        request.url.path,
        type(exc).__name__,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
        headers=_cors_headers_for(request),
    )


def _check_db_status() -> str:
    """Return 'connected' or 'unavailable' depending on whether the DB is reachable."""
    from sqlalchemy import text

    from backend.db.base import SessionLocal

    db = None
    try:
        db = SessionLocal()
    except Exception as exc:
        logger.warning("health_db_session_failed exception_type=%s", type(exc).__name__)
        return "unavailable"

    try:
        db.execute(text("SELECT 1"))
        return "connected"
    except Exception as exc:
        logger.warning("health_db_ping_failed exception_type=%s", type(exc).__name__)
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
        logger.warning("health_storage_failed exception_type=%s", type(exc).__name__)
        return "unavailable"


@lru_cache(maxsize=1)
def _expected_migration_heads() -> frozenset[str]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    repository_root = Path(__file__).resolve().parents[1]
    config = Config(str(repository_root / "alembic.ini"))
    config.set_main_option("script_location", str(repository_root / "alembic"))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def _check_migration_status() -> str:
    """Return current/outdated/unavailable without exposing schema identifiers."""
    from alembic.migration import MigrationContext

    from backend.db.base import engine

    try:
        with engine.connect() as connection:
            current = frozenset(MigrationContext.configure(connection).get_current_heads())
        return "current" if current == _expected_migration_heads() else "outdated"
    except Exception as exc:
        logger.warning("health_migration_failed exception_type=%s", type(exc).__name__)
        return "unavailable"


# ─── Routes ───
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get(f"{settings.API_V1_STR}/health")
def health():
    """Backward-compatible alias for readiness."""
    return health_ready()


@app.get(f"{settings.API_V1_STR}/health/ready")
def health_ready():
    db_status = _check_db_status()
    storage_status = _check_storage_status()
    migration_status = _check_migration_status()
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
def health_live():
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
    db_status = _check_db_status()
    return {
        "message": "CareerOS Local API",
        "status": "online",
        "database": db_status,
    }
