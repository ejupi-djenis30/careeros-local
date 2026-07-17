import errno
import hashlib
import os
import tempfile
from pathlib import Path

from backend.core.config import settings


class StorageWriteError(RuntimeError):
    """A local durable write failed before it could be committed atomically."""


_STORAGE_ERRNOS = {errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)}


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
    relative = Path(relative_path)
    if relative.is_absolute():
        raise ValueError("Stored paths must be relative to the local data directory")
    root = data_root()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Stored path escapes the local data directory")
    return resolved


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
