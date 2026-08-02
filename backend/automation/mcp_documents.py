"""MCP registration for resume and application workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from backend.applications.schemas import (
    ApplicationCreate,
    ApplicationDossierCreate,
    ApplicationDossierDraftPut,
    ApplicationDossierDraftResponse,
    ApplicationEventCreate,
    ApplicationPreparationUpdate,
    ApplicationResponse,
    ApplicationTaskCreate,
    ApplicationTaskUpdate,
)
from backend.automation.mcp_annotations import DESTRUCTIVE, MUTATION, READ_ONLY
from backend.automation.mcp_invocation import SyncInvoker
from backend.resumes.schemas import (
    ResumeDraftResponse,
    ResumeDraftUpdate,
    ResumeGenerate,
    ResumePublishRequest,
    ResumeVersionResponse,
)

if TYPE_CHECKING:
    from backend.automation.facade import AutomationFacade


def register_document_application_tools(
    server: FastMCP,
    facade: AutomationFacade,
    invoke: SyncInvoker,
) -> None:
    if facade.allows("resume:read"):

        async def get_resume(
            resume_id: Annotated[str, Field(min_length=36, max_length=36)],
        ) -> ResumeDraftResponse:
            """Get one owned structured resume draft and its published version metadata."""

            return await invoke(facade.get_resume, resume_id)

        server.add_tool(get_resume, name="get_resume", annotations=READ_ONLY)

    if facade.allows("resume:write"):

        async def generate_resume(resume: ResumeGenerate) -> ResumeDraftResponse:
            """Generate a truthful draft from confirmed Career Vault facts for an optional job."""

            return await invoke(facade.generate_resume, resume)

        async def update_resume(
            resume_id: Annotated[str, Field(min_length=36, max_length=36)],
            resume: ResumeDraftUpdate,
        ) -> ResumeDraftResponse:
            """Update a resume draft with an expected revision and fact-bound overrides."""

            return await invoke(facade.update_resume, resume_id, resume)

        async def publish_resume(
            resume_id: Annotated[str, Field(min_length=36, max_length=36)],
            publication: ResumePublishRequest,
        ) -> ResumeVersionResponse:
            """Render and validate local PDF/DOCX artifacts for an owned resume draft."""

            return await invoke(facade.publish_resume, resume_id, publication)

        server.add_tool(generate_resume, name="generate_resume", annotations=MUTATION)
        server.add_tool(update_resume, name="update_resume", annotations=MUTATION)
        server.add_tool(publish_resume, name="publish_resume", annotations=MUTATION)

    if facade.allows("applications:read"):

        async def get_application(
            application_id: Annotated[str, Field(min_length=36, max_length=36)],
        ) -> ApplicationResponse:
            """Get one owned application with immutable events, tasks and dossier summaries."""

            return await invoke(facade.get_application, application_id)

        async def get_application_dossier_draft(
            application_id: Annotated[str, Field(min_length=36, max_length=36)],
        ) -> ApplicationDossierDraftResponse | None:
            """Get the mutable dossier draft for one owned application, if present."""

            return await invoke(facade.get_application_dossier_draft, application_id)

        server.add_tool(get_application, name="get_application", annotations=READ_ONLY)
        server.add_tool(
            get_application_dossier_draft,
            name="get_application_dossier_draft",
            annotations=READ_ONLY,
        )

    if facade.allows("applications:write"):

        async def create_application(application: ApplicationCreate) -> ApplicationResponse:
            """Track an owned job or manual opportunity, optionally beginning at applied."""

            return await invoke(facade.create_application, application)

        async def append_application_event(
            application_id: Annotated[str, Field(min_length=36, max_length=36)],
            event: ApplicationEventCreate,
        ) -> ApplicationResponse:
            """Append a revision-checked stage, note, contact or interview event."""

            return await invoke(facade.append_application_event, application_id, event)

        async def update_application_preparation(
            application_id: Annotated[str, Field(min_length=36, max_length=36)],
            preparation: ApplicationPreparationUpdate,
        ) -> ApplicationResponse:
            """Revision-check editable job and application-channel details before applying."""

            return await invoke(
                facade.update_application_preparation,
                application_id,
                preparation,
            )

        async def create_application_task(
            application_id: Annotated[str, Field(min_length=36, max_length=36)],
            task: ApplicationTaskCreate,
        ) -> ApplicationResponse:
            """Create revision-checked follow-up work for an application."""

            return await invoke(facade.create_application_task, application_id, task)

        async def update_application_task(
            application_id: Annotated[str, Field(min_length=36, max_length=36)],
            task_id: Annotated[str, Field(min_length=36, max_length=36)],
            task: ApplicationTaskUpdate,
        ) -> ApplicationResponse:
            """Update or complete an application task at the expected application revision."""

            return await invoke(
                facade.update_application_task,
                application_id,
                task_id,
                task,
            )

        async def put_application_dossier_draft(
            application_id: Annotated[str, Field(min_length=36, max_length=36)],
            dossier: ApplicationDossierDraftPut,
        ) -> ApplicationDossierDraftResponse:
            """Create or update fact-linked application materials with both expected revisions."""

            return await invoke(
                facade.put_application_dossier_draft,
                application_id,
                dossier,
            )

        async def publish_application_dossier(
            application_id: Annotated[str, Field(min_length=36, max_length=36)],
            dossier: ApplicationDossierCreate,
        ) -> ApplicationResponse:
            """Publish the exact saved dossier after readiness and evidence validation."""

            return await invoke(
                facade.publish_application_dossier,
                application_id,
                dossier,
            )

        async def delete_application_dossier_draft(
            application_id: Annotated[str, Field(min_length=36, max_length=36)],
            expected_revision: Annotated[int, Field(ge=1)],
        ) -> dict[str, bool]:
            """Delete one owned dossier draft at its expected revision."""

            return await invoke(
                facade.delete_application_dossier_draft,
                application_id,
                expected_revision=expected_revision,
            )

        server.add_tool(create_application, name="create_application", annotations=MUTATION)
        server.add_tool(
            append_application_event,
            name="append_application_event",
            annotations=MUTATION,
        )
        server.add_tool(
            update_application_preparation,
            name="update_application_preparation",
            annotations=MUTATION,
        )
        server.add_tool(
            create_application_task,
            name="create_application_task",
            annotations=MUTATION,
        )
        server.add_tool(
            update_application_task,
            name="update_application_task",
            annotations=MUTATION,
        )
        server.add_tool(
            put_application_dossier_draft,
            name="put_application_dossier_draft",
            annotations=MUTATION,
        )
        server.add_tool(
            delete_application_dossier_draft,
            name="delete_application_dossier_draft",
            annotations=DESTRUCTIVE,
        )
        server.add_tool(
            publish_application_dossier,
            name="publish_application_dossier",
            annotations=MUTATION,
        )
