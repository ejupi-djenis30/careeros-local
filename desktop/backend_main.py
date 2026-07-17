"""Frozen backend entry point owned by the CareerOS Local desktop shell.

The native shell supplies an ephemeral port and per-launch session token. This module creates
the per-user vault layout, performs a backup-protected schema migration, and then starts one
loopback-only Uvicorn worker. It deliberately imports the application only after the environment
has been configured because application settings are immutable after import.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import sqlite3
import sys
import threading
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence


class DesktopMigrationError(RuntimeError):
    """Raised after a desktop schema upgrade fails and rollback is attempted."""


@dataclass(frozen=True, slots=True)
class DesktopArguments:
    host: str
    port: int
    data_dir: Path
    parent_pid: int


@dataclass(frozen=True, slots=True)
class ConfiguredDesktop:
    arguments: DesktopArguments
    database_path: Path
    backup_directory: Path
    installation_secret_path: Path


def parse_args(argv: Sequence[str] | None = None) -> DesktopArguments:
    parser = argparse.ArgumentParser(prog="careeros-backend", allow_abbrev=False)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--parent-pid", required=True, type=int)
    namespace = parser.parse_args(argv)
    return DesktopArguments(
        host=str(namespace.host).strip(),
        port=int(namespace.port),
        data_dir=namespace.data_dir.expanduser().resolve(strict=False),
        parent_pid=int(namespace.parent_pid),
    )


def resource_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root).resolve()
    return Path(__file__).resolve().parents[1]


def _write_installation_secret(path: Path) -> str:
    try:
        current = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        current = ""
    if current:
        if len(current) < 43:
            raise RuntimeError("Existing desktop installation secret is invalid")
        return current

    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(48)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        current = path.read_text(encoding="utf-8").strip()
        if len(current) < 43:
            raise RuntimeError("Concurrent desktop secret initialization failed")
        return current
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(value)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return value


def configure_environment(arguments: DesktopArguments) -> ConfiguredDesktop:
    if arguments.host != "127.0.0.1":
        raise ValueError("Desktop backend must bind only to 127.0.0.1")
    if not 1 <= arguments.port <= 65535:
        raise ValueError("Desktop backend port must be between 1 and 65535")
    if arguments.parent_pid <= 0 or arguments.parent_pid == os.getpid():
        raise ValueError("Desktop backend requires a distinct native parent process")
    session_token = os.getenv("CAREEROS_DESKTOP_SESSION_TOKEN", "").strip()
    if not 32 <= len(session_token) <= 256:
        raise ValueError("Native shell must provide a strong per-launch session token")
    if not arguments.data_dir.is_absolute():
        raise ValueError("Desktop data directory must be absolute")

    for relative in ("assets", "backups", "logs", "models", "staging", "vault"):
        directory = arguments.data_dir / relative
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.chmod(0o700)
        except OSError:
            pass

    database_path = arguments.data_dir / "vault" / "careeros.db"
    secret_path = arguments.data_dir / "vault" / ".installation-secret"
    installation_secret = _write_installation_secret(secret_path)
    environment = {
        "CAREEROS_DESKTOP_MODE": "1",
        "CAREEROS_DESKTOP_HOST": arguments.host,
        "CAREEROS_DESKTOP_PORT": str(arguments.port),
        "CAREEROS_DESKTOP_DATA_DIR": str(arguments.data_dir),
        "CAREEROS_SECRET_FILE": str(secret_path),
        "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
        "DATA_DIR": str(arguments.data_dir),
        "SECRET_KEY": installation_secret,
        "ENVIRONMENT": "production",
        "ALLOWED_HOSTS": '["127.0.0.1","localhost"]',
        "CORS_ORIGINS": '["http://tauri.localhost","https://tauri.localhost","tauri://localhost"]',
        "CORS_ALLOW_ORIGIN_REGEX": "",
    }
    os.environ.update(environment)

    # Validate the exact values that backend.main will consume without importing backend.main.
    from backend.desktop.settings import DesktopRuntimeSettings

    runtime = DesktopRuntimeSettings.from_environment()
    runtime.ensure_directories()
    if runtime.database_path != database_path:
        raise RuntimeError("Desktop database path validation mismatch")
    return ConfiguredDesktop(
        arguments=arguments,
        database_path=database_path,
        backup_directory=arguments.data_dir / "backups",
        installation_secret_path=secret_path,
    )


def _alembic_config(database_path: Path):
    from alembic.config import Config

    root = resource_root()
    configuration = Config(str(root / "alembic.ini"))
    configuration.set_main_option("script_location", str(root / "alembic"))
    configuration.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return configuration


def database_revision_state(database_path: Path) -> tuple[set[str], set[str]]:
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine

    configuration = _alembic_config(database_path)
    expected = set(ScriptDirectory.from_config(configuration).get_heads())
    if not database_path.exists() or database_path.stat().st_size == 0:
        return set(), expected
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            current = set(MigrationContext.configure(connection).get_current_heads())
    finally:
        engine.dispose()
    return current, expected


def run_alembic_upgrade(database_path: Path) -> None:
    from alembic import command

    command.upgrade(_alembic_config(database_path), "heads")


def _backup_database(database_path: Path, backup_directory: Path) -> Path:
    backup_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_directory / f"careeros-{timestamp}.db"
    with closing(sqlite3.connect(database_path)) as source, closing(
        sqlite3.connect(backup_path)
    ) as destination:
        source.backup(destination)
        destination.commit()
    with backup_path.open("r+b") as handle:
        os.fsync(handle.fileno())
    return backup_path


def _remove_sqlite_sidecars(database_path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        Path(f"{database_path}{suffix}").unlink(missing_ok=True)


def _restore_database(database_path: Path, backup_path: Path) -> None:
    _remove_sqlite_sidecars(database_path)
    try:
        with closing(sqlite3.connect(backup_path)) as source, closing(
            sqlite3.connect(database_path)
        ) as destination:
            source.backup(destination)
            destination.commit()
    except sqlite3.Error:
        restore_path = database_path.with_suffix(".restore")
        shutil.copy2(backup_path, restore_path)
        os.replace(restore_path, database_path)
    _remove_sqlite_sidecars(database_path)


def _prune_backups(backup_directory: Path, *, keep: int = 5) -> None:
    backups = sorted(backup_directory.glob("careeros-*.db"), reverse=True)
    for expired in backups[keep:]:
        expired.unlink(missing_ok=True)


def migrate_database(database_path: Path, backup_directory: Path) -> Path | None:
    current, expected = database_revision_state(database_path)
    if current == expected:
        return None

    had_database = database_path.exists() and database_path.stat().st_size > 0
    backup_path = _backup_database(database_path, backup_directory) if had_database else None
    try:
        run_alembic_upgrade(database_path)
        migrated, target = database_revision_state(database_path)
        if migrated != target:
            raise RuntimeError("Schema revision did not reach the expected head")
    except Exception as exc:
        if backup_path is not None:
            _restore_database(database_path, backup_path)
            raise DesktopMigrationError(
                "Desktop database migration failed; the previous vault was restored"
            ) from exc
        _remove_sqlite_sidecars(database_path)
        database_path.unlink(missing_ok=True)
        raise DesktopMigrationError(
            "Desktop database migration failed before the vault was initialized"
        ) from exc
    _prune_backups(backup_directory)
    return backup_path


def run_server(configured: ConfiguredDesktop) -> None:
    import uvicorn

    start_parent_watchdog(configured.arguments.parent_pid)
    server_configuration = uvicorn.Config(
        "backend.main:app",
        host=configured.arguments.host,
        port=configured.arguments.port,
        workers=1,
        reload=False,
        access_log=False,
        server_header=False,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
    uvicorn.Server(server_configuration).run()


def parent_process_is_alive(process_id: int) -> bool:
    if process_id <= 0:
        return False
    if os.name == "nt":
        import ctypes

        synchronize = 0x00100000
        wait_timeout = 0x00000102
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(synchronize, False, process_id)
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(process_id, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def start_parent_watchdog(process_id: int, *, interval_seconds: float = 0.5) -> None:
    def monitor() -> None:
        while parent_process_is_alive(process_id):
            time.sleep(interval_seconds)
        os._exit(0)

    threading.Thread(name="careeros-parent-watchdog", target=monitor, daemon=True).start()


def main(argv: Sequence[str] | None = None) -> int:
    configured = configure_environment(parse_args(argv))
    migrate_database(configured.database_path, configured.backup_directory)
    run_server(configured)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
