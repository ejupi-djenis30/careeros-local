"""Lightweight async circuit breaker for external service calls.

States:
  CLOSED     — normal operation; requests pass through
  OPEN       — breaker tripped; requests fail fast with CircuitOpenError
  HALF_OPEN  — one probe call allowed to test recovery

Usage::

    cb = CircuitBreaker("groq", failure_threshold=5, recovery_seconds=60)

    try:
        result = await cb.call(provider.generate_json_async(sys_p, usr_p))
    except CircuitOpenError:
        # Service is down — handle gracefully (skip, fallback, etc.)
        ...
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Awaitable

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a circuit breaker is in the OPEN state."""

    def __init__(self, service: str, retry_after: float):
        self.service = service
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker OPEN for '{service}'. "
            f"Retry after {retry_after:.0f}s."
        )


class CircuitBreaker:
    """Thread-safe async circuit breaker for a single named service."""

    def __init__(
        self,
        service: str,
        *,
        failure_threshold: int = 5,
        recovery_seconds: float = 60.0,
    ) -> None:
        self._service = service
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds

        self._state = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    # ── public API ─────────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    async def call(self, coro: Awaitable[Any]) -> Any:
        """Execute *coro* guarded by the circuit breaker.

        Raises:
            CircuitOpenError: when the breaker is OPEN and the recovery
                window has not elapsed.
        """
        async with self._lock:
            await self._maybe_transition_to_half_open()

            if self._state == CircuitState.OPEN:
                retry_after = self._recovery_seconds - (time.monotonic() - self._last_failure_time)
                raise CircuitOpenError(self._service, max(0.0, retry_after))

            was_half_open = self._state == CircuitState.HALF_OPEN

        try:
            result = await coro
        except Exception as exc:
            async with self._lock:
                self._on_failure(was_half_open, exc)
            raise

        async with self._lock:
            self._on_success()

        return result

    async def reset(self) -> None:
        """Manually reset the breaker to CLOSED (e.g. after config change)."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = 0.0
        logger.info("Circuit breaker '%s' manually reset to CLOSED", self._service)

    # ── internal helpers ───────────────────────────────────────────────────

    async def _maybe_transition_to_half_open(self) -> None:
        """Transition OPEN → HALF_OPEN once the recovery window has passed."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._recovery_seconds:
                self._state = CircuitState.HALF_OPEN
                logger.info(
                    "Circuit breaker '%s' HALF_OPEN after %.0fs — sending probe call",
                    self._service,
                    elapsed,
                )

    def _on_failure(self, was_half_open: bool, exc: Exception) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if was_half_open or self._failure_count >= self._failure_threshold:
            prev_state = self._state
            self._state = CircuitState.OPEN
            if prev_state != CircuitState.OPEN:
                logger.warning(
                    "Circuit breaker '%s' TRIPPED to OPEN after %d failure(s). "
                    "Last error: %s",
                    self._service,
                    self._failure_count,
                    exc,
                )

    def _on_success(self) -> None:
        if self._state != CircuitState.CLOSED:
            logger.info(
                "Circuit breaker '%s' recovered → CLOSED (had %d failure(s))",
                self._service,
                self._failure_count,
            )
        self._state = CircuitState.CLOSED
        self._failure_count = 0

    def __repr__(self) -> str:
        return (
            f"<CircuitBreaker service={self._service!r} "
            f"state={self._state.value} failures={self._failure_count}>"
        )


# ── Registry ───────────────────────────────────────────────────────────────

class CircuitBreakerRegistry:
    """Global registry — one CircuitBreaker instance per service name."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(
        self,
        service: str,
        *,
        failure_threshold: int = 5,
        recovery_seconds: float = 60.0,
    ) -> CircuitBreaker:
        if service not in self._breakers:
            self._breakers[service] = CircuitBreaker(
                service,
                failure_threshold=failure_threshold,
                recovery_seconds=recovery_seconds,
            )
        return self._breakers[service]

    def all_states(self) -> dict[str, str]:
        return {name: cb.state.value for name, cb in self._breakers.items()}

    async def reset_all(self) -> None:
        for cb in self._breakers.values():
            await cb.reset()


# Singleton shared across the application
circuit_registry = CircuitBreakerRegistry()
