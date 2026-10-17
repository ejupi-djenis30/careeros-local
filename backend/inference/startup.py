"""Short, caller-locked startup ownership and bounded child termination."""

from __future__ import annotations

import subprocess
import threading
from typing import Protocol


class CancellationSignal(Protocol):
    def is_set(self) -> bool: ...


class StartupLease:
    def __init__(self, generation: int, external: threading.Event | None) -> None:
        self.generation = generation
        self._external = external
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def is_set(self) -> bool:
        return self._cancelled.is_set() or (self._external is not None and self._external.is_set())


class StartupOwnership:
    """All methods run under the owning runtime's short status lock."""

    def __init__(self) -> None:
        self._generation = 0
        self._current: StartupLease | None = None

    def begin(self, external: threading.Event | None) -> StartupLease:
        if self._current is not None and not self._current.is_set():
            raise RuntimeError("a managed runtime startup is already running")
        self._generation += 1
        lease = StartupLease(self._generation, external)
        self._current = lease
        return lease

    def matches(self, lease: StartupLease) -> bool:
        return self._current is lease and self._generation == lease.generation

    def owns(self, lease: StartupLease) -> bool:
        return self.matches(lease) and not lease.is_set()

    def cancel(self) -> None:
        if self._current is not None:
            self._current.cancel()
        self._current = None
        self._generation += 1

    def finish(self, lease: StartupLease) -> None:
        if self.matches(lease):
            self._current = None


def terminate_process(process: subprocess.Popen[bytes]) -> None:
    """Reap only this child; the caller retains its handle on failure."""
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        if process.poll() is None:
            raise
    if process.poll() is None:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
