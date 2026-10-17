from __future__ import annotations

import asyncio
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import httpx
import pytest

from backend.inference import managed_runtime as module
from backend.inference import service


class Child:
    def __init__(self):
        self.alive = True
        self.terminate_error = False
        self.ignore_terminate = False
        self.kill_error = False
        self.wait_timeouts = []

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        if self.terminate_error:
            raise OSError("synthetic termination denied")
        if not self.ignore_terminate:
            self.alive = False

    def wait(self, timeout):
        self.wait_timeouts.append(timeout)
        if self.alive:
            raise subprocess.TimeoutExpired("synthetic child", timeout)
        return 0

    def kill(self):
        if self.kill_error:
            raise OSError("synthetic kill denied")
        self.alive = False


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    manager = module.ManagedRuntime(tmp_path)
    children = []

    def spawn(*_args, **_kwargs):
        child = Child()
        children.append(child)
        return child

    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    monkeypatch.setattr(module, "_available_loopback_port", lambda: 55443)
    monkeypatch.setattr(manager, "_verify_launch_assets", lambda **_kwargs: None)
    monkeypatch.setattr(manager, "_wait_until_healthy", lambda **_kwargs: True)
    monkeypatch.setattr(service, "get_managed_runtime", lambda: manager)
    yield manager, children
    for child in children:
        child.alive = False


@contextmanager
def pending_start(manager, monkeypatch, stage, *, healthy=True, cancelled=None):
    entered, release = threading.Event(), threading.Event()

    def block(**_kwargs):
        if entered.is_set():
            return healthy if stage == "health" else None
        entered.set()
        assert release.wait(5), "synthetic start was not released"
        if stage == "verify" and not healthy:
            raise ValueError("synthetic asset verification failure")
        return healthy if stage == "health" else None

    symbol = "_verify_launch_assets" if stage == "verify" else "_wait_until_healthy"
    monkeypatch.setattr(manager, symbol, block)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(manager.start, cancelled=cancelled)
        try:
            assert entered.wait(3), "synthetic start did not reach the boundary"
            yield future, release
        finally:
            release.set()


def test_single_restart_reaps_its_only_child(runtime):
    manager, children = runtime
    status = asyncio.run(service.restart_managed_model())
    assert status.ready
    manager.stop()
    assert len(children) == 1
    assert not any(child.alive for child in children)


def test_real_restart_service_rejects_overlap_without_orphan(runtime, monkeypatch):
    manager, children = runtime
    with pending_start(manager, monkeypatch, "verify") as (first, release):
        with pytest.raises(RuntimeError, match="startup.*already running"):
            asyncio.run(service.restart_managed_model())
        assert not children
        release.set()
        assert first.result(timeout=3).ready
    manager.stop()
    assert len(children) == 1
    assert not children[0].alive


@pytest.mark.parametrize("stage", ["verify", "health"])
def test_stop_interrupts_pending_start_without_waiting_for_health(runtime, monkeypatch, stage):
    manager, children = runtime
    with pending_start(manager, monkeypatch, stage) as (first, release):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(manager.stop).result(timeout=1)
        assert not any(child.alive for child in children)
        release.set()
        with pytest.raises(module.RuntimeStartCancelled):
            first.result(timeout=3)
    assert not manager.snapshot().ready
    assert manager.snapshot().phase == "idle"
    assert manager._api_key is None
    assert manager._endpoint is None


@pytest.mark.parametrize("stage", ["verify", "health"])
@pytest.mark.parametrize("healthy", [False, True])
def test_stale_completion_cannot_stop_or_relabel_new_child(runtime, monkeypatch, stage, healthy):
    manager, children = runtime
    with pending_start(manager, monkeypatch, stage, healthy=healthy) as (old, release):
        manager.stop()
        monkeypatch.setattr(manager, "_verify_launch_assets", lambda **_kwargs: None)
        monkeypatch.setattr(manager, "_wait_until_healthy", lambda **_kwargs: True)
        assert manager.start().ready
        current = children[-1]
        release.set()
        with pytest.raises(module.RuntimeStartCancelled):
            old.result(timeout=3)
        assert current.alive
        assert manager._process is current
        assert manager.snapshot().ready
        assert manager.snapshot().error_code is None
    manager.stop()
    assert not any(child.alive for child in children)


@pytest.mark.parametrize("stage", ["verify", "health"])
def test_external_cancellation_reaps_child_and_allows_next_start(runtime, monkeypatch, stage):
    manager, children = runtime
    cancelled = threading.Event()
    with pending_start(manager, monkeypatch, stage, cancelled=cancelled) as (old, release):
        cancelled.set()
        release.set()
        with pytest.raises(module.RuntimeStartCancelled):
            old.result(timeout=3)
    assert not any(child.alive for child in children)
    monkeypatch.setattr(manager, "_verify_launch_assets", lambda **_kwargs: None)
    monkeypatch.setattr(manager, "_wait_until_healthy", lambda **_kwargs: True)
    assert manager.start().ready


def test_unexpected_health_failure_reaps_child_and_releases_startup(runtime, monkeypatch):
    manager, children = runtime

    def fail(**_kwargs):
        raise ValueError("synthetic health failure")

    monkeypatch.setattr(manager, "_wait_until_healthy", fail)
    with pytest.raises(ValueError, match="synthetic health failure"):
        manager.start()
    assert not children[0].alive
    assert manager._process is None
    assert manager._api_key is None
    assert manager._endpoint is None
    monkeypatch.setattr(manager, "_wait_until_healthy", lambda **_kwargs: True)
    assert manager.start().ready


@pytest.mark.parametrize("failure", ["terminate", "kill"])
def test_failed_bounded_reap_retains_handle_and_blocks_replacement(runtime, failure):
    manager, children = runtime
    manager.start()
    child = children[0]
    child.terminate_error = failure == "terminate"
    child.ignore_terminate = failure == "kill"
    child.kill_error = failure == "kill"
    with pytest.raises(OSError):
        manager.stop()
    assert manager._process is child
    assert child.alive
    assert manager._api_key is None
    assert manager._endpoint is None
    with pytest.raises(OSError):
        manager.start()
    assert children == [child]
    child.terminate_error = child.ignore_terminate = child.kill_error = False
    assert manager.start().ready
    assert not child.alive


def test_reap_keeps_existing_five_then_two_second_budgets(runtime):
    manager, children = runtime
    manager.start()
    children[0].ignore_terminate = True
    manager.stop()
    assert children[0].wait_timeouts == [5, 2]
    assert not children[0].alive


def test_health_probe_uses_captured_process_and_endpoint(runtime, monkeypatch):
    manager, _children = runtime
    captured, successor = Child(), Child()
    manager._process = successor
    manager._endpoint = "http://127.0.0.1:55445"
    seen = []

    def request(req):
        seen.append(str(req.url))
        return httpx.Response(200)

    original_client = httpx.Client
    monkeypatch.setattr(
        module.httpx,
        "Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(request), **kwargs),
    )
    assert module.ManagedRuntime._wait_until_healthy(
        manager,
        process=captured,
        endpoint="http://127.0.0.1:55444",
        timeout_seconds=0.5,
        cancelled=None,
    )
    assert seen == ["http://127.0.0.1:55444/health"]
    captured.alive = False
    assert not module.ManagedRuntime._wait_until_healthy(
        manager,
        process=captured,
        endpoint="http://127.0.0.1:55444",
        timeout_seconds=0.5,
        cancelled=None,
    )
    assert successor.alive
