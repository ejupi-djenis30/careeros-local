import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine
from tenacity import after_log, before_log, retry, stop_after_attempt, wait_fixed

from backend import model_registry  # noqa: F401
from backend.core.config import settings
from backend.core.diagnostics import FailureCode, diagnose_failure, log_failure
from backend.core.logging import configure_logging

configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

max_tries = 30
wait_seconds = 1


def _runtime_engine() -> Engine:
    """Import the lazy application engine only after schema migration."""

    from backend.db.base import engine

    return engine


@retry(
    stop=stop_after_attempt(max_tries),
    wait=wait_fixed(wait_seconds),
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.WARN),
)
def init() -> None:
    engine = _runtime_engine()
    try:
        # Try to create session to check if DB is awake
        with engine.connect() as db:
            db.execute(text("SELECT 1"))
        logger.info("Database is ready.")

    except Exception as exc:
        diagnostic = diagnose_failure(exc, FailureCode.REPOSITORY_OPERATION_FAILED)
        log_failure(logger, diagnostic)
        raise


def migrate_schema() -> None:
    """Run the backup-protected, crash-recoverable local SQLite upgrade."""

    from backend.db.sqlite import sqlite_database_path
    from desktop.backend_main import migrate_database

    database_path = sqlite_database_path(settings.DATABASE_URL)
    if database_path is None:
        raise RuntimeError("Service startup requires a file-backed SQLite database")
    migrate_database(database_path, Path(settings.DATA_DIR).expanduser().resolve() / "backups")


def main() -> None:
    logger.info("Initializing service")
    # The migration/restore boundary must run before the application opens its
    # first SQLite handle. This keeps new-vault rollback in `mode=new`, avoids
    # WAL/backup side effects before the OS migration lock, and is required on
    # Windows where an idle pooled handle prevents atomic replacement.
    migrate_schema()
    init()
    logger.info("Service finished initializing")


if __name__ == "__main__":
    main()
