import os
import threading
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.config import settings
from backend.db.sqlite import (
    ensure_sqlite_database_parent,
    sqlite_database_path,
    validate_sqlite_runtime_files,
)
from backend.models.base_model import Base as Base


def ensure_sqlite_parent(database_url: str, *, data_root: Path | None = None) -> None:
    """Create the parent for a file-backed SQLite vault before opening it."""
    ensure_sqlite_database_parent(database_url, data_root=data_root)


def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    """Apply durability and integrity settings to every SQLite connection."""
    cursor = dbapi_connection.cursor()
    try:
        database_rows = cursor.execute("PRAGMA database_list").fetchall()
        main_file = next((str(row[2]) for row in database_rows if str(row[1]) == "main"), "")
        if main_file:
            # Bootstrap hardens files before create_engine. Runtime checks must
            # never open/close a second descriptor: on POSIX that could release
            # fcntl locks held by another SQLite connection in this process.
            validate_sqlite_runtime_files(Path(main_file))

        cursor.execute(f"PRAGMA busy_timeout={int(settings.SQLITE_BUSY_TIMEOUT_MS)}")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA secure_delete=ON")
        journal_mode = str(cursor.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.execute("PRAGMA trusted_schema=OFF")

        if main_file:
            validate_sqlite_runtime_files(Path(main_file))
        if main_file and journal_mode != "wal":
            raise RuntimeError("SQLite could not enable WAL for the local vault")
        checks = {
            "busy_timeout": int(cursor.execute("PRAGMA busy_timeout").fetchone()[0]),
            "foreign_keys": int(cursor.execute("PRAGMA foreign_keys").fetchone()[0]),
            "secure_delete": int(cursor.execute("PRAGMA secure_delete").fetchone()[0]),
            "synchronous": int(cursor.execute("PRAGMA synchronous").fetchone()[0]),
            "trusted_schema": int(cursor.execute("PRAGMA trusted_schema").fetchone()[0]),
        }
        expected = {
            "busy_timeout": int(settings.SQLITE_BUSY_TIMEOUT_MS),
            "foreign_keys": 1,
            "secure_delete": 1,
            "synchronous": 2,
            "trusted_schema": 0,
        }
        if checks != expected:
            raise RuntimeError("SQLite connection safety settings were not applied")
    finally:
        cursor.close()


# Configure connection pooling appropriately based on the database type
if os.environ.get("TESTING") == "1":
    # Use a shared in-memory database for testing to ensure background tasks
    # and the main thread see the same data.
    SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
elif (configured_database_path := sqlite_database_path(settings.DATABASE_URL)) is not None:
    database_path_for_runtime: Path = configured_database_path
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={
            "check_same_thread": False,
            "timeout": settings.SQLITE_BUSY_TIMEOUT_MS / 1000,
        },
    )
    _sqlite_bootstrap_lock = threading.Lock()
    _sqlite_bootstrapped = False

    def _prepare_sqlite_before_connect(*_args, **_kwargs) -> None:
        """Reserve the vault privately before the first DB-API handle opens."""

        global _sqlite_bootstrapped
        with _sqlite_bootstrap_lock:
            if not _sqlite_bootstrapped:
                ensure_sqlite_parent(
                    settings.DATABASE_URL,
                    data_root=Path(settings.DATA_DIR),
                )
                _sqlite_bootstrapped = True
            else:
                # Descriptor repair after the first connection could release
                # process-wide POSIX fcntl locks; later connects only inspect.
                validate_sqlite_runtime_files(database_path_for_runtime)

    event.listen(engine, "do_connect", _prepare_sqlite_before_connect)
else:
    # Settings validation permits an in-memory SQLite URL only in non-production
    # contexts. Production and normal test runs use the explicit branches above.
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

event.listen(engine, "connect", configure_sqlite_connection)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
