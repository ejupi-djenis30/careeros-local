import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
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

# ─── Logging ───
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


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

    logger.error(f"Validation error: {exc.errors()}")
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
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
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
        logger.warning("Health DB session creation failed: %s", exc)
        return "unavailable"

    try:
        db.execute(text("SELECT 1"))
        return "connected"
    except Exception as exc:
        logger.warning("Health DB ping failed: %s", exc)
        return "unavailable"
    finally:
        if db is not None:
            db.close()


# ─── Routes ───
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get(f"{settings.API_V1_STR}/health")
def health():
    db_status = _check_db_status()
    if db_status != "connected":
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"status": "degraded", "database": db_status})
    return {"status": "ok", "database": db_status}


@app.get(f"{settings.API_V1_STR}/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/")
async def root():
    db_status = _check_db_status()
    return {
        "message": "Job Hunter AI API",
        "status": "online",
        "database": db_status,
    }
