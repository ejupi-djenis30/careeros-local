"""Per-account protection for sensitive password reauthentication."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(slots=True)
class _FailureState:
    failures: int
    first_failure_at: float
    locked_until: float | None = None


class AccountReauthenticationGuard:
    """Bound repeated password failures without blocking emergency revocation.

    CareerOS Local runs as a single local application process, so an in-memory,
    per-account guard avoids leaking one account's failures to another account
    or trusting a client-controlled network address.
    """

    def __init__(
        self,
        *,
        max_failures: int = 5,
        failure_window_seconds: int = 15 * 60,
        lockout_seconds: int = 15 * 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_failures < 1 or failure_window_seconds < 1 or lockout_seconds < 1:
            raise ValueError("Reauthentication guard limits must be positive")
        self._max_failures = max_failures
        self._failure_window_seconds = failure_window_seconds
        self._lockout_seconds = lockout_seconds
        self._clock = clock
        self._states: dict[int, _FailureState] = {}
        self._lock = threading.Lock()
        self._verification_locks: dict[int, threading.Lock] = {}

    @contextmanager
    def serialize_verification(self, user_id: int) -> Iterator[None]:
        """Allow only one password verification at a time for an account."""
        with self._lock:
            account_lock = self._verification_locks.setdefault(
                user_id,
                threading.Lock(),
            )
        with account_lock:
            yield

    def retry_after(self, user_id: int) -> int | None:
        """Return the remaining account lockout, or ``None`` when issuance is allowed."""
        now = self._clock()
        with self._lock:
            state = self._active_state(user_id, now)
            if state is None or state.locked_until is None:
                return None
            return max(1, math.ceil(state.locked_until - now))

    def register_failure(self, user_id: int) -> int | None:
        """Record a failed reauthentication and return any resulting lockout."""
        now = self._clock()
        with self._lock:
            state = self._active_state(user_id, now)
            if state is None:
                state = _FailureState(failures=0, first_failure_at=now)
                self._states[user_id] = state
            state.failures += 1
            if state.failures >= self._max_failures:
                state.locked_until = now + self._lockout_seconds
                return self._lockout_seconds
            return None

    def register_success(self, user_id: int) -> None:
        """Clear failures after a successful password verification."""
        with self._lock:
            self._states.pop(user_id, None)

    def reset(self) -> None:
        """Clear state for deterministic application tests."""
        with self._lock:
            self._states.clear()

    def _active_state(self, user_id: int, now: float) -> _FailureState | None:
        state = self._states.get(user_id)
        if state is None:
            return None
        if state.locked_until is not None:
            if state.locked_until > now:
                return state
            self._states.pop(user_id, None)
            return None
        if now - state.first_failure_at < self._failure_window_seconds:
            return state
        self._states.pop(user_id, None)
        return None
