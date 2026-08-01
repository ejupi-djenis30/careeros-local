from __future__ import annotations

import asyncio
import threading
from contextlib import suppress

import pytest

from backend.api.middleware import VaultActivityMiddleware
from backend.career.activity import VaultActivityGate


async def _wait_for_counter(gate: VaultActivityGate, name: str, value: int) -> None:
    for _attempt in range(50):
        if getattr(gate, name) == value:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"{name} did not reach {value}")


@pytest.mark.asyncio
async def test_cancelled_waiting_writer_wakes_readers_and_cleans_counters() -> None:
    gate = VaultActivityGate()
    release_first_reader = asyncio.Event()
    first_reader_acquired = asyncio.Event()
    second_reader_acquired = asyncio.Event()

    async def first_reader() -> None:
        async with gate.reader():
            first_reader_acquired.set()
            await release_first_reader.wait()

    async def waiting_writer() -> None:
        async with gate.writer():
            raise AssertionError("cancelled writer unexpectedly acquired")

    async def second_reader() -> None:
        async with gate.reader():
            second_reader_acquired.set()

    first = asyncio.create_task(first_reader())
    await first_reader_acquired.wait()
    writer = asyncio.create_task(waiting_writer())
    await _wait_for_counter(gate, "_waiting_writers", 1)
    second = asyncio.create_task(second_reader())
    await asyncio.sleep(0)
    assert not second_reader_acquired.is_set()

    writer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await writer

    # Readers may coexist. Removing writer priority must actively wake reader 2;
    # reader 1 does not need to release first to trigger another notification.
    await asyncio.wait_for(second_reader_acquired.wait(), timeout=1)
    release_first_reader.set()
    await asyncio.gather(first, second)

    assert gate._readers == 0
    assert gate._waiting_writers == 0
    assert gate._writer is False


@pytest.mark.asyncio
async def test_cancelled_acquired_writer_releases_gate() -> None:
    gate = VaultActivityGate()
    writer_acquired = asyncio.Event()
    reader_acquired = asyncio.Event()

    async def active_writer() -> None:
        async with gate.writer():
            writer_acquired.set()
            await asyncio.Future()

    async def reader() -> None:
        async with gate.reader():
            reader_acquired.set()

    writer = asyncio.create_task(active_writer())
    await writer_acquired.wait()
    waiting_reader = asyncio.create_task(reader())
    await asyncio.sleep(0)
    assert not reader_acquired.is_set()

    writer.cancel()
    with suppress(asyncio.CancelledError):
        await writer
    await asyncio.wait_for(reader_acquired.wait(), timeout=1)
    await waiting_reader

    assert gate._readers == 0
    assert gate._waiting_writers == 0
    assert gate._writer is False


@pytest.mark.asyncio
async def test_cancelled_acquired_reader_wakes_writer() -> None:
    gate = VaultActivityGate()
    reader_acquired = asyncio.Event()
    writer_acquired = asyncio.Event()

    async def reader() -> None:
        async with gate.reader():
            reader_acquired.set()
            await asyncio.Future()

    async def writer() -> None:
        async with gate.writer():
            writer_acquired.set()

    active_reader = asyncio.create_task(reader())
    await reader_acquired.wait()
    waiting_writer = asyncio.create_task(writer())
    await _wait_for_counter(gate, "_waiting_writers", 1)

    active_reader.cancel()
    with suppress(asyncio.CancelledError):
        await active_reader
    await asyncio.wait_for(writer_acquired.wait(), timeout=1)
    await waiting_writer
    assert gate._readers == 0
    assert gate._writer is False


@pytest.mark.asyncio
async def test_cancelled_waiting_reader_leaves_gate_reusable() -> None:
    gate = VaultActivityGate()
    writer_acquired = asyncio.Event()
    release_writer = asyncio.Event()

    async def writer() -> None:
        async with gate.writer():
            writer_acquired.set()
            await release_writer.wait()

    active_writer = asyncio.create_task(writer())
    await writer_acquired.wait()
    waiting_reader = asyncio.create_task(gate.reader().__aenter__())
    await asyncio.sleep(0)
    waiting_reader.cancel()
    with suppress(asyncio.CancelledError):
        await waiting_reader
    release_writer.set()
    await active_writer

    async with gate.reader():
        assert gate._readers == 1
    assert gate._readers == 0


@pytest.mark.asyncio
async def test_cancelled_maintenance_holder_and_waiter_leave_mutex_reusable() -> None:
    gate = VaultActivityGate()
    holder_acquired = asyncio.Event()

    async def holder() -> None:
        async with gate.maintenance():
            holder_acquired.set()
            await asyncio.Future()

    active_holder = asyncio.create_task(holder())
    await holder_acquired.wait()
    waiting = asyncio.create_task(gate.maintenance().__aenter__())
    await asyncio.sleep(0)
    waiting.cancel()
    with suppress(asyncio.CancelledError):
        await waiting

    active_holder.cancel()
    with suppress(asyncio.CancelledError):
        await active_holder
    async with gate.maintenance():
        pass


@pytest.mark.asyncio
async def test_health_probes_bypass_writer_while_private_requests_still_drain() -> None:
    gate = VaultActivityGate()

    async def inner(scope, _receive, send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": scope["path"].encode()})

    middleware = VaultActivityMiddleware(inner, path_prefix="/api/v1", gate=gate)

    async def request(path: str) -> list[dict]:
        messages: list[dict] = []

        async def receive() -> dict:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict) -> None:
            messages.append(message)

        await middleware(
            {"type": "http", "method": "GET", "path": path, "headers": []},
            receive,
            send,
        )
        return messages

    async with gate.maintenance(), gate.writer():
        for path in (
            "/api/v1/health",
            "/api/v1/health/live",
            "/api/v1/health/ready",
        ):
            messages = await asyncio.wait_for(request(path), timeout=0.2)
            assert messages[0]["status"] == 200

        private_request = asyncio.create_task(request("/api/v1/career-profile"))
        await asyncio.sleep(0)
        assert not private_request.done()

    messages = await asyncio.wait_for(private_request, timeout=1)
    assert messages[0]["status"] == 200


@pytest.mark.asyncio
async def test_nonblocking_probe_reader_is_atomic_with_waiting_writer() -> None:
    gate = VaultActivityGate()
    writer_acquired = asyncio.Event()
    release_writer = asyncio.Event()

    async def writer() -> None:
        async with gate.writer():
            writer_acquired.set()
            await release_writer.wait()

    async with gate.try_reader() as acquired:
        assert acquired is True
        waiting_writer = asyncio.create_task(writer())
        await _wait_for_counter(gate, "_waiting_writers", 1)
        assert not writer_acquired.is_set()
        async with gate.try_reader() as second_probe:
            assert second_probe is False

    await asyncio.wait_for(writer_acquired.wait(), timeout=1)
    async with gate.try_reader() as probe_during_writer:
        assert probe_during_writer is False
    release_writer.set()
    await waiting_writer


@pytest.mark.asyncio
async def test_cancelled_readiness_joins_probe_thread_before_writer(
    monkeypatch,
) -> None:
    import backend.main as main_module

    gate = VaultActivityGate()
    probe_started = threading.Event()
    release_probe = threading.Event()
    writer_acquired = asyncio.Event()

    def blocking_statuses() -> tuple[str, str, str]:
        probe_started.set()
        release_probe.wait(timeout=5)
        return "connected", "writable", "current"

    monkeypatch.setattr(main_module, "vault_activity_gate", gate)
    monkeypatch.setattr(main_module, "_readiness_statuses", blocking_statuses)
    readiness = asyncio.create_task(main_module.health_ready())
    assert await asyncio.to_thread(probe_started.wait, 1)
    readiness.cancel()

    async def writer() -> None:
        async with gate.writer():
            writer_acquired.set()

    waiting_writer = asyncio.create_task(writer())
    await asyncio.sleep(0)
    assert not writer_acquired.is_set()
    assert not readiness.done()

    release_probe.set()
    with pytest.raises(asyncio.CancelledError):
        await readiness
    await asyncio.wait_for(writer_acquired.wait(), timeout=1)
    await waiting_writer
