"""Exclusive, cwd-independent bootstrap for the headless automation process."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


class AutomationRuntimeError(RuntimeError):
    """A stable automation bootstrap failure safe to show without a traceback."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    data_dir: Path
    database_path: Path
    database_revision: str
    session_factory: Any


def default_data_dir() -> Path:
    identifier = "local.careeros.desktop"
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", "").strip()
        if not base:
            raise AutomationRuntimeError(
                "data_dir_required", "APPDATA is unavailable; pass --data-dir"
            )
        return (Path(base) / identifier).resolve(strict=False)
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / identifier).resolve(strict=False)
    base = os.environ.get("XDG_DATA_HOME", "").strip()
    root = Path(base).expanduser() if base else Path.home() / ".local" / "share"
    return (root / identifier).resolve(strict=False)


def resolve_data_dir(value: str | Path | None) -> Path:
    raw = value or os.environ.get("CAREEROS_DESKTOP_DATA_DIR")
    candidate = Path(raw).expanduser() if raw else default_data_dir()
    if not candidate.is_absolute():
        raise AutomationRuntimeError(
            "data_dir_required", "CareerOS data directory must be absolute"
        )
    return candidate.resolve(strict=False)


def _configure_environment(data_dir: Path) -> Path:
    database_path = data_dir / "vault" / "careeros.db"
    secret_path = data_dir / "vault" / ".installation-secret"
    if not database_path.is_file():
        raise AutomationRuntimeError(
            "vault_not_found",
            "CareerOS vault not found; open the desktop app before authorizing automation",
        )
    try:
        installation_secret = secret_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise AutomationRuntimeError(
            "installation_secret_missing", "CareerOS installation secret is unavailable"
        ) from exc
    if len(installation_secret) < 32:
        raise AutomationRuntimeError(
            "installation_secret_invalid", "CareerOS installation secret is invalid"
        )
    initialized_modules = {
        name for name in ("backend.core.config", "backend.db.base") if name in sys.modules
    }
    if initialized_modules:
        raise AutomationRuntimeError(
            "runtime_already_initialized",
            "Automation runtime must be configured before CareerOS settings or database imports",
        )
    os.environ.update(
        {
            "CAREEROS_DESKTOP_MODE": "0",
            "CAREEROS_DESKTOP_DATA_DIR": str(data_dir),
            "CAREEROS_SECRET_FILE": str(secret_path),
            "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "DATA_DIR": str(data_dir),
            "SECRET_KEY": installation_secret,
            "ENVIRONMENT": "production",
        }
    )
    return database_path


def _revision_state(database_path: Path) -> tuple[set[str], set[str]]:
    from desktop.backend_main import database_revision_state

    try:
        return cast(
            tuple[set[str], set[str]],
            database_revision_state(database_path, read_only=True),
        )
    except Exception as exc:
        raise AutomationRuntimeError(
            "schema_unavailable", "CareerOS could not inspect the vault schema"
        ) from exc


def _read_only_session_bundle(database_path: Path) -> tuple[Any, Any]:
    """Build a SQLite read capability that cannot mutate the vault."""
    import sqlite3

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    from backend.core.config import settings

    database_uri = f"{database_path.resolve(strict=True).as_uri()}?mode=ro"

    def open_database():
        return sqlite3.connect(
            database_uri,
            uri=True,
            check_same_thread=False,
        )

    read_only_engine = create_engine(
        "sqlite://",
        creator=open_database,
        poolclass=NullPool,
    )

    def configure_read_only_connection(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA query_only=ON")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={int(settings.SQLITE_BUSY_TIMEOUT_MS)}")
            cursor.execute("PRAGMA query_only")
            state = cursor.fetchone()
            if state is None or int(state[0]) != 1:
                raise AutomationRuntimeError(
                    "read_only_unavailable",
                    "CareerOS could not enforce read-only vault access",
                )
        finally:
            cursor.close()

    event.listen(read_only_engine, "connect", configure_read_only_connection)
    factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=read_only_engine,
    )
    return factory, read_only_engine


@contextmanager
def automation_runtime(
    data_dir_value: str | Path | None,
    *,
    migrate: bool = False,
    write_access: bool = False,
) -> Iterator[RuntimeContext]:
    data_dir = resolve_data_dir(data_dir_value)
    database_path = _configure_environment(data_dir)

    from backend.desktop.lifecycle import DesktopInstanceAlreadyRunning, desktop_instance_lease

    try:
        with desktop_instance_lease(root=data_dir):
            current, expected = _revision_state(database_path)
            if migrate and current != expected:
                from desktop.backend_main import DesktopMigrationError, migrate_database

                try:
                    migrate_database(database_path, data_dir / "backups")
                except DesktopMigrationError as exc:
                    raise AutomationRuntimeError(
                        "migration_failed",
                        "CareerOS could not update the vault schema; the previous vault was preserved",
                    ) from exc
                current, expected = _revision_state(database_path)
            if current != expected or not current:
                raise AutomationRuntimeError(
                    "migration_required",
                    "CareerOS schema is not current; run `careeros authorize` while the desktop app is closed",
                )

            if write_access:
                from backend.db.base import SessionLocal, engine

                session_factory = SessionLocal
                runtime_engine = engine
            else:
                session_factory, runtime_engine = _read_only_session_bundle(database_path)

            try:
                yield RuntimeContext(
                    data_dir=data_dir,
                    database_path=database_path,
                    database_revision=next(iter(current)),
                    session_factory=session_factory,
                )
            finally:
                runtime_engine.dispose()
    except DesktopInstanceAlreadyRunning as exc:
        raise AutomationRuntimeError(
            "vault_busy", "Close CareerOS Local before starting the CLI or MCP server"
        ) from exc


def doctor(data_dir_value: str | Path | None) -> dict[str, object]:
    data_dir = resolve_data_dir(data_dir_value)
    database_path = data_dir / "vault" / "careeros.db"
    secret_path = data_dir / "vault" / ".installation-secret"
    vault_exists = database_path.is_file()
    current: set[str] | None = None
    expected: set[str] | None = None
    diagnostic_codes: list[str] = []

    secret_status = "missing"
    if secret_path.is_file():
        try:
            installation_secret = secret_path.read_text(encoding="utf-8").strip()
            secret_status = "ready" if len(installation_secret) >= 32 else "invalid"
        except OSError:
            secret_status = "unavailable"
    if secret_status != "ready":
        diagnostic_codes.append(f"installation_secret_{secret_status}")

    schema_status = "missing"
    migration_required: bool | None = None
    if vault_exists:
        try:
            current, expected = _revision_state(database_path)
            if not current or not expected:
                schema_status = "unavailable"
                diagnostic_codes.append("schema_unavailable")
            elif current != expected:
                schema_status = "migration_required"
                migration_required = True
                diagnostic_codes.append("migration_required")
            else:
                schema_status = "ready"
                migration_required = False
        except AutomationRuntimeError:
            schema_status = "unavailable"
            diagnostic_codes.append("schema_unavailable")
    else:
        diagnostic_codes.append("vault_not_found")

    return {
        "schema_version": "1.0",
        "data_dir": str(data_dir),
        "ready": not diagnostic_codes,
        "diagnostic_codes": diagnostic_codes,
        "vault_exists": vault_exists,
        "installation_secret_exists": secret_path.is_file(),
        "installation_secret_status": secret_status,
        "schema_status": schema_status,
        "database_revision": next(iter(current), None) if current else None,
        "expected_revision": next(iter(expected), None) if expected else None,
        "migration_required": migration_required,
    }
