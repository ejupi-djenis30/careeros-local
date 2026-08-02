"""Career profile, job catalog and search operations for automation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from pydantic import ValidationError

from backend.career.repository import CareerProfileConflictError
from backend.career.schemas import CareerProfileResponse, CareerProfileWrite
from backend.career.service import CareerProfileService
from backend.models import Job
from backend.schemas.job import JobCreate, JobPaginationResponse, JobResponse, JobUpdate
from backend.schemas.search import AgentSearchRunRequest, AgentSearchRunView
from backend.search.agent_campaign import AgentSearchError, run_agent_search
from backend.services.job_service import JobService

if TYPE_CHECKING:
    from backend.automation.grants import AutomationPrincipal
    from backend.automation.schemas import AutomationScope


class CareerJobOperationsMixin:
    if TYPE_CHECKING:
        _session_factory: Any
        principal: AutomationPrincipal

        def _require(self, scope: AutomationScope) -> None: ...

    def career_profile(self) -> CareerProfileResponse:
        self._require("career:read")
        with self._session_factory() as db:
            profile = CareerProfileService(db).get(self.principal.user_id)
        if profile is None:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError("career_profile_not_found", "Career profile not found")
        return profile

    def save_career_profile(self, payload: CareerProfileWrite) -> CareerProfileResponse:
        self._require("career:write")
        try:
            with self._session_factory() as db:
                return CareerProfileService(db).save(self.principal.user_id, payload)
        except (CareerProfileConflictError, ValueError, ValidationError) as exc:
            from backend.automation.facade import AutomationFacadeError

            code = (
                "revision_conflict"
                if isinstance(exc, CareerProfileConflictError)
                else "invalid_profile"
            )
            raise AutomationFacadeError(code, str(exc)) from exc

    def list_jobs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        min_score: float | None = None,
        worth_applying: bool | None = None,
        applied: bool | None = None,
        include_dismissed: bool = False,
    ) -> JobPaginationResponse:
        self._require("jobs:read")
        if page < 1 or not 1 <= page_size <= 50:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError("invalid_page", "Page parameters are invalid")
        filters = {
            "min_score": min_score,
            "worth_applying": worth_applying,
            "applied": applied,
            "include_dismissed": include_dismissed,
            "sort_by": "affinity_score",
            "sort_order": "desc",
        }
        with self._session_factory() as db:
            return JobPaginationResponse.model_validate(
                JobService(db).get_jobs_by_user(
                    self.principal.user_id, page, page_size, filters
                )
            )

    def get_job(self, job_id: int) -> JobResponse:
        self._require("jobs:read")
        with self._session_factory() as db:
            job = (
                db.query(Job)
                .filter(Job.id == job_id, Job.user_id == self.principal.user_id)
                .first()
            )
            if job is None:
                from backend.automation.facade import AutomationFacadeError

                raise AutomationFacadeError("job_not_found", "Job not found")
            service = JobService(db)
            service._mark_analysis_receipt(job, self.principal.user_id)
            service._with_application_link(self.principal.user_id, job)
            return JobResponse.model_validate(job)

    def create_job(self, payload: JobCreate) -> JobResponse:
        self._require("jobs:write")
        try:
            with self._session_factory() as db:
                row = JobService(db).create_job(self.principal.user_id, payload)
                return JobResponse.model_validate(row)
        except (HTTPException, ValueError, ValidationError) as exc:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError("invalid_job", str(exc)) from exc

    def update_job(self, job_id: int, payload: JobUpdate) -> JobResponse:
        self._require("jobs:write")
        try:
            with self._session_factory() as db:
                row = JobService(db).update_job(self.principal.user_id, job_id, payload)
                return JobResponse.model_validate(row)
        except (HTTPException, ValueError) as exc:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError("job_update_failed", str(exc)) from exc

    def record_job_view(self, job_id: int) -> JobResponse:
        self._require("jobs:write")
        try:
            with self._session_factory() as db:
                row = JobService(db).record_view(self.principal.user_id, job_id)
                return JobResponse.model_validate(row)
        except (HTTPException, ValueError) as exc:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError("job_update_failed", str(exc)) from exc

    def dismiss_job(self, job_id: int, feedback_signal: str | None = None) -> JobResponse:
        self._require("jobs:write")
        try:
            payload = JobUpdate(dismissed=True, feedback_signal=feedback_signal)
            with self._session_factory() as db:
                row = JobService(db).update_job(self.principal.user_id, job_id, payload)
                return JobResponse.model_validate(row)
        except (HTTPException, ValueError, ValidationError) as exc:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError("job_update_failed", str(exc)) from exc

    def delete_job(self, job_id: int) -> dict[str, bool]:
        self._require("jobs:write")
        try:
            with self._session_factory() as db:
                JobService(db).delete_job(self.principal.user_id, job_id)
        except (HTTPException, ValueError) as exc:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError("job_delete_failed", str(exc)) from exc
        return {"deleted": True}

    async def run_job_search(self, payload: AgentSearchRunRequest) -> AgentSearchRunView:
        self._require("search:execute")
        self._require("jobs:read")
        try:
            with self._session_factory() as db:
                return await run_agent_search(
                    db,
                    user_id=self.principal.user_id,
                    request=payload,
                )
        except AgentSearchError as exc:
            from backend.automation.facade import AutomationFacadeError

            raise AutomationFacadeError(exc.code, str(exc)) from exc
