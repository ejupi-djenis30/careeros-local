from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import BinaryIO, Iterator

from backend.storage.atomic import data_root


class VaultLockTimeout(TimeoutError):
    """Raised when another desktop operation owns the vault lock for too long."""


class DesktopInstanceAlreadyRunning(RuntimeError):
    """Raised when another CareerOS desktop sidecar already owns the vault."""


_process_lock = RLock()
_instance_lock = RLock()


def _try_lock(handle: BinaryIO) -> bool:
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(  # type: ignore[attr-defined]
                handle.fileno(), msvcrt.LK_NBLCK, 1  # type: ignore[attr-defined]
            )
        else:
            import fcntl

            fcntl.flock(  # type: ignore[attr-defined]
                handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB  # type: ignore[attr-defined]
            )
    except OSError:
        return False
    return True


def _unlock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(  # type: ignore[attr-defined]
            handle.fileno(), msvcrt.LK_UNLCK, 1  # type: ignore[attr-defined]
        )
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


@contextmanager
def desktop_vault_lock(
    *, timeout_seconds: float = 15.0, root: Path | None = None
) -> Iterator[None]:
    """Serialize backup, restore and erasure across processes and threads."""

    if timeout_seconds <= 0:
        raise ValueError("Vault lock timeout must be positive")
    vault_root = (root or data_root()) / "vault"
    vault_root.mkdir(parents=True, exist_ok=True)
    lock_path = vault_root / ".vault.lock"
    deadline = time.monotonic() + timeout_seconds

    remaining = max(0.0, deadline - time.monotonic())
    if not _process_lock.acquire(timeout=remaining):
        raise VaultLockTimeout("The local career vault is busy")
    try:
        handle = lock_path.open("a+b")
    except Exception:
        _process_lock.release()
        raise
    try:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        while not _try_lock(handle):
            if time.monotonic() >= deadline:
                raise VaultLockTimeout("The local career vault is busy")
            time.sleep(0.05)
        try:
            yield
        finally:
            _unlock(handle)
    finally:
        handle.close()
        _process_lock.release()


@contextmanager
def desktop_instance_lease(*, root: Path | None = None) -> Iterator[None]:
    """Hold a process-lifetime writer lease without blocking vault maintenance operations."""

    vault_root = (root or data_root()) / "vault"
    vault_root.mkdir(parents=True, exist_ok=True)
    lock_path = vault_root / ".instance.lock"
    if not _instance_lock.acquire(blocking=False):
        raise DesktopInstanceAlreadyRunning("CareerOS Local is already using this career vault")
    try:
        handle = lock_path.open("a+b")
    except Exception:
        _instance_lock.release()
        raise
    try:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        if not _try_lock(handle):
            raise DesktopInstanceAlreadyRunning(
                "CareerOS Local is already using this career vault"
            )
        try:
            yield
        finally:
            _unlock(handle)
    finally:
        handle.close()
        _instance_lock.release()
