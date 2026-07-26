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
from backend.db.base import SessionLocal


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
            "get_resume_catalog",
            "list_applications",
            "get_application_readiness",
            "get_application_agenda",
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
            "get_application_readiness": {"application_id": application.id},
            "get_application_agenda": {"limit": 10},
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
    serialized = str({name: result.structuredContent for name, result in results.items()})
    for forbidden in (
        "events",
        "job_snapshot",
        "document_body",
        "artifact_bytes",
        "prompt",
        "token",
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
        assert [tool.name for tool in tools.tools] == ["get_career_summary"]
        assert all("delete" not in tool.name for tool in tools.tools)
        assert all("restore" not in tool.name for tool in tools.tools)
        assert all("file" not in tool.name for tool in tools.tools)
        assert all("sql" not in tool.name for tool in tools.tools)


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
        "get_resume_catalog": {},
        "list_applications": {},
        "get_application_readiness": {"application_id": "missing"},
        "get_application_agenda": {},
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
