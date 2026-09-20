from __future__ import annotations

from contextlib import contextmanager

import anyio
import httpx
import pytest

from backend.automation.desktop_client import (
    MAX_RESPONSE_BYTES,
    DesktopBridgeClient,
    DesktopBridgeError,
    validate_canonical_desktop_url,
)


@contextmanager
def _mock_client(*, transport, **_options):
    yield transport


@pytest.fixture(autouse=True)
def close_bridge_pools(monkeypatch):
    created = []
    original = DesktopBridgeClient.__init__

    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs)
        created.append(self)

    monkeypatch.setattr(DesktopBridgeClient, "__init__", initialize)
    yield
    for bridge in created:
        bridge.close()


def test_validate_canonical_desktop_url_valid() -> None:
    assert (
        validate_canonical_desktop_url("http://127.0.0.1:8000/api/v1")
        == "http://127.0.0.1:8000/api/v1"
    )
    assert validate_canonical_desktop_url("http://[::1]:9000/api/v1") == "http://[::1]:9000/api/v1"


@pytest.mark.parametrize(
    "invalid_url",
    [
        "https://127.0.0.1:8000/api/v1",  # Not http
        "ftp://127.0.0.1:8000/api/v1",
        "http://user:pass@127.0.0.1:8000/api/v1",  # Credentials
        "http://127.0.0.1:8000/api/v1?query=1",  # Query params
        "http://127.0.0.1:8000/api/v1#frag",  # Fragment
        "http://example.com:8000/api/v1",  # Non-loopback domain
        "http://8.8.8.8:8000/api/v1",  # Public IP
        "http://0.0.0.0:8000/api/v1",  # Non-loopback 0.0.0.0
        "http://192.168.1.5:8000/api/v1",  # Private LAN IP
        "http://127.0.0.1:8000/",  # Wrong path
        "http://127.0.0.1:8000/api",  # Wrong path
        "http://127.0.0.1:8000/other/path",  # Wrong path
        "http://127.0.0.1/api/v1",  # Missing port
        "http://localhost:5000/api/v1",
        "http://127.0.0.1:8000/api/v1/",
        "http://@127.0.0.1:8000/api/v1",
        "http://127.0.0.1:8000/api/v1?",
        "http://127.0.0.1:8000/api/v1;",
        "http://127.0.0.1:8000/api/v1#",
        "http://127.0.0.1:08000/api/v1",
        "",  # Empty
    ],
)
def test_validate_canonical_desktop_url_invalid(invalid_url: str) -> None:
    with pytest.raises(DesktopBridgeError) as exc_info:
        validate_canonical_desktop_url(invalid_url)
    assert exc_info.value.code == "invalid_desktop_url"


def test_desktop_bridge_client_requires_token() -> None:
    with pytest.raises(DesktopBridgeError) as exc_info:
        DesktopBridgeClient("http://127.0.0.1:8000/api/v1", "")
    assert exc_info.value.code == "grant_required"


def test_desktop_bridge_client_trust_env_and_redirects_policy() -> None:
    client = DesktopBridgeClient("http://127.0.0.1:8000/api/v1", "token-123")
    try:
        assert client._client.trust_env is False
        assert client._client.follow_redirects is False
    finally:
        client.close()


def test_desktop_bridge_client_rejects_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://127.0.0.1:8000/api/v1/other"})

    transport = httpx.MockTransport(handler)
    with _mock_client(
        transport=transport,
        base_url="http://127.0.0.1:8000/api/v1",
        trust_env=False,
        follow_redirects=False,
    ) as mock_httpx:
        bridge = DesktopBridgeClient(
            "http://127.0.0.1:8000/api/v1", "token-123", transport=mock_httpx
        )
        with pytest.raises(DesktopBridgeError) as exc_info:
            bridge.get_agent_status()
        assert exc_info.value.code == "bridge_error"
        assert "Redirects are not permitted" in exc_info.value.message


def test_desktop_bridge_client_enforces_response_size_limits() -> None:
    # 1. Content-Length header too large
    def handler_header(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": str(MAX_RESPONSE_BYTES + 100)})

    transport = httpx.MockTransport(handler_header)
    with _mock_client(
        transport=transport,
        base_url="http://127.0.0.1:8000/api/v1",
        trust_env=False,
        follow_redirects=False,
    ) as mock_httpx:
        bridge = DesktopBridgeClient(
            "http://127.0.0.1:8000/api/v1", "token-123", transport=mock_httpx
        )
        with pytest.raises(DesktopBridgeError) as exc_info:
            bridge.get_agent_status()
        assert exc_info.value.code == "response_too_large"

    # 2. Body payload too large
    def handler_body(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"a" * (MAX_RESPONSE_BYTES + 1))

    transport2 = httpx.MockTransport(handler_body)
    with _mock_client(
        transport=transport2,
        base_url="http://127.0.0.1:8000/api/v1",
        trust_env=False,
        follow_redirects=False,
    ) as mock_httpx:
        bridge = DesktopBridgeClient(
            "http://127.0.0.1:8000/api/v1", "token-123", transport=mock_httpx
        )
        with pytest.raises(DesktopBridgeError) as exc_info:
            bridge.get_agent_status()
        assert exc_info.value.code == "response_too_large"


def test_desktop_bridge_client_methods_and_error_parsing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/agent-bridge/status":
            return httpx.Response(200, json={"granted_scopes": ["system:read"]})
        if path == "/api/v1/agent-bridge/work-requests":
            return httpx.Response(200, json={"items": [], "offset": 0, "limit": 25})
        if (
            path
            == "/api/v1/agent-bridge/work-requests/c2b535fa-92b0-4f51-b0fa-d204d80a1001/context"
        ):
            return httpx.Response(200, json={"facts": [], "input_digest": "digest1"})
        if path == "/api/v1/agent-bridge/work-requests/c2b535fa-92b0-4f51-b0fa-d204d80a1001/result":
            if request.method == "POST":
                return httpx.Response(200, json={"proposal_id": "p-1", "state": "returned"})
            return httpx.Response(200, json={"proposal_id": "p-1", "state": "returned"})
        if path == "/api/v1/agent-bridge/resume-templates":
            return httpx.Response(200, json=[{"id": "software-en"}])
        if (
            path
            == "/api/v1/agent-bridge/work-requests/c2b535fa-92b0-4f51-b0fa-d204d80a1002/context"
        ):
            return httpx.Response(
                404,
                json={"detail": {"code": "work_not_found", "message": "Work request missing"}},
            )
        return httpx.Response(404, json={"detail": "Not found"})

    transport = httpx.MockTransport(handler)
    with _mock_client(
        transport=transport,
        base_url="http://127.0.0.1:8000/api/v1",
        trust_env=False,
        follow_redirects=False,
    ) as mock_httpx:
        bridge = DesktopBridgeClient(
            "http://127.0.0.1:8000/api/v1", "token-123", transport=mock_httpx
        )

        # Status
        status = bridge.get_agent_status()
        assert status["granted_scopes"] == ["system:read"]

        # List work
        work = bridge.list_work_requests(offset=0, limit=25)
        assert work["items"] == []

        # Context
        ctx = bridge.get_work_context("c2b535fa-92b0-4f51-b0fa-d204d80a1001")
        assert ctx["input_digest"] == "digest1"

        # Submit result
        res = bridge.submit_work_result(
            "c2b535fa-92b0-4f51-b0fa-d204d80a1001",
            {"request_id": "c2b535fa-92b0-4f51-b0fa-d204d80a1001", "result": "ok"},
        )
        assert res["proposal_id"] == "p-1"

        # Get result
        res_get = bridge.get_work_result("c2b535fa-92b0-4f51-b0fa-d204d80a1001")
        assert res_get["proposal_id"] == "p-1"

        # Templates
        templates = bridge.list_resume_templates()
        assert templates[0]["id"] == "software-en"

        # Structured error
        with pytest.raises(DesktopBridgeError) as exc_info:
            bridge.get_work_context("c2b535fa-92b0-4f51-b0fa-d204d80a1002")
        assert exc_info.value.code == "work_not_found"
        assert exc_info.value.status_code == 404


@pytest.mark.parametrize(
    "identity", ["../auth/login", "%2fstatus", "http://example.com", " abc", "abc?x=1"]
)
def test_request_identity_rejected_before_transport(identity):
    calls = []
    with _mock_client(
        transport=httpx.MockTransport(lambda request: calls.append(request))
    ) as client:
        bridge = DesktopBridgeClient(
            "http://127.0.0.1:8000/api/v1", "synthetic-token", transport=client
        )
        with pytest.raises(DesktopBridgeError):
            bridge.get_work_context(identity)
    assert calls == []


def test_chunked_response_limit_stops_stream_and_sends_grant_only_to_fixed_url():
    observed = []

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            for index in range(100):
                observed.append(index)
                yield b"x" * 8192

    def handler(request):
        assert str(request.url) == "http://127.0.0.1:8000/api/v1/agent-bridge/status"
        assert request.headers["Authorization"] == "Bearer synthetic-token"
        return httpx.Response(200, stream=Chunks())

    with _mock_client(transport=httpx.MockTransport(handler)) as client:
        bridge = DesktopBridgeClient(
            "http://127.0.0.1:8000/api/v1", "synthetic-token", transport=client
        )
        with pytest.raises(DesktopBridgeError) as exc:
            bridge.get_agent_status()
    assert exc.value.code == "response_too_large" and len(observed) < 100


def test_untrusted_error_content_never_exposed():
    secret = "synthetic-token-and-private-profile"

    def handler(request):
        return httpx.Response(422, json={"detail": {"code": secret, "message": secret}})

    with _mock_client(transport=httpx.MockTransport(handler)) as client:
        bridge = DesktopBridgeClient(
            "http://127.0.0.1:8000/api/v1", "synthetic-token", transport=client
        )
        with pytest.raises(DesktopBridgeError) as exc:
            bridge.get_agent_status()
    assert secret not in str(exc.value) and exc.value.code == "invalid_result"


def test_slow_drip_is_checked_against_total_deadline():
    observed = []

    class Drip(httpx.AsyncByteStream):
        async def __aiter__(self):
            for index in range(100):
                await anyio.sleep(0.6)
                observed.append(index)
                yield b" "

    with _mock_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Drip()))
    ) as client:
        bridge = DesktopBridgeClient(
            "http://127.0.0.1:8000/api/v1", "synthetic-token", timeout_seconds=1, transport=client
        )
        with pytest.raises(DesktopBridgeError) as exc:
            bridge.get_agent_status()
    assert exc.value.code == "desktop_unavailable" and len(observed) == 1


def test_outgoing_oversize_is_rejected_before_transport():
    calls = []
    with _mock_client(
        transport=httpx.MockTransport(lambda request: calls.append(request))
    ) as client:
        bridge = DesktopBridgeClient(
            "http://127.0.0.1:8000/api/v1", "synthetic-token", transport=client
        )
        with pytest.raises(DesktopBridgeError) as exc:
            bridge.submit_work_result(
                "c2b535fa-92b0-4f51-b0fa-d204d80a1001",
                {"request_id": "c2b535fa-92b0-4f51-b0fa-d204d80a1001", "result": "x" * 300000},
            )
    assert exc.value.code == "invalid_result" and calls == []
