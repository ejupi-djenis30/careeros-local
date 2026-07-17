import hashlib
import os
import tempfile
from pathlib import Path

from backend.core.config import settings


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
    destination = resolve_data_path(relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != data:
            raise ValueError("Existing stored file does not match the requested content")
        return destination, False

    handle, temporary_name = tempfile.mkstemp(prefix=".write-", dir=destination.parent)
    try:
        with os.fdopen(handle, "wb") as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, destination)
        return destination, True
    except Exception:
        try:
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
