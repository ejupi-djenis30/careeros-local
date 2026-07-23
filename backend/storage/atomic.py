import errno
import hashlib
import os
import re
import tempfile
from pathlib import Path

from backend.core.config import settings


class StorageWriteError(RuntimeError):
    """A local durable write failed before it could be committed atomically."""


_STORAGE_ERRNOS = {errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)}
_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:")


def is_storage_exhaustion(error: BaseException) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, OSError) and current.errno in _STORAGE_ERRNOS:
            return True
        message = str(current).casefold()
        if any(
            marker in message
            for marker in ("database or disk is full", "disk is full", "no space left")
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def data_root() -> Path:
    root = Path(settings.DATA_DIR).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_data_path(relative_path: str | Path) -> Path:
    raw_path = relative_path.as_posix() if isinstance(relative_path, Path) else relative_path
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("Stored paths must be non-empty relative paths")
    if "\x00" in raw_path:
        raise ValueError("Stored paths cannot contain null bytes")
    if "\\" in raw_path:
        raise ValueError("Stored paths must use portable forward-slash separators")
    if raw_path.startswith("/") or _WINDOWS_DRIVE_PATH.match(raw_path):
        raise ValueError("Stored paths must be relative to the local data directory")

    parts = raw_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Stored paths must be normalized and cannot contain traversal")

    root = data_root()
    root_real = os.path.realpath(os.fspath(root))
    try:
        resolved = os.path.realpath(os.path.join(root_real, *parts))
    except OSError as exc:
        raise ValueError("Stored path escapes the local data directory") from exc
    root_prefix = root_real.rstrip(os.sep) + os.sep
    if not resolved.startswith(root_prefix):
        raise ValueError("Stored path escapes the local data directory")
    try:
        common = os.path.commonpath((root_real, resolved))
    except ValueError as exc:
        raise ValueError("Stored path escapes the local data directory") from exc
    if os.path.normcase(common) != os.path.normcase(root_real):
        raise ValueError("Stored path escapes the local data directory")
    return Path(resolved)


def atomic_write(relative_path: str | Path, data: bytes) -> tuple[Path, bool]:
    temporary_name: str | None = None
    try:
        destination = resolve_data_path(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != data:
                raise ValueError("Existing stored file does not match the requested content")
            return destination, False

        handle, temporary_name = tempfile.mkstemp(prefix=".write-", dir=destination.parent)
        with os.fdopen(handle, "wb") as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, destination)
        return destination, True
    except OSError as exc:
        try:
            if temporary_name is not None:
                os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise StorageWriteError(
            "Local storage write failed; verify free disk space and folder access, then retry."
        ) from exc
    except Exception:
        try:
            if temporary_name is not None:
                os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def read_verified(relative_path: str | Path, expected_sha256: str) -> bytes:
    source = resolve_data_path(relative_path)
    data = source.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise ValueError("Stored file failed its integrity check")
    return data
