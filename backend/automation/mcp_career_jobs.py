"""MCP registration for Career Vault, jobs and search."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from backend.automation.mcp_annotations import DESTRUCTIVE, MUTATION, NETWORK_MUTATION, READ_ONLY
from backend.automation.mcp_invocation import AsyncInvoker, SyncInvoker
from backend.career.schemas import CareerProfileResponse, CareerProfileWrite
from backend.schemas.job import JobCreate, JobPaginationResponse, JobResponse, JobUpdate
from backend.schemas.search import AgentSearchRunRequest, AgentSearchRunView

if TYPE_CHECKING:
    from backend.automation.facade import AutomationFacade


def register_career_job_tools(
    server: FastMCP,
    facade: AutomationFacade,
    invoke: SyncInvoker,
    invoke_async: AsyncInvoker,
) -> None:
    if facade.allows("career:read"):

        async def get_career_profile() -> CareerProfileResponse:
            """Return the owned structured Career Vault, including facts needed for truthful work."""

            return await invoke(facade.career_profile)

        server.add_tool(get_career_profile, name="get_career_profile", annotations=READ_ONLY)

    if facade.allows("career:write"):

        async def save_career_profile(profile: CareerProfileWrite) -> CareerProfileResponse:
            """Save the complete Career Vault using its expected revision."""

            return await invoke(facade.save_career_profile, profile)

        server.add_tool(save_career_profile, name="save_career_profile", annotations=MUTATION)

    if facade.allows("jobs:read"):

        async def list_jobs(
            page: Annotated[int, Field(ge=1, le=100_000)] = 1,
            page_size: Annotated[int, Field(ge=1, le=50)] = 20,
            min_score: Annotated[float | None, Field(default=None, ge=0, le=100)] = None,
            worth_applying: bool | None = None,
            applied: bool | None = None,
            include_dismissed: bool = False,
        ) -> JobPaginationResponse:
            """List owned jobs; analysis fields appear only when their local receipt verifies."""

            return await invoke(
                facade.list_jobs,
                page=page,
                page_size=page_size,
                min_score=min_score,
                worth_applying=worth_applying,
                applied=applied,
                include_dismissed=include_dismissed,
            )

        async def get_job(
            job_id: Annotated[int, Field(ge=1)],
        ) -> JobResponse:
            """Get one owned job and its receipt-verified local analysis."""

            return await invoke(facade.get_job, job_id)

        server.add_tool(list_jobs, name="list_jobs", annotations=READ_ONLY)
        server.add_tool(get_job, name="get_job", annotations=READ_ONLY)

    if facade.allows("jobs:write"):

        async def create_job(job: JobCreate) -> JobResponse:
            """Capture a manual job in the owned vault."""

            return await invoke(facade.create_job, job)

        async def update_job(
            job_id: Annotated[int, Field(ge=1)],
            update: JobUpdate,
        ) -> JobResponse:
            """Update owned job interaction flags; Applications remain authoritative for applied."""

            return await invoke(facade.update_job, job_id, update)

        async def record_job_view(
            job_id: Annotated[int, Field(ge=1)],
        ) -> JobResponse:
            """Idempotently record that the agent inspected one job's analysis."""

            return await invoke(facade.record_job_view, job_id)

        async def dismiss_job(
            job_id: Annotated[int, Field(ge=1)],
            feedback_signal: Annotated[str | None, Field(default=None, max_length=40)] = None,
        ) -> JobResponse:
            """Dismiss one owned job with an optional validated feedback signal."""

            return await invoke(facade.dismiss_job, job_id, feedback_signal)

        async def delete_job(
            job_id: Annotated[int, Field(ge=1)],
        ) -> dict[str, bool]:
            """Delete one owned job; applications remain independent historical records."""

            return await invoke(facade.delete_job, job_id)

        server.add_tool(create_job, name="create_job", annotations=MUTATION)
        server.add_tool(update_job, name="update_job", annotations=MUTATION)
        server.add_tool(record_job_view, name="record_job_view", annotations=MUTATION)
        server.add_tool(dismiss_job, name="dismiss_job", annotations=MUTATION)
        server.add_tool(delete_job, name="delete_job", annotations=DESTRUCTIVE)

    if facade.allows("search:execute") and facade.allows("jobs:read"):

        async def run_job_search(search: AgentSearchRunRequest) -> AgentSearchRunView:
            """Run enabled providers and mandatory local-model analysis, then return owned jobs."""

            return await invoke_async(facade.run_job_search, search)

        server.add_tool(run_job_search, name="run_job_search", annotations=NETWORK_MUTATION)
