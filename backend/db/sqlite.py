"""Canonical SQLite URL and filesystem boundary helpers."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


class SQLiteConfigurationError(ValueError):
    """Raised when the local vault URL cannot name one ordinary SQLite file."""


_SQLITE_SIDECAR_SUFFIXES = ("-journal", "-wal", "-shm")
_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600


def sqlite_database_path(database_url: str | URL) -> Path | None:
    """Return a canonical SQLite path, or ``None`` for an in-memory database.

    CareerOS deliberately does not accept SQLite URI filenames for its primary
    vault. URI query flags can silently select read-only, immutable or shared
    cache behavior and make lock/sidecar ownership ambiguous. Read-only
    automation uses an explicit ``sqlite3`` creator instead.
    """

    try:
        url = database_url if isinstance(database_url, URL) else make_url(database_url)
    except (ArgumentError, TypeError, ValueError) as exc:
        raise SQLiteConfigurationError("DATABASE_URL must be a valid SQLite URL") from exc
    if url.get_backend_name() != "sqlite":
        raise SQLiteConfigurationError("CareerOS supports only a local SQLite DATABASE_URL")
    if url.username is not None or url.password is not None or url.host is not None or url.port:
        raise SQLiteConfigurationError("SQLite DATABASE_URL must not contain network authority")
    if url.query:
        raise SQLiteConfigurationError("SQLite DATABASE_URL must not contain URI query options")
    database = url.database
    if database in {None, "", ":memory:"}:
        if database == ":memory:":
            return None
        raise SQLiteConfigurationError("SQLite DATABASE_URL must name a database file")
    if database.startswith("file:"):
        raise SQLiteConfigurationError("SQLite URI filenames are not accepted for the vault")
    if "?" in database:
        raise SQLiteConfigurationError("SQLite database path contains ambiguous URL punctuation")
    if any(ord(character) < 32 or ord(character) == 127 for character in database):
        raise SQLiteConfigurationError("SQLite database path contains control characters")
    candidate = Path(database).expanduser()
    # Reject a final-component alias before canonicalization can hide it. Parent
    # aliases are resolved deliberately; the canonical parent is hardened below.
    validate_sqlite_database_file(candidate)
    resolved = candidate.resolve(strict=False)
    validate_sqlite_database_file(resolved)
    return resolved


def sqlite_url_for_path(database_path: Path) -> URL:
    """Build a SQLAlchemy URL object without reparsing path punctuation."""

    path = database_path.expanduser().resolve(strict=False)
    return URL.create("sqlite", database=str(path))


def validate_sqlite_database_location(
    database_url: str | URL,
    *,
    data_root: Path,
) -> Path:
    """Validate one canonical vault location without changing the filesystem."""

    database_path = sqlite_database_path(database_url)
    if database_path is None:
        raise SQLiteConfigurationError("SQLite vault must use a file-backed database")
    canonical_root = data_root.expanduser().resolve(strict=False)
    try:
        database_path.relative_to(canonical_root)
    except ValueError as exc:
        raise SQLiteConfigurationError(
            "SQLite vault must stay inside its configured data root"
        ) from exc
    if database_path == canonical_root:
        raise SQLiteConfigurationError("SQLite vault must stay inside its configured data root")
    return database_path


def _is_link_like(_path: Path, metadata: os.stat_result) -> bool:
    file_attributes = int(getattr(metadata, "st_file_attributes", 0))
    return stat.S_ISLNK(metadata.st_mode) or bool(file_attributes & 0x400)


def _effective_user_id() -> int:
    get_effective_user_id = getattr(os, "geteuid", None)
    if get_effective_user_id is None:
        raise SQLiteConfigurationError("POSIX vault ownership checks are unavailable")
    return int(get_effective_user_id())


def _required_open_flag(name: str) -> int:
    value = int(getattr(os, name, 0))
    if value == 0:
        raise SQLiteConfigurationError(f"POSIX vault protection requires {name}")
    return value


def _secure_descriptor_mode(descriptor: int, mode: int) -> None:
    change_mode = getattr(os, "fchmod", None)
    if change_mode is None:
        raise SQLiteConfigurationError("POSIX descriptor permission repair is unavailable")
    change_mode(descriptor, mode)


def _secure_posix_database_parent(parent: Path) -> None:
    """Repair one canonical vault parent without following its final component."""

    if os.name == "nt":
        return
    try:
        before = parent.lstat()
    except OSError as exc:
        raise SQLiteConfigurationError("SQLite vault parent could not be inspected") from exc
    owner = _effective_user_id()
    if (
        _is_link_like(parent, before)
        or not stat.S_ISDIR(before.st_mode)
        or int(before.st_uid) != owner
    ):
        raise SQLiteConfigurationError("SQLite vault parent must be an owned ordinary directory")

    flags = (
        os.O_RDONLY
        | _required_open_flag("O_DIRECTORY")
        | _required_open_flag("O_NOFOLLOW")
        | int(getattr(os, "O_CLOEXEC", 0))
    )
    try:
        descriptor = os.open(parent, flags)
    except OSError as exc:
        raise SQLiteConfigurationError("SQLite vault parent changed while it was opened") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not os.path.samestat(before, opened)
            or not stat.S_ISDIR(opened.st_mode)
            or int(opened.st_uid) != owner
        ):
            raise SQLiteConfigurationError("SQLite vault parent changed while it was opened")
        _secure_descriptor_mode(descriptor, _PRIVATE_DIRECTORY_MODE)
        secured = os.fstat(descriptor)
        if (
            not os.path.samestat(opened, secured)
            or int(secured.st_uid) != owner
            or stat.S_IMODE(secured.st_mode) != _PRIVATE_DIRECTORY_MODE
        ):
            raise SQLiteConfigurationError("SQLite vault parent permissions are not private")
        try:
            current = parent.lstat()
        except OSError as exc:
            raise SQLiteConfigurationError(
                "SQLite vault parent changed while it was secured"
            ) from exc
        if (
            _is_link_like(parent, current)
            or not stat.S_ISDIR(current.st_mode)
            or not os.path.samestat(secured, current)
        ):
            raise SQLiteConfigurationError("SQLite vault parent changed while it was secured")
    finally:
        os.close(descriptor)


def _secure_posix_regular_file(path: Path, *, required: bool, label: str) -> None:
    """Validate and repair one owned file before SQLite opens any handle."""

    if os.name == "nt":
        return
    try:
        before = path.lstat()
    except FileNotFoundError:
        if required:
            raise SQLiteConfigurationError(f"SQLite {label} file is missing") from None
        return
    except OSError as exc:
        raise SQLiteConfigurationError(f"SQLite {label} file could not be inspected") from exc

    owner = _effective_user_id()
    if (
        _is_link_like(path, before)
        or not stat.S_ISREG(before.st_mode)
        or int(before.st_uid) != owner
        or int(getattr(before, "st_nlink", 1)) != 1
    ):
        raise SQLiteConfigurationError(f"SQLite {label} must be an owned, unaliased ordinary file")

    # O_NONBLOCK prevents a final-component regular-file-to-FIFO race from
    # blocking before fstat can reject the replacement.
    flags = (
        os.O_RDONLY
        | _required_open_flag("O_NOFOLLOW")
        | _required_open_flag("O_NONBLOCK")
        | int(getattr(os, "O_CLOEXEC", 0))
    )
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        if required:
            raise SQLiteConfigurationError(f"SQLite {label} file is missing") from None
        return
    except OSError as exc:
        raise SQLiteConfigurationError(f"SQLite {label} changed while it was opened") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not os.path.samestat(before, opened)
            or not stat.S_ISREG(opened.st_mode)
            or int(opened.st_uid) != owner
            or int(getattr(opened, "st_nlink", 1)) != 1
        ):
            raise SQLiteConfigurationError(f"SQLite {label} changed while it was opened")
        _secure_descriptor_mode(descriptor, _PRIVATE_FILE_MODE)
        secured = os.fstat(descriptor)
        if (
            not os.path.samestat(opened, secured)
            or int(secured.st_uid) != owner
            or int(getattr(secured, "st_nlink", 1)) != 1
            or stat.S_IMODE(secured.st_mode) != _PRIVATE_FILE_MODE
        ):
            raise SQLiteConfigurationError(f"SQLite {label} permissions are not private")
        try:
            current = path.lstat()
        except FileNotFoundError:
            if not required:
                return
            raise SQLiteConfigurationError(f"SQLite {label} changed while it was secured") from None
        except OSError as exc:
            raise SQLiteConfigurationError(f"SQLite {label} changed while it was secured") from exc
        if (
            _is_link_like(path, current)
            or not stat.S_ISREG(current.st_mode)
            or not os.path.samestat(secured, current)
            or int(getattr(current, "st_nlink", 1)) != 1
        ):
            raise SQLiteConfigurationError(f"SQLite {label} changed while it was secured")
    finally:
        os.close(descriptor)


def _create_private_posix_database(database_path: Path) -> None:
    """Reserve a new vault privately before SQLite can acquire process locks."""

    if os.name == "nt":
        return
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | _required_open_flag("O_NOFOLLOW")
        | int(getattr(os, "O_CLOEXEC", 0))
    )
    try:
        descriptor = os.open(database_path, flags, _PRIVATE_FILE_MODE)
    except FileExistsError:
        return
    except OSError as exc:
        raise SQLiteConfigurationError("SQLite vault could not be created privately") from exc
    try:
        metadata = os.fstat(descriptor)
        owner = _effective_user_id()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or int(metadata.st_uid) != owner
            or int(getattr(metadata, "st_nlink", 1)) != 1
        ):
            raise SQLiteConfigurationError("SQLite vault creation returned an unsafe file")
        _secure_descriptor_mode(descriptor, _PRIVATE_FILE_MODE)
        secured = os.fstat(descriptor)
        if (
            not os.path.samestat(metadata, secured)
            or int(secured.st_uid) != owner
            or int(getattr(secured, "st_nlink", 1)) != 1
            or stat.S_IMODE(secured.st_mode) != _PRIVATE_FILE_MODE
        ):
            raise SQLiteConfigurationError("SQLite vault permissions are not private")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def secure_sqlite_database_files(database_path: Path, *, require_database: bool) -> None:
    """Harden files before SQLite opens them and starts POSIX lock tracking.

    Closing an unrelated descriptor for a file can release every POSIX record
    lock that this process holds for that inode. Call this only during bootstrap,
    before any SQLite connection exists; connection hooks use the lstat-only
    validator below.
    """

    if os.name == "nt":
        return
    _secure_posix_regular_file(
        database_path,
        required=require_database,
        label="vault",
    )
    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        _secure_posix_regular_file(
            Path(f"{database_path}{suffix}"),
            required=False,
            label=f"{suffix[1:]} sidecar",
        )


def _validate_posix_runtime_file(path: Path, *, required: bool, label: str) -> None:
    """Validate one runtime file without opening a lock-disrupting descriptor."""

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if required:
            raise SQLiteConfigurationError(f"SQLite {label} file is missing") from None
        return
    except OSError as exc:
        raise SQLiteConfigurationError(f"SQLite {label} file could not be inspected") from exc
    if (
        _is_link_like(path, metadata)
        or not stat.S_ISREG(metadata.st_mode)
        or int(metadata.st_uid) != _effective_user_id()
        or int(getattr(metadata, "st_nlink", 1)) != 1
        or stat.S_IMODE(metadata.st_mode) != _PRIVATE_FILE_MODE
    ):
        raise SQLiteConfigurationError(
            f"SQLite {label} must be a private, owned, unaliased ordinary file"
        )


def validate_sqlite_runtime_files(database_path: Path) -> None:
    """Revalidate POSIX vault entries without disturbing SQLite fcntl locks."""

    if os.name == "nt":
        return
    _validate_posix_runtime_file(database_path, required=True, label="vault")
    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        _validate_posix_runtime_file(
            Path(f"{database_path}{suffix}"),
            required=False,
            label=f"{suffix[1:]} sidecar",
        )


def validate_sqlite_database_file(database_path: Path) -> None:
    """Reject aliases and special files that break SQLite sidecar ownership."""

    try:
        metadata = database_path.lstat()
    except FileNotFoundError:
        return
    if _is_link_like(database_path, metadata) or not stat.S_ISREG(metadata.st_mode):
        raise SQLiteConfigurationError("SQLite vault must be an ordinary non-linked file")
    if int(getattr(metadata, "st_nlink", 1)) != 1:
        raise SQLiteConfigurationError("SQLite vault must not have filesystem hard-link aliases")


def ensure_sqlite_database_parent(
    database_url: str | URL,
    *,
    data_root: Path | None = None,
) -> Path | None:
    """Create and harden the in-scope directory chain before SQLite opens."""

    if data_root is None:
        database_path = sqlite_database_path(database_url)
        if database_path is None:
            return None
        private_directories = [database_path.parent]
    else:
        database_path = validate_sqlite_database_location(
            database_url,
            data_root=data_root,
        )
        canonical_root = data_root.expanduser().resolve(strict=False)
        relative_parent = database_path.parent.relative_to(canonical_root)
        private_directories = [canonical_root]
        current = canonical_root
        for component in relative_parent.parts:
            current /= component
            private_directories.append(current)
    database_path.parent.mkdir(
        mode=_PRIVATE_DIRECTORY_MODE,
        parents=True,
        exist_ok=True,
    )
    for directory in private_directories:
        _secure_posix_database_parent(directory)
    _create_private_posix_database(database_path)
    validate_sqlite_database_file(database_path)
    if os.name != "nt":
        try:
            validate_sqlite_runtime_files(database_path)
        except SQLiteConfigurationError:
            # Bootstrap is the only safe point for descriptor-based repair.
            # Already-private files stay on the lstat-only fast path so a
            # repeated Alembic command cannot disturb an idle SQLite handle.
            secure_sqlite_database_files(database_path, require_database=True)
            validate_sqlite_runtime_files(database_path)
    return database_path


def path_is_within(path: Path, root: Path) -> bool:
    """Return whether canonical ``path`` is strictly inside canonical ``root``."""

    resolved_path = path.expanduser().resolve(strict=False)
    resolved_root = root.expanduser().resolve(strict=False)
    return resolved_path != resolved_root and resolved_path.is_relative_to(resolved_root)
