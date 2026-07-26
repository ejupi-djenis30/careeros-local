"""Least-privilege read facade shared by the CLI and MCP transport."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta, timezone
from typing import Any, cast

from sqlalchemy import text

from backend import __version__
from backend.applications.agenda import ApplicationAgendaService
from backend.applications.service import (
    ApplicationNotFoundError,
    ApplicationService,
    ApplicationValidationError,
)
from backend.automation.grants import AutomationPrincipal
from backend.automation.schemas import (
    ALL_AUTOMATION_SCOPES,
    AgendaItemView,
    AgendaView,
    ApplicationListView,
    ApplicationReadinessView,
    ApplicationSummaryView,
    AutomationScope,
    CareerSummaryView,
    LocalModelStatusView,
    NextActionView,
    ResumeCatalogView,
    ResumeSummaryView,
    ResumeVersionView,
    SystemStatusView,
)
from backend.career.service import CareerProfileService
from backend.resumes.service import ResumeService


class AutomationFacadeError(RuntimeError):
    """A stable, redacted tool error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AutomationFacade:
    """One scoped principal with a fresh database session per read operation."""

    def __init__(self, session_factory: Any, principal: AutomationPrincipal) -> None:
        self._session_factory = session_factory
        self.principal = principal

    def allows(self, scope: AutomationScope) -> bool:
        return self.principal.allows(scope)

    def _require(self, scope: AutomationScope) -> None:
        if not self.allows(scope):
            raise AutomationFacadeError("scope_denied", f"Grant requires the {scope} scope")

    @staticmethod
    def _next_action(value: Any) -> NextActionView | None:
        if value is None:
            return None
        return NextActionView(
            id=value.id,
            title=value.title,
            due_at=value.due_at,
            priority=value.priority,
        )

    def system_status(self) -> SystemStatusView:
        self._require("system:read")
        with self._session_factory() as db:
            revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tools = ["get_status"]
        if self.allows("system:read"):
            tools.append("get_local_model_status")
        if self.allows("career:read"):
            tools.append("get_career_summary")
        if self.allows("resume:read"):
            tools.append("get_resume_catalog")
        if self.allows("applications:read"):
            tools.extend(
                ["list_applications", "get_application_readiness", "get_application_agenda"]
            )
        scopes = [scope for scope in ALL_AUTOMATION_SCOPES if scope in self.principal.scopes]
        return SystemStatusView(
            product_version=__version__,
            database_revision=revision,
            granted_scopes=scopes,
            available_tools=tools,
        )

    async def local_model_status(self) -> LocalModelStatusView:
        self._require("system:read")
        from backend.inference.service import get_local_model_status

        try:
            status = await get_local_model_status()
        except Exception as exc:
            raise AutomationFacadeError(
                "model_status_unavailable", "Local model status is unavailable"
            ) from exc
        return LocalModelStatusView(
            required=status.required,
            analysis_required=status.analysis_required,
            available=status.available,
            ready=status.ready,
            configured_model=status.configured_model,
            installed_model_count=len(status.installed_models),
            error_code=status.error_code,
            runtime=status.runtime,
        )

    def career_summary(self) -> CareerSummaryView:
        self._require("career:read")
        with self._session_factory() as db:
            summary = CareerProfileService(db).summary(self.principal.user_id)
        if summary is None:
            return CareerSummaryView(profile_exists=False)
        return CareerSummaryView(
            profile_exists=True,
            revision=summary.revision,
            fact_counts=summary.fact_counts,
            goal_count=summary.goal_count,
            completeness_score=summary.completeness_score,
            issue_count=summary.issue_count,
            updated_at=summary.updated_at,
        )

    def list_applications(self, *, offset: int = 0, limit: int = 25) -> ApplicationListView:
        self._require("applications:read")
        if offset < 0 or not 1 <= limit <= 50:
            raise AutomationFacadeError(
                "invalid_page", "Offset must be non-negative and limit 1 to 50"
            )
        try:
            with self._session_factory() as db:
                items = ApplicationService(db).list(
                    self.principal.user_id, offset=offset, limit=limit
                )
        except ApplicationValidationError as exc:
            raise AutomationFacadeError(
                "application_projection_invalid",
                "Application summaries are temporarily unavailable",
            ) from exc
        mapped = [
            ApplicationSummaryView(
                id=item.id,
                revision=item.revision,
                current_stage=item.current_stage,
                title=item.title,
                company=item.company,
                location=item.location,
                latest_event_at=item.latest_event_at,
                updated_at=item.updated_at,
                next_action=self._next_action(item.next_action),
            )
            for item in items
        ]
        return ApplicationListView(
            items=mapped,
            offset=offset,
            limit=limit,
            returned_count=len(mapped),
        )

    def application_readiness(self, application_id: str) -> ApplicationReadinessView:
        self._require("applications:read")
        if not application_id or len(application_id) > 36:
            raise AutomationFacadeError("invalid_application_id", "Application ID is invalid")
        try:
            with self._session_factory() as db:
                report = ApplicationService(db).readiness(self.principal.user_id, application_id)
        except ApplicationNotFoundError as exc:
            raise AutomationFacadeError("application_not_found", "Application not found") from exc
        except ApplicationValidationError as exc:
            raise AutomationFacadeError(
                "readiness_unavailable", "Application readiness is unavailable"
            ) from exc
        return cast(
            ApplicationReadinessView,
            ApplicationReadinessView.model_validate(
                report.model_dump(mode="python", exclude={"schema_version", "score_kind"})
            ),
        )

    def application_agenda(
        self,
        *,
        horizon_days: int = 7,
        limit: int = 25,
        timezone_offset_minutes: int = 0,
    ) -> AgendaView:
        self._require("applications:read")
        if not 1 <= horizon_days <= 30 or not 1 <= limit <= 50:
            raise AutomationFacadeError(
                "invalid_agenda_window", "Agenda horizon must be 1 to 30 days and limit 1 to 50"
            )
        if not -840 <= timezone_offset_minutes <= 840:
            raise AutomationFacadeError(
                "invalid_timezone", "Timezone offset must be between -840 and 840 minutes"
            )
        local_zone = timezone(timedelta(minutes=timezone_offset_minutes))
        now = datetime.now(UTC)
        local_now = now.astimezone(local_zone)
        local_day_end = datetime.combine(
            local_now.date() + timedelta(days=1), time.min, tzinfo=local_zone
        )
        try:
            with self._session_factory() as db:
                agenda = ApplicationAgendaService(db).build(
                    self.principal.user_id,
                    local_day_end=local_day_end,
                    horizon_days=horizon_days,
                    limit=limit,
                    now=now,
                )
        except ApplicationValidationError as exc:
            raise AutomationFacadeError(
                "agenda_unavailable", "Application agenda is unavailable"
            ) from exc
        items = [
            AgendaItemView(
                application_id=item.application_id,
                application_revision=item.application_revision,
                title=item.title,
                company=item.company,
                current_stage=item.current_stage,
                latest_event_at=item.latest_event_at,
                state=item.state,
                next_action=self._next_action(item.next_action),
            )
            for item in agenda.items
        ]
        return AgendaView(
            generated_at=agenda.generated_at,
            local_day_end=agenda.local_day_end,
            horizon_end=agenda.horizon_end,
            active_count=agenda.active_count,
            visible_count=agenda.visible_count,
            later_count=agenda.later_count,
            truncated_count=agenda.truncated_count,
            items=items,
        )

    def resume_catalog(self) -> ResumeCatalogView:
        self._require("resume:read")
        with self._session_factory() as db:
            service = ResumeService(db)
            resumes = service.list_resumes(self.principal.user_id)[:50]
            versions = service.list_versions(self.principal.user_id)[:100]
        return ResumeCatalogView(
            resumes=[
                ResumeSummaryView(
                    id=item.id,
                    revision=item.revision,
                    title=item.title,
                    template_kind=item.template_kind,
                    selected_fact_count=item.selected_fact_count,
                    latest_version=item.latest_version,
                    updated_at=item.updated_at,
                )
                for item in resumes
            ],
            published_versions=[
                ResumeVersionView(
                    id=item.id,
                    draft_id=item.draft_id,
                    draft_title=item.draft_title,
                    semantic_version=item.semantic_version,
                    name=item.name,
                    published_at=item.published_at,
                )
                for item in versions
            ],
        )
