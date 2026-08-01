"""Cross-process and integrity boundaries for SQLite schema migrations."""

from __future__ import annotations

import os
import stat
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

from alembic.config import Config
from sqlalchemy import Connection
from sqlalchemy.engine import URL, make_url

from backend.db.sqlite import sqlite_database_path

DEFAULT_DATABASE_URL = "sqlite:///./data/careeros.db"
MIGRATION_LOCK_TIMEOUT_SECONDS = 300.0


class MigrationLockTimeout(TimeoutError):
    """Raised when another process owns the schema migration boundary."""


def database_url_from_config(config: Config) -> URL:
    """Resolve one explicit migration target without importing the app engine.

    Programmatic launchers use ``config.attributes['database_url']`` so path
    punctuation is never round-tripped through ConfigParser. A non-default URL
    explicitly set on ``Config`` wins next. The environment overrides only the
    checked-in fallback, preserving isolated migration tests in CI where a
    different process-wide ``DATABASE_URL`` may also exist.
    """

    attributed = config.attributes.get("database_url")
    configured = config.get_main_option("sqlalchemy.url")
    if attributed is not None:
        selected = attributed
    elif configured and configured != DEFAULT_DATABASE_URL:
        selected = configured
    else:
        selected = os.environ.get("DATABASE_URL", "").strip() or configured
    if not selected:
        raise RuntimeError("Alembic has no SQLite database target")
    url = selected if isinstance(selected, URL) else make_url(selected)
    sqlite_database_path(url)
    return url


def sqlite_busy_timeout_ms() -> int:
    """Parse the one migration-relevant runtime setting without app side effects."""

    raw = os.environ.get("SQLITE_BUSY_TIMEOUT_MS", "5000").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("SQLITE_BUSY_TIMEOUT_MS must be an integer") from exc
    if not 1 <= value <= 300_000:
        raise RuntimeError("SQLITE_BUSY_TIMEOUT_MS must be between 1 and 300000")
    return value


_process_lock = threading.RLock()
_thread_state = threading.local()


def _try_lock(handle: BinaryIO) -> bool:
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(  # type: ignore[attr-defined]
                handle.fileno(),
                msvcrt.LK_NBLCK,  # type: ignore[attr-defined]
                1,
            )
        else:
            import fcntl

            fcntl.flock(  # type: ignore[attr-defined]
                handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,  # type: ignore[attr-defined]
            )
    except OSError:
        return False
    return True


def _unlock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(  # type: ignore[attr-defined]
            handle.fileno(),
            msvcrt.LK_UNLCK,  # type: ignore[attr-defined]
            1,
        )
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


def _open_lock_file(lock_path: Path) -> BinaryIO:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = lock_path.lstat()
    except FileNotFoundError:
        pass
    else:
        file_attributes = int(getattr(existing, "st_file_attributes", 0))
        if (
            lock_path.is_symlink()
            or bool(file_attributes & 0x400)
            or not stat.S_ISREG(existing.st_mode)
            or int(getattr(existing, "st_nlink", 1)) != 1
        ):
            raise RuntimeError("Migration lock must be one ordinary local file")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        path_metadata = lock_path.lstat()
        file_attributes = int(getattr(path_metadata, "st_file_attributes", 0))
        if (
            lock_path.is_symlink()
            or bool(file_attributes & 0x400)
            or not os.path.samestat(metadata, path_metadata)
            or not stat.S_ISREG(metadata.st_mode)
            or int(getattr(metadata, "st_nlink", 1)) != 1
        ):
            raise RuntimeError("Migration lock must be one ordinary local file")
        handle = os.fdopen(descriptor, "r+b")
        descriptor = -1
        if metadata.st_size == 0:
            handle.write(b"0")
            handle.flush()
            os.fsync(handle.fileno())
        return handle
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        raise


@contextmanager
def migration_lock(
    database_path: Path | None,
    *,
    timeout_seconds: float = MIGRATION_LOCK_TIMEOUT_SECONDS,
) -> Iterator[None]:
    """Serialize migrations across threads/processes, including nested Alembic calls."""

    if timeout_seconds <= 0:
        raise ValueError("Migration lock timeout must be positive")
    canonical = database_path.resolve(strict=False) if database_path is not None else None
    key = os.path.normcase(str(canonical)) if canonical is not None else ":memory:"
    deadline = time.monotonic() + timeout_seconds
    remaining = max(0.0, deadline - time.monotonic())
    if not _process_lock.acquire(timeout=remaining):
        raise MigrationLockTimeout("Another CareerOS schema migration is still running")

    counts = getattr(_thread_state, "migration_counts", None)
    if counts is None:
        counts = {}
        _thread_state.migration_counts = counts
    if counts.get(key, 0):
        counts[key] += 1
        try:
            yield
        finally:
            counts[key] -= 1
            _process_lock.release()
        return

    counts[key] = 1
    handle: BinaryIO | None = None
    locked = False
    try:
        if canonical is not None:
            lock_path = canonical.parent / f".{canonical.name}.migration.lock"
            handle = _open_lock_file(lock_path)
            while not _try_lock(handle):
                if time.monotonic() >= deadline:
                    raise MigrationLockTimeout("Another CareerOS schema migration is still running")
                time.sleep(0.05)
            locked = True
        yield
    finally:
        try:
            if handle is not None:
                try:
                    if locked:
                        _unlock(handle)
                finally:
                    handle.close()
        finally:
            counts.pop(key, None)
            _process_lock.release()


def configure_migration_connection(connection: Connection, *, busy_timeout_ms: int) -> None:
    """Apply bounded SQLite migration settings before non-transactional DDL."""

    connection.exec_driver_sql(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    connection.exec_driver_sql("PRAGMA synchronous=FULL")
    observed_timeout = int(connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one())
    foreign_keys = int(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one())
    synchronous = int(connection.exec_driver_sql("PRAGMA synchronous").scalar_one())
    if observed_timeout != busy_timeout_ms or foreign_keys != 0 or synchronous != 2:
        raise RuntimeError("SQLite migration safety settings were not applied")


def validate_sqlite_integrity(connection: Connection) -> None:
    """Fail a migration whose resulting SQLite image is physically/logically invalid."""

    quick_check = connection.exec_driver_sql("PRAGMA quick_check").all()
    if quick_check != [("ok",)]:
        raise RuntimeError("SQLite quick integrity check failed after schema migration")
    if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("SQLite foreign-key integrity check failed after schema migration")
