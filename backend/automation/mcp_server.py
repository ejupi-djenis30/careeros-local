"""Read-only MCP stdio transport for a scoped CareerOS automation grant."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager, contextmanager
from typing import TYPE_CHECKING, Annotated, Any, TypeVar

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from backend.automation.grants import (
    TOKEN_ENVIRONMENT_VARIABLE,
    AutomationGrantError,
    authenticate_grant,
)
from backend.automation.runtime import AutomationRuntimeError, automation_runtime
from backend.automation.schemas import (
    AgendaView,
    ApplicationListView,
    ApplicationReadinessView,
    CareerSummaryView,
    LocalModelStatusView,
    ResumeCatalogView,
    SystemStatusView,
)

if TYPE_CHECKING:
    from backend.automation.facade import AutomationFacade

ResultT = TypeVar("ResultT")

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def _safe(call: Callable[..., ResultT], *args: Any, **kwargs: Any) -> ResultT:
    from backend.automation.facade import AutomationFacadeError

    try:
        return call(*args, **kwargs)
    except AutomationFacadeError as exc:
        raise ToolError(f"{exc.code}: {exc}") from None
    except Exception:
        raise ToolError("internal_error: CareerOS could not complete the read operation") from None


async def _safe_async(
    call: Callable[..., Awaitable[ResultT]], *args: Any, **kwargs: Any
) -> ResultT:
    from backend.automation.facade import AutomationFacadeError

    try:
        return await call(*args, **kwargs)
    except AutomationFacadeError as exc:
        raise ToolError(f"{exc.code}: {exc}") from None
    except Exception:
        raise ToolError("internal_error: CareerOS could not complete the read operation") from None


def build_server(
    facade: AutomationFacade,
    *,
    access: Callable[[], AbstractContextManager[None]],
) -> FastMCP:
    access_lock = asyncio.Lock()

    async def read(call: Callable[..., ResultT], *args: Any, **kwargs: Any) -> ResultT:
        async with access_lock:
            try:
                with access():
                    return _safe(call, *args, **kwargs)
            except ToolError:
                raise
            except (AutomationGrantError, AutomationRuntimeError) as exc:
                raise ToolError(f"{exc.code}: {exc}") from None
            except Exception:
                raise ToolError(
                    "internal_error: CareerOS could not authorize the read operation"
                ) from None

    async def read_async(
        call: Callable[..., Awaitable[ResultT]], *args: Any, **kwargs: Any
    ) -> ResultT:
        async with access_lock:
            try:
                with access():
                    return await _safe_async(call, *args, **kwargs)
            except ToolError:
                raise
            except (AutomationGrantError, AutomationRuntimeError) as exc:
                raise ToolError(f"{exc.code}: {exc}") from None
            except Exception:
                raise ToolError(
                    "internal_error: CareerOS could not authorize the read operation"
                ) from None

    server = FastMCP(
        name="CareerOS Local",
        instructions=(
            "Read-only access to one explicitly authorized CareerOS vault. "
            "Tool results are bounded projections, not raw resumes or source documents. "
            "Never ask for passwords, grant tokens, arbitrary files, SQL, or destructive operations."
        ),
        website_url="https://github.com/ejupi-djenis30/careeros-local",
        log_level="ERROR",
    )

    if facade.allows("system:read"):

        async def get_status() -> SystemStatusView:
            """Return product, schema, scope and available-tool metadata without local paths."""

            return await read(facade.system_status)

        async def get_local_model_status() -> LocalModelStatusView:
            """Report whether the required local CareerOS model is installed and ready."""

            return await read_async(facade.local_model_status)

        server.add_tool(get_status, name="get_status", annotations=_READ_ONLY)
        server.add_tool(
            get_local_model_status,
            name="get_local_model_status",
            annotations=_READ_ONLY,
        )

    if facade.allows("career:read"):

        async def get_career_summary() -> CareerSummaryView:
            """Return completeness and fact counts without contact data or career-fact prose."""

            return await read(facade.career_summary)

        server.add_tool(get_career_summary, name="get_career_summary", annotations=_READ_ONLY)

    if facade.allows("resume:read"):

        async def get_resume_catalog() -> ResumeCatalogView:
            """List resume drafts and published versions without document bodies or artifact bytes."""

            return await read(facade.resume_catalog)

        server.add_tool(get_resume_catalog, name="get_resume_catalog", annotations=_READ_ONLY)

    if facade.allows("applications:read"):

        async def list_applications(
            offset: Annotated[int, Field(ge=0, le=100_000)] = 0,
            limit: Annotated[int, Field(ge=1, le=50)] = 25,
        ) -> ApplicationListView:
            """List a bounded page of owned applications and their next-action projection."""

            return await read(facade.list_applications, offset=offset, limit=limit)

        async def get_application_readiness(
            application_id: Annotated[str, Field(min_length=1, max_length=36)],
        ) -> ApplicationReadinessView:
            """Return deterministic preflight checks for one owned application."""

            return await read(facade.application_readiness, application_id)

        async def get_application_agenda(
            horizon_days: Annotated[int, Field(ge=1, le=30)] = 7,
            limit: Annotated[int, Field(ge=1, le=50)] = 25,
            timezone_offset_minutes: Annotated[int, Field(ge=-840, le=840)] = 0,
        ) -> AgendaView:
            """Return prioritized application follow-ups for a bounded local-time window."""

            return await read(
                facade.application_agenda,
                horizon_days=horizon_days,
                limit=limit,
                timezone_offset_minutes=timezone_offset_minutes,
            )

        server.add_tool(list_applications, name="list_applications", annotations=_READ_ONLY)
        server.add_tool(
            get_application_readiness,
            name="get_application_readiness",
            annotations=_READ_ONLY,
        )
        server.add_tool(
            get_application_agenda,
            name="get_application_agenda",
            annotations=_READ_ONLY,
        )

    return server


def run_server(
    *,
    data_dir: str | None,
    acknowledge_agent_disclosure: bool,
    token: str | None = None,
) -> None:
    if not acknowledge_agent_disclosure:
        raise AutomationRuntimeError(
            "disclosure_acknowledgement_required",
            "MCP output can be sent to the connected agent; pass --acknowledge-agent-disclosure",
        )
    bearer = (token or os.environ.get(TOKEN_ENVIRONMENT_VARIABLE, "")).strip()
    if not bearer:
        raise AutomationGrantError(
            "grant_required", f"Set {TOKEN_ENVIRONMENT_VARIABLE} to an active automation grant"
        )

    with automation_runtime(data_dir, migrate=False) as runtime:
        from backend.automation.facade import AutomationFacade

        with runtime.session_factory() as db:
            principal = authenticate_grant(db, bearer)
        facade = AutomationFacade(runtime.session_factory, principal)
        data_root = runtime.data_dir
        session_factory = runtime.session_factory

    from backend.desktop.lifecycle import DesktopInstanceAlreadyRunning, desktop_instance_lease

    @contextmanager
    def authorized_access():
        try:
            with desktop_instance_lease(root=data_root):
                with session_factory() as db:
                    current = authenticate_grant(db, bearer)
                if current != principal:
                    raise AutomationGrantError(
                        "grant_changed", "The automation grant changed; start a new MCP session"
                    )
                yield
        except DesktopInstanceAlreadyRunning as exc:
            raise AutomationRuntimeError(
                "vault_busy", "Close CareerOS Local before reading the vault from MCP"
            ) from exc

    sys.stderr.write("CareerOS MCP: read-only stdio session started\n")
    sys.stderr.flush()
    build_server(facade, access=authorized_access).run(transport="stdio")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CareerOS read-only MCP stdio server")
    parser.add_argument("--data-dir")
    parser.add_argument("--acknowledge-agent-disclosure", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        run_server(
            data_dir=arguments.data_dir,
            acknowledge_agent_disclosure=arguments.acknowledge_agent_disclosure,
        )
    except (AutomationRuntimeError, AutomationGrantError) as exc:
        sys.stderr.write(
            json.dumps({"error": exc.code, "message": str(exc)}, ensure_ascii=False) + "\n"
        )
        return 2
    except Exception:
        sys.stderr.write(
            json.dumps(
                {
                    "error": "internal_error",
                    "message": "CareerOS MCP could not start",
                }
            )
            + "\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
