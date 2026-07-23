"""Unit tests for backend/providers/circuit_breaker.py.

Covers:
- CircuitBreaker state machine: CLOSED → OPEN → HALF_OPEN → CLOSED
- CircuitOpenError fast-fail when OPEN
- CircuitBreakerRegistry singleton behaviour
"""

import asyncio

import pytest

from backend.providers.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitOpenError,
    CircuitState,
)

# ─── helpers ──────────────────────────────────────────────────────────────────


async def _ok(value=42):
    return value


async def _fail(exc_type: type[Exception] = RuntimeError, msg: str = "boom"):
    raise exc_type(msg)


# ─── Basic CLOSED state ────────────────────────────────────────────────────────


class TestCircuitBreakerClosed:
    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self):
        cb = CircuitBreaker("svc", failure_threshold=3, recovery_seconds=60)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_successful_call_returns_value(self):
        cb = CircuitBreaker("svc", failure_threshold=3, recovery_seconds=60)
        result = await cb.call(_ok(99))
        assert result == 99

    @pytest.mark.asyncio
    async def test_success_does_not_change_state(self):
        cb = CircuitBreaker("svc", failure_threshold=3, recovery_seconds=60)
        await cb.call(_ok())
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_failed_call_reraises_exception(self):
        cb = CircuitBreaker("svc", failure_threshold=3, recovery_seconds=60)
        with pytest.raises(ValueError, match="oops"):
            await cb.call(_fail(ValueError, "oops"))

    @pytest.mark.asyncio
    async def test_failure_increments_count(self):
        cb = CircuitBreaker("svc", failure_threshold=3, recovery_seconds=60)
        try:
            await cb.call(_fail())
        except RuntimeError:
            pass
        assert cb.failure_count == 1
        assert cb.state == CircuitState.CLOSED  # not tripped yet


# ─── CLOSED → OPEN transition ─────────────────────────────────────────────────


class TestCircuitBreakerTrip:
    @pytest.mark.asyncio
    async def test_trips_to_open_after_threshold_failures(self):
        cb = CircuitBreaker("svc", failure_threshold=2, recovery_seconds=60)
        for _ in range(2):
            try:
                await cb.call(_fail())
            except RuntimeError:
                pass
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_circuit_raises_circuit_open_error(self):
        cb = CircuitBreaker("svc", failure_threshold=1, recovery_seconds=60)
        try:
            await cb.call(_fail())
        except RuntimeError:
            pass
        coro = _ok()
        try:
            with pytest.raises(CircuitOpenError) as exc_info:
                await cb.call(coro)
        finally:
            coro.close()
        assert exc_info.value.service == "svc"
        assert exc_info.value.retry_after >= 0

    @pytest.mark.asyncio
    async def test_circuit_open_error_message_contains_service_name(self):
        cb = CircuitBreaker("my-service", failure_threshold=1, recovery_seconds=30)
        try:
            await cb.call(_fail())
        except RuntimeError:
            pass
        coro = _ok()
        try:
            await cb.call(coro)
        except CircuitOpenError as e:
            assert "my-service" in str(e)
        else:
            pytest.fail("Expected CircuitOpenError")
        finally:
            coro.close()


# ─── OPEN → HALF_OPEN → CLOSED recovery ───────────────────────────────────────


class TestCircuitBreakerRecovery:
    @pytest.mark.asyncio
    async def test_half_open_after_recovery_window(self):
        cb = CircuitBreaker("svc", failure_threshold=1, recovery_seconds=0.05)
        try:
            await cb.call(_fail())
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN
        await asyncio.sleep(0.1)
        # Next call should succeed and close the circuit
        result = await cb.call(_ok(7))
        assert result == 7
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_failed_probe_in_half_open_reopens(self):
        cb = CircuitBreaker("svc", failure_threshold=1, recovery_seconds=0.05)
        try:
            await cb.call(_fail())
        except RuntimeError:
            pass
        await asyncio.sleep(0.1)
        # Should transition to HALF_OPEN; probe fails → back to OPEN
        try:
            await cb.call(_fail())
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_manual_reset_closes_circuit(self):
        cb = CircuitBreaker("svc", failure_threshold=1, recovery_seconds=60)
        try:
            await cb.call(_fail())
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN
        await cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0


# ─── repr ─────────────────────────────────────────────────────────────────────


class TestCircuitBreakerRepr:
    def test_repr_contains_state_and_service(self):
        cb = CircuitBreaker("ollama-local", failure_threshold=5, recovery_seconds=60)
        r = repr(cb)
        assert "ollama-local" in r
        assert "closed" in r


# ─── CircuitBreakerRegistry ───────────────────────────────────────────────────


class TestCircuitBreakerRegistry:
    def test_get_returns_circuit_breaker(self):
        reg = CircuitBreakerRegistry()
        cb = reg.get("my-svc")
        assert isinstance(cb, CircuitBreaker)

    def test_get_same_service_returns_same_instance(self):
        reg = CircuitBreakerRegistry()
        a = reg.get("svc-a")
        b = reg.get("svc-a")
        assert a is b

    def test_get_different_services_return_different_instances(self):
        reg = CircuitBreakerRegistry()
        a = reg.get("svc-a")
        b = reg.get("svc-b")
        assert a is not b

    def test_all_states_returns_dict(self):
        reg = CircuitBreakerRegistry()
        reg.get("svc-x")
        reg.get("svc-y")
        states = reg.all_states()
        assert "svc-x" in states
        assert "svc-y" in states
        assert states["svc-x"] == "closed"

    @pytest.mark.asyncio
    async def test_reset_all_closes_open_circuits(self):
        reg = CircuitBreakerRegistry()
        cb = reg.get("svc-z", failure_threshold=1, recovery_seconds=60)
        try:
            await cb.call(_fail())
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN
        await reg.reset_all()
        assert cb.state == CircuitState.CLOSED
