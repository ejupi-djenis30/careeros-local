from datetime import timedelta

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from backend.agent_work.schemas import WorkContextPayload
from backend.automation.desktop_client import DesktopBridgeClient
from backend.automation.workspace_mcp import build_workspace_mcp_server
from tests.backend.agent_work.helpers import discovery

ID = "c2b535fa-92b0-4f51-b0fa-d204d80a1001"
NOW = "2026-09-13T10:00:00Z"


def _bridge(handler):
    return DesktopBridgeClient(
        "http://127.0.0.1:8000/api/v1",
        "synthetic-token",
        transport=httpx.MockTransport(handler),
    )


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


@pytest.mark.asyncio
async def test_workspace_mcp_initialize_list_and_annotations():
    bridge = _bridge(lambda request: httpx.Response(200, json={}))
    server = build_workspace_mcp_server(bridge)
    async with create_connected_server_and_client_session(
        server, read_timeout_seconds=timedelta(seconds=5), raise_exceptions=True
    ) as session:
        tools = (await session.list_tools()).tools
        assert {t.name for t in tools} == {
            "get_agent_status",
            "list_work_requests",
            "get_work_context",
            "submit_work_result",
            "get_work_result",
            "list_resume_templates",
        }
        by_name = {tool.name: tool for tool in tools}
        for tool in tools:
            assert tool.outputSchema
            assert tool.annotations.readOnlyHint is (tool.name != "submit_work_result")
        schema = by_name["submit_work_result"].inputSchema
        assert "oneOf" in schema["properties"]["result"]
        assert schema["properties"]["request_id"]["pattern"]
        assert schema["properties"]["input_digest"]["pattern"] == "^[0-9a-f]{64}$"
        assert schema["properties"]["idempotency_key"]["pattern"] == "^[!-~]+$"
        for definition in schema.get("$defs", {}).values():
            if definition.get("type") == "object":
                assert definition.get("additionalProperties") is False


@pytest.mark.asyncio
async def test_workspace_mcp_tool_execution_flow():
    calls = []

    def handler(request):
        assert request.headers["Authorization"] == "Bearer synthetic-token"
        calls.append(request.url.path)
        if request.url.path.endswith("/status"):
            body = {
                "schema_version": "1.0",
                "contract_version": 1,
                "granted_scopes": ["context:read", "proposals:write"],
                "queue_counts": {"queued": 1, "returned": 0},
            }
        elif request.url.path.endswith("/work-requests"):
            body = {
                "items": [
                    {
                        "id": ID,
                        "work_kind": "discover",
                        "state": "queued",
                        "revision": 1,
                        "expires_at": NOW,
                        "created_at": NOW,
                        "updated_at": NOW,
                    }
                ],
                "offset": 0,
                "limit": 25,
                "returned_count": 1,
            }
        elif request.url.path.endswith("/context"):
            body = WorkContextPayload(
                request_id=ID,
                work_kind="discover",
                instruction="Synthetic",
                input_digest="a" * 64,
                input_revisions={},
                facts=[],
            ).model_dump(mode="json")
        elif request.url.path.endswith("/resume-templates"):
            body = [
                {
                    "id": "software-en",
                    "name": "Software",
                    "version": 1,
                    "locale": "en",
                    "layout": "ats",
                }
            ]
        else:
            body = {
                "proposal_id": ID,
                "request_id": ID,
                "state": "returned",
                "payload_digest": "b" * 64,
                "review_required": True,
                "created_at": NOW,
            }
        return httpx.Response(200, json=body)

    bridge = _bridge(handler)
    async with create_connected_server_and_client_session(
        build_workspace_mcp_server(bridge), raise_exceptions=True
    ) as session:
        for name, args in [
            ("get_agent_status", {}),
            ("list_work_requests", {}),
            ("get_work_context", {"request_id": ID}),
            (
                "submit_work_result",
                {
                    "request_id": ID,
                    "input_digest": "a" * 64,
                    "idempotency_key": "sdk-1",
                    "client": "Synthetic",
                    "result": discovery(),
                },
            ),
            ("get_work_result", {"request_id": ID}),
            ("list_resume_templates", {}),
        ]:
            result = await session.call_tool(name, args)
            assert not result.isError, result.content
    assert len(calls) == 6


@pytest.mark.asyncio
async def test_workspace_mcp_negative_errors_are_content_free():
    private = "synthetic-private-profile-do-not-echo"
    bridge = _bridge(
        lambda request: httpx.Response(
            403, json={"detail": {"code": "scope_denied", "message": private}}
        )
    )
    async with create_connected_server_and_client_session(
        build_workspace_mcp_server(bridge), raise_exceptions=True
    ) as session:
        denied = await session.call_tool("get_work_context", {"request_id": ID})
        assert (
            denied.isError
            and "scope_denied" in denied.content[0].text
            and private not in denied.content[0].text
        )
        malformed = await session.call_tool("get_work_context", {"request_id": private})
        assert malformed.isError and private not in malformed.content[0].text


@pytest.mark.asyncio
async def test_workspace_mcp_rejects_digest_and_idempotency_patterns_before_transport():
    calls = []
    bridge = _bridge(lambda request: calls.append(request) or httpx.Response(200, json={}))
    result = discovery()
    private = "synthetic-private-input-must-not-echo"
    common = {
        "request_id": ID,
        "client": "Synthetic",
        "result": result,
    }
    async with create_connected_server_and_client_session(
        build_workspace_mcp_server(bridge), raise_exceptions=True
    ) as session:
        malformed_digest = await session.call_tool(
            "submit_work_result",
            {**common, "input_digest": private.ljust(64, "Z"), "idempotency_key": "sdk-1"},
        )
        malformed_key = await session.call_tool(
            "submit_work_result",
            {**common, "input_digest": "a" * 64, "idempotency_key": f"sdk\n{private}"},
        )

    for response in (malformed_digest, malformed_key):
        assert response.isError
        assert private not in response.content[0].text
    assert calls == []
