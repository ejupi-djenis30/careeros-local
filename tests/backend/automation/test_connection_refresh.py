from __future__ import annotations

import time
from threading import Event
from uuid import uuid4

import anyio
import httpx
import pytest

from backend.automation import desktop_client as desktop_client_module
from backend.automation.desktop_client import DesktopBridgeClient, DesktopBridgeError
from backend.automation.mcp_server import MCPStartupError, _parser, run_server
from backend.desktop.connection_descriptor import publish_connection_descriptor


def test_connection_is_refreshed_each_operation_and_recycles_pool_even_on_same_port(tmp_path):
    calls = []

    def handler(request):
        calls.append((str(request.url), request.headers.get("Authorization")))
        return httpx.Response(200, json={"ok": True})

    path = publish_connection_descriptor(tmp_path, "http://127.0.0.1:43127/api/v1", str(uuid4()))
    with DesktopBridgeClient(
        None, "synthetic-grant", connection_file=str(path), transport=httpx.MockTransport(handler)
    ) as bridge:
        assert bridge.get_agent_status() == {"ok": True}
        initial = bridge._client
        publish_connection_descriptor(tmp_path, "http://127.0.0.1:43127/api/v1", str(uuid4()))
        bridge.get_agent_status()
        assert initial.is_closed and bridge._client is not initial
        second = bridge._client
        publish_connection_descriptor(tmp_path, "http://127.0.0.1:43128/api/v1", str(uuid4()))
        bridge.get_agent_status()
        assert second.is_closed and calls[-1][0].startswith("http://127.0.0.1:43128/")
        path.unlink()
        with pytest.raises(DesktopBridgeError, match="desktop_unavailable"):
            bridge.get_agent_status()
        assert len(calls) == 3
    assert all(token == "Bearer synthetic-grant" for _, token in calls)


@pytest.mark.parametrize("stage", ["headers", "late-read"])
def test_absolute_deadline_cancels_headers_and_a_read_near_the_limit(stage):
    canceled = Event()

    class LateRead(httpx.AsyncByteStream):
        async def __aiter__(self):
            try:
                yield b"{"
                await anyio.sleep(0.8)
                yield b" "
                await anyio.sleep_forever()
            finally:
                canceled.set()

    async def handler(request):
        if stage == "headers":
            try:
                await anyio.sleep_forever()
            finally:
                canceled.set()
        return httpx.Response(200, stream=LateRead())

    with DesktopBridgeClient(
        "http://127.0.0.1:43127/api/v1",
        "synthetic-grant",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    ) as bridge:
        started = time.monotonic()
        with pytest.raises(DesktopBridgeError, match="deadline"):
            bridge.get_agent_status()
        assert time.monotonic() - started < 3
        assert canceled.is_set()


def test_absolute_deadline_includes_connection_descriptor_read(tmp_path, monkeypatch):
    calls = []
    path = publish_connection_descriptor(
        tmp_path, "http://127.0.0.1:43127/api/v1", str(uuid4())
    )
    original_reader = desktop_client_module.read_connection_descriptor

    def slow_reader(connection_file):
        time.sleep(1.65)
        return original_reader(connection_file)

    monkeypatch.setattr(desktop_client_module, "read_connection_descriptor", slow_reader)
    with DesktopBridgeClient(
        None,
        "synthetic-grant",
        connection_file=str(path),
        timeout_seconds=1,
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200, json={"ok": True})
        ),
    ) as bridge:
        started = time.monotonic()
        with pytest.raises(DesktopBridgeError, match="deadline") as failure:
            bridge.get_agent_status()
        elapsed = time.monotonic() - started

    assert failure.value.code == "desktop_unavailable"
    assert elapsed < 1.5
    assert calls == []


def test_connection_modes_are_exclusive_and_disclosure_required(tmp_path):
    with pytest.raises(SystemExit):
        _parser().parse_args(
            [
                "--connection-file",
                str(tmp_path / "connection.json"),
                "--desktop-url",
                "http://127.0.0.1:43127/api/v1",
            ]
        )
    with pytest.raises(MCPStartupError) as denied:
        run_server(
            connection_file=str(tmp_path / "connection.json"),
            acknowledge_agent_disclosure=False,
            token="synthetic",
        )
    assert denied.value.code == "disclosure_acknowledgement_required"


@pytest.mark.parametrize("mode", ["connection_file", "desktop_url"])
def test_empty_explicit_desktop_mode_never_falls_back_to_the_headless_vault(mode, monkeypatch):
    def reject_headless(*_args):
        raise AssertionError("An invalid desktop configuration must not open the headless vault")

    monkeypatch.setattr("backend.automation.mcp_server._run_headless", reject_headless)
    with pytest.raises(DesktopBridgeError, match="invalid_desktop_url"):
        run_server(**{mode: ""}, acknowledge_agent_disclosure=True, token="synthetic")
