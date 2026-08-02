from __future__ import annotations

import contextlib
from datetime import timedelta

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import text

from backend.applications.schemas import ApplicationCreate, ManualJobSnapshot
from backend.applications.service import ApplicationService
from backend.automation.facade import AutomationFacade
from backend.automation.grants import AutomationGrantError, AutomationPrincipal
from backend.automation.mcp_server import build_server
from backend.automation.schemas import ALL_AUTOMATION_SCOPES
from backend.automation.tool_catalog import TOOL_SCOPES
from backend.db.base import SessionLocal
from tests.backend.providers.configuration.helpers import json_provider_payload


def _server(user_id: int, scopes: frozenset[str]):
    principal = AutomationPrincipal(
        grant_id="protocol-test",
        user_id=user_id,
        scopes=scopes,  # type: ignore[arg-type]
    )
    return build_server(AutomationFacade(SessionLocal, principal), access=contextlib.nullcontext)


@pytest.mark.asyncio
async def test_official_client_negotiates_lists_and_calls_typed_tools(
    db_session, test_user
) -> None:
    db_session.execute(
        text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
    )
    db_session.execute(text("DELETE FROM alembic_version"))
    db_session.execute(text("INSERT INTO alembic_version VALUES ('protocol-head')"))
    application = ApplicationService(db_session).create(
        test_user.id,
        ApplicationCreate(
            manual_job=ManualJobSnapshot(
                title="Reliability Engineer",
                company="Example Foundation",
            )
        ),
    )
    db_session.commit()
    server = _server(
        test_user.id,
        frozenset({"system:read", "career:read", "resume:read", "applications:read"}),
    )

    async with create_connected_server_and_client_session(
        server,
        read_timeout_seconds=timedelta(seconds=5),
        raise_exceptions=True,
    ) as session:
        response = await session.list_tools()
        names = {tool.name for tool in response.tools}
        assert names == {
            "get_status",
            "get_local_model_status",
            "get_career_summary",
            "get_career_profile",
            "get_resume_catalog",
            "get_resume",
            "list_applications",
            "get_application",
            "get_application_readiness",
            "get_application_agenda",
            "get_application_dossier_draft",
        }
        for tool in response.tools:
            assert tool.outputSchema is not None
            assert tool.annotations is not None
            assert tool.annotations.readOnlyHint is True
            assert tool.annotations.destructiveHint is False
            assert tool.annotations.openWorldHint is False

        calls = {
            "get_status": {},
            "get_local_model_status": {},
            "get_career_summary": {},
            "get_resume_catalog": {},
            "list_applications": {"limit": 10},
            "get_application": {"application_id": application.id},
            "get_application_readiness": {"application_id": application.id},
            "get_application_agenda": {"limit": 10},
            "get_application_dossier_draft": {"application_id": application.id},
        }
        results = {
            name: await session.call_tool(name, arguments) for name, arguments in calls.items()
        }

    for result in results.values():
        assert result.isError is False
        assert result.structuredContent is not None
    assert results["list_applications"].structuredContent["returned_count"] == 1
    assert (
        results["get_application_readiness"].structuredContent["application_id"] == application.id
    )
    assert results["get_application_agenda"].structuredContent["active_count"] == 1
    assert results["get_application"].structuredContent["id"] == application.id
    serialized = str({name: result.structuredContent for name, result in results.items()})
    for forbidden in (
        "artifact_bytes",
        "prompt",
        "token",
        "password",
    ):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_tool_visibility_is_derived_from_grant_scopes(db_session, test_user) -> None:
    db_session.execute(
        text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
    )
    db_session.execute(text("DELETE FROM alembic_version"))
    db_session.execute(text("INSERT INTO alembic_version VALUES ('protocol-head')"))
    db_session.commit()
    server = _server(test_user.id, frozenset({"career:read"}))

    async with create_connected_server_and_client_session(server) as session:
        tools = await session.list_tools()
        assert [tool.name for tool in tools.tools] == [
            "get_career_summary",
            "get_career_profile",
        ]
        assert all("delete" not in tool.name for tool in tools.tools)
        assert all("restore" not in tool.name for tool in tools.tools)
        assert {"read_file", "write_file"}.isdisjoint(tool.name for tool in tools.tools)
        assert all("sql" not in tool.name for tool in tools.tools)


@pytest.mark.asyncio
async def test_all_scope_registration_matches_the_shared_capability_catalog(
    db_session, test_user
) -> None:
    server = _server(test_user.id, frozenset(ALL_AUTOMATION_SCOPES))

    async with create_connected_server_and_client_session(server) as session:
        response = await session.list_tools()

    assert {tool.name for tool in response.tools} == set(TOOL_SCOPES)
    assert all(tool.outputSchema is not None for tool in response.tools)


@pytest.mark.asyncio
async def test_every_registered_tool_revalidates_access(db_session, test_user) -> None:
    principal = AutomationPrincipal(
        grant_id="protocol-test",
        user_id=test_user.id,
        scopes=frozenset({"system:read", "career:read", "resume:read", "applications:read"}),  # type: ignore[arg-type]
    )
    checks = 0

    @contextlib.contextmanager
    def revoked_access():
        nonlocal checks
        checks += 1
        raise AutomationGrantError("revoked_grant", "The automation grant has been revoked")
        yield  # pragma: no cover

    server = build_server(AutomationFacade(SessionLocal, principal), access=revoked_access)
    arguments = {
        "get_status": {},
        "get_local_model_status": {},
        "get_career_summary": {},
        "get_career_profile": {},
        "get_resume_catalog": {},
        "get_resume": {"resume_id": "00000000-0000-0000-0000-000000000000"},
        "list_applications": {},
        "get_application": {
            "application_id": "00000000-0000-0000-0000-000000000000"
        },
        "get_application_readiness": {"application_id": "missing"},
        "get_application_agenda": {},
        "get_application_dossier_draft": {
            "application_id": "00000000-0000-0000-0000-000000000000"
        },
    }

    async with create_connected_server_and_client_session(
        server,
        read_timeout_seconds=timedelta(seconds=5),
        raise_exceptions=True,
    ) as session:
        response = await session.list_tools()
        for tool in response.tools:
            result = await session.call_tool(tool.name, arguments[tool.name])
            assert result.isError is True
            assert "revoked_grant" in str(result.content)

    assert checks == len(arguments)


@pytest.mark.asyncio
async def test_expected_facade_error_keeps_its_stable_code(db_session, test_user) -> None:
    server = _server(test_user.id, frozenset({"applications:read"}))

    async with create_connected_server_and_client_session(
        server,
        read_timeout_seconds=timedelta(seconds=5),
        raise_exceptions=True,
    ) as session:
        result = await session.call_tool("get_application_readiness", {"application_id": "missing"})

    assert result.isError is True
    assert "application_not_found" in str(result.content)
    assert "internal_error" not in str(result.content)


@pytest.mark.asyncio
async def test_scoped_agent_can_configure_source_capture_job_and_mark_applied(
    db_session, test_user
) -> None:
    server = _server(
        test_user.id,
        frozenset(
            {
                "providers:read",
                "providers:write",
                "jobs:read",
                "jobs:write",
                "applications:read",
                "applications:write",
            }
        ),
    )
    provider = json_provider_payload().model_dump(mode="json")

    async with create_connected_server_and_client_session(
        server,
        read_timeout_seconds=timedelta(seconds=5),
        raise_exceptions=True,
    ) as session:
        tools = {tool.name: tool for tool in (await session.list_tools()).tools}
        assert tools["create_provider_configuration"].annotations.readOnlyHint is False
        assert tools["delete_provider_configuration"].annotations.destructiveHint is True
        assert tools["list_provider_packs"].annotations.readOnlyHint is True
        assert tools["import_bundled_provider_pack"].annotations.readOnlyHint is False
        assert tools["set_provider_state"].annotations.readOnlyHint is False
        assert "run_job_search" not in tools

        listed_packs = await session.call_tool("list_provider_packs", {})
        imported_pack = await session.call_tool(
            "import_bundled_provider_pack",
            {
                "pack_id": "careeros.switzerland.core",
                "install": {"activate": False},
            },
        )
        job_room = imported_pack.structuredContent["imported"][0]
        enabled_provider = await session.call_tool(
            "set_provider_state",
            {
                "configuration_id": job_room["id"],
                "state": {"expected_revision": 1, "enabled": True},
            },
        )
        validated = await session.call_tool(
            "validate_provider_configuration",
            {"configuration": provider},
        )
        created_provider = await session.call_tool(
            "create_provider_configuration",
            {"configuration": provider},
        )
        created_job = await session.call_tool(
            "create_job",
            {
                "job": {
                    "title": "Platform Engineer",
                    "company": "Example AG",
                    "description": "Build reliable local systems",
                    "location": "Zurich",
                    "external_url": "https://jobs.example.com/platform-engineer",
                    "platform": "manual",
                    "platform_job_id": "agent-job-1",
                }
            },
        )
        application = await session.call_tool(
            "create_application",
            {
                "application": {
                    "job_id": created_job.structuredContent["id"],
                    "initial_stage": "applied",
                    "note": "Submitted through the employer portal",
                }
            },
        )

    assert validated.isError is False
    assert listed_packs.isError is False
    assert "careeros.switzerland.core" in str(listed_packs.structuredContent)
    assert imported_pack.isError is False
    assert imported_pack.structuredContent["activated"] is False
    assert all(
        provider["enabled"] is False
        for provider in imported_pack.structuredContent["imported"]
    )
    assert enabled_provider.isError is False
    assert enabled_provider.structuredContent["enabled"] is True
    assert enabled_provider.structuredContent["revision"] == 2
    assert validated.structuredContent["valid"] is True
    assert created_provider.isError is False
    assert created_provider.structuredContent["request"]["headers"]["X-API-Key"] == (
        "••••••••"
    )
    assert "test-provider-secret" not in str(created_provider.structuredContent)
    assert created_job.isError is False
    assert application.isError is False
    assert application.structuredContent["current_stage"] == "applied"
