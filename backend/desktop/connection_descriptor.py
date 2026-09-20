"""Bounded token-free desktop discovery. This reader deliberately uses only stdlib."""

from __future__ import annotations

import json
import os
import re
import stat
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from desktop.connection_security import (
    checked_path,
    secure_private,
    verify_private,
)
from desktop.process_identity import process_identity

MAX_BYTES = 4096
LIFETIME_SECONDS = 30
RELATIVE_PATH = Path("mcp") / "connection.json"
_KEYS = {
    "schema_version",
    "api_base_url",
    "instance_id",
    "pid",
    "process_start",
    "issued_at",
    "expires_at",
}
_URL = re.compile(r"http://(?:127\.0\.0\.1|\[::1\]):([1-9][0-9]{0,4})/api/v1\Z")


class DescriptorError(ValueError):
    """Connection metadata is unavailable, stale or unsafe (no private details)."""


@dataclass(frozen=True)
class ConnectionDescriptor:
    api_base_url: str
    instance_id: str
    pid: int
    process_start: str
    issued_at: int
    expires_at: int
    schema_version: int = 1


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DescriptorError("Duplicate descriptor fields")
        result[key] = value
    return result


def _decode(data: bytes, *, fresh: bool) -> ConnectionDescriptor:
    payload = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
    if not isinstance(payload, dict) or set(payload) != _KEYS:
        raise DescriptorError("Unsupported descriptor schema")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise DescriptorError("Unsupported descriptor schema")
    url = payload["api_base_url"]
    match = _URL.fullmatch(url) if isinstance(url, str) else None
    if not match or int(match[1]) > 65535:
        raise DescriptorError("Invalid descriptor address")
    identity = payload["instance_id"]
    if not isinstance(identity, str) or str(uuid.UUID(identity)) != identity:
        raise DescriptorError("Invalid descriptor instance")
    if any(type(payload[key]) is not int for key in ("pid", "issued_at", "expires_at")):
        raise DescriptorError("Invalid descriptor timestamps")
    if not 0 < payload["pid"] <= 0xFFFFFFFF:
        raise DescriptorError("Invalid descriptor process")
    start = payload["process_start"]
    if not isinstance(start, str) or not 1 <= len(start) <= 128 or not start.isascii():
        raise DescriptorError("Invalid descriptor process")
    now = int(time.time())
    if (
        not 0 < payload["expires_at"] - payload["issued_at"] <= LIFETIME_SECONDS
        or payload["issued_at"] > now + 2
    ):
        raise DescriptorError("Invalid descriptor lifetime")
    if fresh and (payload["expires_at"] <= now or process_identity(payload["pid"]) != start):
        raise DescriptorError("Desktop connection has expired")
    return ConnectionDescriptor(**payload)


def read_connection_descriptor(value: str | Path, *, fresh: bool = True) -> ConnectionDescriptor:
    try:
        path = checked_path(value)
        verify_private(path.parent, path.parent.lstat())
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= MAX_BYTES:
            raise DescriptorError("Descriptor is not a bounded file")
        verify_private(path, metadata)
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            opened = os.fstat(descriptor)
            if not os.path.samestat(metadata, opened) or opened.st_nlink != 1:
                raise DescriptorError("Descriptor changed while opening")
            data = os.read(descriptor, MAX_BYTES + 1)
            if len(data) > MAX_BYTES or not os.path.samestat(opened, checked_path(path).lstat()):
                raise DescriptorError("Descriptor changed while reading")
            verify_private(path, path.lstat())
            return _decode(data, fresh=fresh)
        finally:
            os.close(descriptor)
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        raise DescriptorError(
            "CareerOS connection metadata is unavailable, stale or unsafe"
        ) from None


def publish_connection_descriptor(root: Path, url: str, instance_id: str) -> Path:
    from dataclasses import asdict

    parent = checked_path(root) / RELATIVE_PATH.parent
    try:
        parent.mkdir(mode=0o700)
    except FileExistsError:
        pass
    else:
        secure_private(parent)
    checked_path(parent)
    verify_private(parent, parent.lstat())
    path = checked_path(parent / RELATIVE_PATH.name, exists=False)
    if path.exists():
        read_connection_descriptor(path, fresh=False)
    now = int(time.time())
    data = json.dumps(
        asdict(
            ConnectionDescriptor(
                url,
                instance_id,
                os.getpid(),
                process_identity(os.getpid()),
                now,
                now + LIFETIME_SECONDS,
            )
        ),
        separators=(",", ":"),
    ).encode("utf-8")
    _decode(data, fresh=True)
    temporary = parent / f".connection-{uuid.uuid4()}.tmp"
    descriptor = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600
    )
    try:
        secure_private(temporary)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        checked_path(path, exists=False)
        _replace_connection(temporary, path)
        if os.name != "nt":
            directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        return path
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _replace_connection(temporary: Path, path: Path) -> None:
    # Windows may deny replacing a file during a concurrent bounded read. Keep
    # the old complete descriptor, then retry briefly after the reader closes.
    deadline = time.monotonic() + 0.5
    while True:
        checked_path(path, exists=False)
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if os.name != "nt" or time.monotonic() >= deadline:
                raise
            time.sleep(0.01)


def invalidate_connection_descriptor(path: Path, instance_id: str) -> None:
    try:
        current = read_connection_descriptor(path, fresh=False)
    except DescriptorError:
        return
    if current.instance_id == instance_id:
        path.unlink(missing_ok=True)
