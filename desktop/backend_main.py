"""Frozen backend entry point owned by the CareerOS Local desktop shell.

The native shell supplies an ephemeral port and per-launch session token. This module creates
the per-user vault layout, performs a backup-protected schema migration, and then starts one
loopback-only Uvicorn worker. It deliberately imports the application only after the environment
has been configured because application settings are immutable after import.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
import threading
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

UVICORN_GRACEFUL_SHUTDOWN_SECONDS = 20
PARENT_WATCHDOG_HARD_TIMEOUT_SECONDS = 30.0
INSTALLATION_SECRET_MIN_BYTES = 43
INSTALLATION_SECRET_MAX_BYTES = 256
INSTALLATION_SECRET_TEMP_ATTEMPTS = 32
_INSTALLATION_SECRET = re.compile(r"^[A-Za-z0-9_-]+$")
MIGRATION_RECOVERY_SCHEMA = 1
MIGRATION_RECOVERY_MAX_BYTES = 4096
_BACKUP_NAME = re.compile(r"^careeros-\d{8}T\d{12}Z-[0-9a-f]{8}\.db$")


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
    data_dir = namespace.data_dir.expanduser()
    if not data_dir.is_absolute():
        parser.error("--data-dir must be an absolute path")
    return DesktopArguments(
        host=str(namespace.host).strip(),
        port=int(namespace.port),
        data_dir=data_dir.resolve(strict=False),
        parent_pid=int(namespace.parent_pid),
    )


def resource_root() -> Path:
    """Return the packaged migration directory for source, wheel, and frozen runs."""
    from backend.migrations.resources import migration_resource_directory

    return migration_resource_directory()


def _is_link_like(path: Path, metadata: os.stat_result | None = None) -> bool:
    details = metadata or path.lstat()
    file_attributes = int(getattr(details, "st_file_attributes", 0))
    return path.is_symlink() or bool(file_attributes & 0x400)


def _effective_user_id() -> int:
    getter: Callable[[], int] | None = getattr(os, "geteuid", None)
    if getter is None:
        raise RuntimeError("Effective-user identity is unavailable on this platform")
    return getter()


def _secure_descriptor_mode(descriptor: int, mode: int) -> None:
    setter: Callable[[int, int], None] | None = getattr(os, "fchmod", None)
    if setter is None:
        raise RuntimeError("Descriptor-based permission changes are unavailable")
    setter(descriptor, mode)


def _ensure_private_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        path.mkdir(parents=True, exist_ok=False)
        metadata = path.lstat()
    if _is_link_like(path, metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"Desktop data path is not a regular directory: {path}")
    if os.name == "nt":
        confirmed = path.lstat()
        if (
            not os.path.samestat(metadata, confirmed)
            or _is_link_like(path, confirmed)
            or not stat.S_ISDIR(confirmed.st_mode)
        ):
            raise RuntimeError(f"Desktop data path changed during validation: {path}")
        return

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not os.path.samestat(metadata, opened)
            or not stat.S_ISDIR(opened.st_mode)
            or int(getattr(opened, "st_nlink", 1)) <= 0
            or opened.st_uid != _effective_user_id()
        ):
            raise RuntimeError(f"Desktop data directory changed while opening: {path}")
        _secure_descriptor_mode(descriptor, 0o700)
        secured = os.fstat(descriptor)
        if (
            not os.path.samestat(opened, secured)
            or secured.st_uid != _effective_user_id()
            or stat.S_IMODE(secured.st_mode) != 0o700
        ):
            raise RuntimeError(f"Desktop data directory is not private to this user: {path}")
    finally:
        os.close(descriptor)


def _validate_installation_secret(value: str) -> str:
    if (
        not INSTALLATION_SECRET_MIN_BYTES <= len(value) <= INSTALLATION_SECRET_MAX_BYTES
        or _INSTALLATION_SECRET.fullmatch(value) is None
    ):
        raise RuntimeError("Existing desktop installation secret is invalid")
    return value


def _installation_secret_temp_paths(path: Path) -> list[Path]:
    pattern = re.compile(rf"^\.{re.escape(path.name)}\.[0-9a-f]{{32}}\.tmp$")
    matches = [
        candidate for candidate in path.parent.iterdir() if pattern.fullmatch(candidate.name)
    ]
    if len(matches) > INSTALLATION_SECRET_TEMP_ATTEMPTS * 2:
        raise RuntimeError("Desktop installation secret has too many temporary siblings")
    return matches


def _settle_installation_secret_publication(path: Path, metadata: os.stat_result) -> os.stat_result:
    """Recover the completed two-link state left by a kill after publication."""
    if int(getattr(metadata, "st_nlink", 1)) == 1:
        return metadata
    if int(getattr(metadata, "st_nlink", 1)) != 2:
        raise RuntimeError("Desktop installation secret has an ambiguous hard-link identity")

    aliases: list[Path] = []
    for candidate in _installation_secret_temp_paths(path):
        try:
            candidate_metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        if os.path.samestat(metadata, candidate_metadata):
            if (
                _is_link_like(candidate, candidate_metadata)
                or not stat.S_ISREG(candidate_metadata.st_mode)
                or int(getattr(candidate_metadata, "st_nlink", 1)) != 2
            ):
                raise RuntimeError("Desktop installation secret temporary alias is unsafe")
            aliases.append(candidate)

    if len(aliases) != 1:
        # The publisher may have removed its alias while this process was
        # enumerating. Re-read once before rejecting an unexplained hard link.
        refreshed = path.lstat()
        if int(getattr(refreshed, "st_nlink", 1)) == 1:
            return refreshed
        raise RuntimeError("Desktop installation secret has an ambiguous hard-link identity")
    aliases[0].unlink(missing_ok=True)
    _fsync_directory(path.parent)
    settled = path.lstat()
    if not os.path.samestat(metadata, settled) or int(getattr(settled, "st_nlink", 1)) != 1:
        raise RuntimeError("Desktop installation secret publication did not settle safely")
    return settled


def _read_installation_secret(path: Path) -> str:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        raise
    if (
        _is_link_like(path, metadata)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > INSTALLATION_SECRET_MAX_BYTES + 2
    ):
        raise RuntimeError("Existing desktop installation secret is not a bounded regular file")
    metadata = _settle_installation_secret_publication(path, metadata)
    if int(getattr(metadata, "st_nlink", 1)) != 1:
        raise RuntimeError("Existing desktop installation secret has a hard-link alias")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not os.path.samestat(metadata, opened)
            or not stat.S_ISREG(opened.st_mode)
            or int(getattr(opened, "st_nlink", 1)) != 1
            or (os.name != "nt" and (opened.st_uid != _effective_user_id()))
        ):
            raise RuntimeError("Desktop installation secret changed while it was opened")
        if os.name != "nt":
            _secure_descriptor_mode(descriptor, 0o600)
            secured = os.fstat(descriptor)
            if (
                not os.path.samestat(opened, secured)
                or secured.st_uid != _effective_user_id()
                or stat.S_IMODE(secured.st_mode) != 0o600
            ):
                raise RuntimeError("Desktop installation secret permissions are not private")
        with os.fdopen(descriptor, "r", encoding="utf-8", newline="") as handle:
            descriptor = -1
            payload = handle.read(INSTALLATION_SECRET_MAX_BYTES + 3)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    value = payload.removesuffix("\r\n").removesuffix("\n")
    if payload not in {value, f"{value}\n", f"{value}\r\n"}:
        raise RuntimeError("Existing desktop installation secret has non-canonical whitespace")
    return _validate_installation_secret(value)


def _write_installation_secret(path: Path) -> str:
    try:
        return _read_installation_secret(path)
    except FileNotFoundError:
        pass

    _ensure_private_directory(path.parent)
    value = secrets.token_urlsafe(48)
    _validate_installation_secret(value)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    for _attempt in range(INSTALLATION_SECRET_TEMP_ATTEMPTS):
        temporary = path.parent / f".{path.name}.{secrets.token_hex(16)}.tmp"
        try:
            descriptor = os.open(temporary, flags, 0o600)
        except FileExistsError:
            continue
        published = False
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                descriptor = -1
                handle.write(value)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError:
                pass
            else:
                published = True
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)
            _fsync_directory(path.parent)
        if published:
            observed = _read_installation_secret(path)
            if observed != value:
                raise RuntimeError("Published desktop installation secret changed unexpectedly")
            return value
        return _read_installation_secret(path)
    raise RuntimeError("Desktop installation secret temporary name reservation was exhausted")


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
    data_dir = arguments.data_dir.expanduser()
    if not data_dir.is_absolute():
        raise ValueError("Desktop data directory must be absolute")
    data_dir = data_dir.resolve(strict=False)
    if data_dir.parent == data_dir:
        raise ValueError("Desktop data directory cannot be a filesystem root")
    arguments = DesktopArguments(
        host=arguments.host,
        port=arguments.port,
        data_dir=data_dir,
        parent_pid=arguments.parent_pid,
    )

    _ensure_private_directory(arguments.data_dir)
    directories = [
        arguments.data_dir / relative
        for relative in ("assets", "backups", "logs", "models", "staging", "vault")
    ]
    for directory in directories:
        _ensure_private_directory(directory)

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
        "LOG_LEVEL": "INFO",
        "ALLOWED_HOSTS": '["127.0.0.1","localhost"]',
        "CORS_ORIGINS": '["http://tauri.localhost","https://tauri.localhost","tauri://localhost"]',
    }
    os.environ.update(environment)

    # Validate the exact values that backend.main will consume without importing backend.main.
    from backend.desktop.settings import DesktopRuntimeSettings

    runtime = DesktopRuntimeSettings.from_environment()
    runtime.ensure_directories()
    for directory in (arguments.data_dir, *directories):
        _ensure_private_directory(directory)
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

    from backend.db.sqlite import sqlite_url_for_path

    root = resource_root()
    configuration = Config(str(root / "alembic.ini"))
    configuration.set_main_option("script_location", str(root))
    # Avoid ConfigParser interpolation/path parsing for valid filesystem
    # punctuation such as '%'. The migration environment consumes this URL
    # object directly.
    configuration.attributes["database_url"] = sqlite_url_for_path(database_path)
    return configuration


def database_revision_state(
    database_path: Path,
    *,
    read_only: bool = False,
) -> tuple[set[str], set[str]]:
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    from backend.db.sqlite import validate_sqlite_database_file
    from backend.migrations.resources import current_migration_head

    del read_only  # Revision inspection is always enforced read-only.
    validate_sqlite_database_file(database_path)
    expected = {current_migration_head(resource_root())}
    if not database_path.exists() or database_path.stat().st_size == 0:
        return set(), expected

    database_uri = f"{database_path.resolve(strict=True).as_uri()}?mode=ro"

    def open_read_only_database():
        connection = sqlite3.connect(database_uri, uri=True, timeout=30)
        try:
            connection.execute("PRAGMA query_only=ON")
            state = connection.execute("PRAGMA query_only").fetchone()
            if state is None or int(state[0]) != 1:
                raise RuntimeError("SQLite did not enable read-only revision inspection")
            if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise RuntimeError("SQLite vault failed its quick integrity check")
            return connection
        except Exception:
            connection.close()
            raise

    engine = create_engine(
        "sqlite://",
        creator=open_read_only_database,
        poolclass=NullPool,
    )
    try:
        with engine.connect() as connection:
            current = set(MigrationContext.configure(connection).get_current_heads())
    finally:
        engine.dispose()
    return current, expected


def run_alembic_upgrade(database_path: Path) -> None:
    from alembic import command

    command.upgrade(_alembic_config(database_path), "head")


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _open_read_only_sqlite(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve(strict=True).as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA query_only").fetchone() != (1,):
            raise RuntimeError("SQLite did not enforce read-only backup access")
        return connection
    except Exception:
        connection.close()
        raise


def _validate_sqlite_image(connection: sqlite3.Connection, *, foreign_keys: bool) -> None:
    if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
        raise RuntimeError("SQLite vault failed its quick integrity check")
    if foreign_keys and connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("SQLite vault failed its foreign-key integrity check")


def _reserve_private_file(path: Path) -> None:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    os.close(descriptor)


def _sha256_file(path: Path) -> str:
    before = path.lstat()
    if (
        _is_link_like(path, before)
        or not stat.S_ISREG(before.st_mode)
        or int(getattr(before, "st_nlink", 1)) != 1
        or (
            os.name != "nt"
            and (
                int(before.st_uid) != _effective_user_id() or stat.S_IMODE(before.st_mode) != 0o600
            )
        )
    ):
        raise RuntimeError("Migration backup is not one private ordinary file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    if os.name != "nt":
        flags |= getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not os.path.samestat(before, opened)
            or not stat.S_ISREG(opened.st_mode)
            or int(getattr(opened, "st_nlink", 1)) != 1
            or (
                os.name != "nt"
                and (
                    int(opened.st_uid) != _effective_user_id()
                    or stat.S_IMODE(opened.st_mode) != 0o600
                )
            )
        ):
            raise RuntimeError("Migration backup changed while it was opened")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(descriptor)
        current = path.lstat()
        if (
            not os.path.samestat(opened, after)
            or not os.path.samestat(after, current)
            or _is_link_like(path, current)
            or not stat.S_ISREG(after.st_mode)
            or int(getattr(after, "st_nlink", 1)) != 1
            or after.st_size != opened.st_size
            or after.st_mtime_ns != opened.st_mtime_ns
            or after.st_ctime_ns != opened.st_ctime_ns
        ):
            raise RuntimeError("Migration backup changed while it was read")
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _migration_recovery_path(database_path: Path) -> Path:
    return database_path.parent / f".{database_path.name}.migration-recovery.json"


def _write_migration_recovery_marker(
    database_path: Path,
    backup_path: Path | None,
) -> Path:
    marker_path = _migration_recovery_path(database_path)
    try:
        marker_path.lstat()
    except FileNotFoundError:
        pass
    else:
        raise RuntimeError("A previous migration recovery marker must be resolved first")
    payload: dict[str, object] = {
        "schema_version": MIGRATION_RECOVERY_SCHEMA,
        "mode": "new" if backup_path is None else "backup",
    }
    if backup_path is not None:
        if _BACKUP_NAME.fullmatch(backup_path.name) is None:
            raise RuntimeError("Migration backup has a non-canonical filename")
        payload.update(
            {
                "backup_name": backup_path.name,
                "backup_sha256": _sha256_file(backup_path),
            }
        )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MIGRATION_RECOVERY_MAX_BYTES:
        raise RuntimeError("Migration recovery marker exceeds its size bound")
    temporary = marker_path.parent / f".{marker_path.name}.{secrets.token_hex(8)}.tmp"
    _reserve_private_file(temporary)
    try:
        with temporary.open("r+b") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, marker_path)
        _fsync_directory(marker_path.parent)
        return marker_path
    finally:
        temporary.unlink(missing_ok=True)


def _read_migration_recovery_marker(marker_path: Path) -> dict[str, object]:
    from backend.storage.atomic import read_stable_bounded_file

    before = marker_path.lstat()
    file_attributes = int(getattr(before, "st_file_attributes", 0))
    if (
        marker_path.is_symlink()
        or bool(file_attributes & 0x400)
        or not stat.S_ISREG(before.st_mode)
        or int(getattr(before, "st_nlink", 1)) != 1
        or not 1 <= before.st_size <= MIGRATION_RECOVERY_MAX_BYTES
        or (
            os.name != "nt"
            and (
                int(before.st_uid) != _effective_user_id() or stat.S_IMODE(before.st_mode) != 0o600
            )
        )
    ):
        raise RuntimeError("Migration recovery marker is not one private bounded file")
    encoded = read_stable_bounded_file(
        marker_path,
        maximum_size=MIGRATION_RECOVERY_MAX_BYTES,
    )
    current = marker_path.lstat()
    if (
        not os.path.samestat(before, current)
        or current.st_size != before.st_size
        or current.st_mtime_ns != before.st_mtime_ns
        or current.st_ctime_ns != before.st_ctime_ns
    ):
        raise RuntimeError("Migration recovery marker changed while it was read")
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Migration recovery marker is invalid") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Migration recovery marker is invalid")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if canonical != encoded:
        raise RuntimeError("Migration recovery marker is not canonical")
    mode = payload.get("mode")
    expected_keys = (
        {"schema_version", "mode"}
        if mode == "new"
        else {"schema_version", "mode", "backup_name", "backup_sha256"}
    )
    if (
        payload.get("schema_version") != MIGRATION_RECOVERY_SCHEMA
        or mode not in {"new", "backup"}
        or set(payload) != expected_keys
    ):
        raise RuntimeError("Migration recovery marker has an unsupported schema")
    if mode == "backup" and (
        not isinstance(payload.get("backup_name"), str)
        or _BACKUP_NAME.fullmatch(str(payload["backup_name"])) is None
        or not isinstance(payload.get("backup_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", str(payload["backup_sha256"])) is None
    ):
        raise RuntimeError("Migration recovery marker has invalid backup identity")
    return payload


def _clear_migration_recovery_marker(marker_path: Path) -> None:
    marker_path.unlink()
    _fsync_directory(marker_path.parent)


def _recover_interrupted_migration(database_path: Path, backup_directory: Path) -> None:
    from backend.db.sqlite import path_is_within, validate_sqlite_database_file

    marker_path = _migration_recovery_path(database_path)
    try:
        marker_path.lstat()
    except FileNotFoundError:
        return
    payload = _read_migration_recovery_marker(marker_path)
    if payload["mode"] == "new":
        _remove_sqlite_sidecars(database_path)
        database_path.unlink(missing_ok=True)
        _remove_sqlite_sidecars(database_path)
    else:
        backup_path = backup_directory / str(payload["backup_name"])
        if not path_is_within(backup_path, backup_directory):
            raise RuntimeError("Migration recovery backup escaped its directory")
        validate_sqlite_database_file(backup_path)
        if not backup_path.is_file() or _sha256_file(backup_path) != payload["backup_sha256"]:
            raise RuntimeError("Migration recovery backup is missing or has changed")
        _restore_database(database_path, backup_path)
    _clear_migration_recovery_marker(marker_path)


def _backup_database(database_path: Path, backup_directory: Path) -> Path:
    backup_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_directory / f"careeros-{timestamp}-{secrets.token_hex(4)}.db"
    _reserve_private_file(backup_path)
    try:
        with (
            closing(_open_read_only_sqlite(database_path)) as source,
            closing(sqlite3.connect(backup_path, timeout=30)) as destination,
        ):
            _validate_sqlite_image(source, foreign_keys=False)
            source.backup(destination)
            destination.commit()
            _validate_sqlite_image(destination, foreign_keys=False)
        _fsync_file(backup_path)
        _fsync_directory(backup_directory)
        return backup_path
    except Exception:
        backup_path.unlink(missing_ok=True)
        raise


def _remove_sqlite_sidecars(database_path: Path) -> None:
    for suffix in ("-journal", "-wal", "-shm"):
        Path(f"{database_path}{suffix}").unlink(missing_ok=True)


def _restore_database(database_path: Path, backup_path: Path) -> None:
    restore_path = database_path.parent / (
        f".{database_path.name}.restore-{secrets.token_hex(8)}.tmp"
    )
    _reserve_private_file(restore_path)
    try:
        with (
            closing(_open_read_only_sqlite(backup_path)) as source,
            closing(sqlite3.connect(restore_path, timeout=30)) as destination,
        ):
            _validate_sqlite_image(source, foreign_keys=False)
            source.backup(destination)
            destination.commit()
            _validate_sqlite_image(destination, foreign_keys=False)
        _fsync_file(restore_path)
        # No connection may survive the migration boundary. Removing every
        # SQLite journaling mode before replacement prevents stale frames from
        # being replayed against the restored main database.
        _remove_sqlite_sidecars(database_path)
        os.replace(restore_path, database_path)
        _remove_sqlite_sidecars(database_path)
        _fsync_directory(database_path.parent)
        with closing(_open_read_only_sqlite(database_path)) as restored:
            _validate_sqlite_image(restored, foreign_keys=False)
    finally:
        restore_path.unlink(missing_ok=True)


def _prune_backups(backup_directory: Path, *, keep: int = 5) -> None:
    backups = sorted(backup_directory.glob("careeros-*.db"), reverse=True)
    for expired in backups[keep:]:
        expired.unlink(missing_ok=True)


def migrate_database(database_path: Path, backup_directory: Path) -> Path | None:
    from alembic.script import ScriptDirectory

    from backend.db.sqlite import (
        ensure_sqlite_database_parent,
        sqlite_url_for_path,
        validate_sqlite_database_file,
        validate_sqlite_database_location,
    )
    from backend.migrations.runtime import migration_lock

    validate_sqlite_database_file(database_path)
    database_url = sqlite_url_for_path(database_path)
    backup_directory = backup_directory.resolve(strict=False)
    data_root = backup_directory.parent
    database_path = validate_sqlite_database_location(
        database_url,
        data_root=data_root,
    )
    validate_sqlite_database_file(database_path)
    with migration_lock(database_path):
        ensured_path = ensure_sqlite_database_parent(
            database_url,
            data_root=data_root,
        )
        if ensured_path != database_path:
            raise DesktopMigrationError("Desktop database path validation mismatch")
        try:
            _recover_interrupted_migration(database_path, backup_directory)
        except Exception as exc:
            raise DesktopMigrationError(
                "Interrupted migration could not be recovered; the vault was left untouched"
            ) from exc
        # A mode=new recovery removes the partial database. Reserve its private
        # replacement before any revision probe can ask SQLite to recreate it.
        ensure_sqlite_database_parent(database_url, data_root=data_root)
        validate_sqlite_database_file(database_path)
        current, expected = database_revision_state(database_path)
        if current == expected:
            return None
        if len(expected) != 1:
            raise DesktopMigrationError("Packaged migration history has no unique head")

        had_database = database_path.exists() and database_path.stat().st_size > 0
        if current:
            scripts = ScriptDirectory.from_config(_alembic_config(database_path))
            try:
                reachable = {
                    revision.revision
                    for revision in scripts.iterate_revisions(next(iter(expected)), "base")
                }
            except Exception as exc:
                raise DesktopMigrationError("Packaged migration history is invalid") from exc
            if not current <= reachable:
                raise DesktopMigrationError(
                    "Vault revision is not a supported ancestor; automatic downgrade is refused"
                )
            for revision in current:
                ancestors = {item.revision for item in scripts.iterate_revisions(revision, "base")}
                if (current - {revision}) & ancestors:
                    raise DesktopMigrationError(
                        "Vault revision frontier is internally inconsistent"
                    )
        elif had_database:
            with closing(_open_read_only_sqlite(database_path)) as connection:
                user_table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version' LIMIT 1"
                ).fetchone()
            if user_table is not None:
                raise DesktopMigrationError(
                    "Populated vault has no Alembic revision; automatic initialization is refused"
                )

        try:
            backup_path = (
                _backup_database(database_path, backup_directory) if had_database else None
            )
        except Exception as exc:
            raise DesktopMigrationError(
                "Desktop migration backup failed; the vault was left untouched"
            ) from exc
        try:
            marker_path = _write_migration_recovery_marker(database_path, backup_path)
        except Exception as exc:
            raise DesktopMigrationError(
                "Migration recovery journal could not be created; the vault was left untouched"
            ) from exc
        try:
            run_alembic_upgrade(database_path)
            migrated, target = database_revision_state(database_path)
            if migrated != target:
                raise RuntimeError("Schema revision did not reach the expected head")
            with closing(_open_read_only_sqlite(database_path)) as migrated_database:
                _validate_sqlite_image(migrated_database, foreign_keys=True)
        except Exception as exc:
            if backup_path is not None:
                try:
                    _restore_database(database_path, backup_path)
                except Exception as restore_exc:
                    raise DesktopMigrationError(
                        "Desktop migration and automatic restore failed; verified backup was preserved"
                    ) from restore_exc
                _clear_migration_recovery_marker(marker_path)
                raise DesktopMigrationError(
                    "Desktop database migration failed; the previous vault was restored"
                ) from exc
            _remove_sqlite_sidecars(database_path)
            database_path.unlink(missing_ok=True)
            _remove_sqlite_sidecars(database_path)
            _clear_migration_recovery_marker(marker_path)
            raise DesktopMigrationError(
                "Desktop database migration failed before the vault was initialized"
            ) from exc
        _clear_migration_recovery_marker(marker_path)
        _prune_backups(backup_directory)
        return backup_path


def run_server(configured: ConfiguredDesktop) -> None:
    import uvicorn

    from backend.api.routes.desktop import desktop_shutdown_controller

    server_configuration = uvicorn.Config(
        "backend.main:app",
        host=configured.arguments.host,
        port=configured.arguments.port,
        workers=1,
        reload=False,
        access_log=False,
        server_header=False,
        proxy_headers=False,
        log_level="info",
        timeout_graceful_shutdown=UVICORN_GRACEFUL_SHUTDOWN_SECONDS,
    )
    server = uvicorn.Server(server_configuration)
    shutdown_complete = threading.Event()

    def request_shutdown() -> None:
        # Uvicorn polls this flag on its event loop. Assignment is atomic in
        # CPython and avoids delivering an OS signal from a watchdog thread.
        server.should_exit = True

    start_parent_watchdog(
        configured.arguments.parent_pid,
        request_shutdown=request_shutdown,
        shutdown_complete=shutdown_complete,
    )
    try:
        with desktop_shutdown_controller.bind(request_shutdown):
            server.run()
    finally:
        shutdown_complete.set()


def parent_process_is_alive(process_id: int) -> bool:
    if process_id <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        synchronize = 0x00100000
        wait_timeout = 0x00000102
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return False
        kernel32 = windll.kernel32
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(synchronize, False, process_id)
        if not handle:
            return False
        try:
            return bool(kernel32.WaitForSingleObject(handle, 0) == wait_timeout)
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(process_id, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def start_parent_watchdog(
    process_id: int,
    *,
    request_shutdown: Callable[[], None],
    shutdown_complete: threading.Event,
    interval_seconds: float = 0.5,
    hard_timeout_seconds: float = PARENT_WATCHDOG_HARD_TIMEOUT_SECONDS,
    parent_probe: Callable[[int], bool] = parent_process_is_alive,
    force_exit: Callable[[int], None] = os._exit,
) -> threading.Thread:
    """Drain Uvicorn after native-parent death, then enforce a hard bound.

    The native shell normally requests the authenticated HTTP shutdown first.
    This watchdog covers crashes and forced parent termination without skipping
    FastAPI lifespan cleanup during the recoverable path.
    """

    if interval_seconds <= 0 or hard_timeout_seconds <= 0:
        raise ValueError("Watchdog timing values must be positive")

    def monitor() -> None:
        while parent_probe(process_id):
            time.sleep(interval_seconds)
        try:
            request_shutdown()
        except Exception:
            force_exit(1)
            return
        if not shutdown_complete.wait(timeout=hard_timeout_seconds):
            force_exit(1)

    thread = threading.Thread(name="careeros-parent-watchdog", target=monitor, daemon=True)
    thread.start()
    return thread


def main(argv: Sequence[str] | None = None) -> int:
    configured = configure_environment(parse_args(argv))
    from backend.desktop.lifecycle import desktop_instance_lease

    with desktop_instance_lease(root=configured.arguments.data_dir):
        migrate_database(configured.database_path, configured.backup_directory)
        run_server(configured)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
