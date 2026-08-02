"""Resume and application operations for scoped automation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn

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
from backend.applications.service import (
    ApplicationConflictError,
    ApplicationNotFoundError,
    ApplicationService,
    ApplicationValidationError,
)
from backend.resumes.schemas import (
    ResumeDraftResponse,
    ResumeDraftUpdate,
    ResumeGenerate,
    ResumePublishRequest,
    ResumeVersionResponse,
)
from backend.resumes.service import (
    ResumeConflictError,
    ResumeNotFoundError,
    ResumeService,
    ResumeValidationError,
)
from backend.storage.atomic import StorageWriteError

if TYPE_CHECKING:
    from backend.automation.grants import AutomationPrincipal
    from backend.automation.schemas import AutomationScope


class DocumentApplicationOperationsMixin:
    if TYPE_CHECKING:
        _session_factory: Any
        principal: AutomationPrincipal

        def _require(self, scope: AutomationScope) -> None: ...

    @staticmethod
    def _raise_application_error(exc: Exception) -> NoReturn:
        from backend.automation.facade import AutomationFacadeError

        if isinstance(exc, ApplicationNotFoundError):
            code = "application_not_found"
        elif isinstance(exc, ApplicationConflictError):
            code = "revision_conflict"
        else:
            code = "invalid_application"
        raise AutomationFacadeError(code, str(exc)) from exc

    @staticmethod
    def _raise_resume_error(exc: Exception) -> NoReturn:
        from backend.automation.facade import AutomationFacadeError

        if isinstance(exc, ResumeNotFoundError):
            code = "resume_not_found"
        elif isinstance(exc, ResumeConflictError):
            code = "revision_conflict"
        elif isinstance(exc, StorageWriteError):
            code = "storage_unavailable"
        else:
            code = "invalid_resume"
        raise AutomationFacadeError(code, str(exc)) from exc

    def get_resume(self, resume_id: str) -> ResumeDraftResponse:
        self._require("resume:read")
        try:
            with self._session_factory() as db:
                return ResumeService(db).get(self.principal.user_id, resume_id)
        except ResumeNotFoundError as exc:
            self._raise_resume_error(exc)

    def generate_resume(self, payload: ResumeGenerate) -> ResumeDraftResponse:
        self._require("resume:write")
        try:
            with self._session_factory() as db:
                return ResumeService(db).generate(self.principal.user_id, payload)
        except (ResumeValidationError, ResumeConflictError, ResumeNotFoundError, ValueError) as exc:
            self._raise_resume_error(exc)

    def update_resume(self, resume_id: str, payload: ResumeDraftUpdate) -> ResumeDraftResponse:
        self._require("resume:write")
        try:
            with self._session_factory() as db:
                return ResumeService(db).update(self.principal.user_id, resume_id, payload)
        except (ResumeValidationError, ResumeConflictError, ResumeNotFoundError) as exc:
            self._raise_resume_error(exc)

    def publish_resume(
        self, resume_id: str, payload: ResumePublishRequest
    ) -> ResumeVersionResponse:
        self._require("resume:write")
        try:
            with self._session_factory() as db:
                return ResumeService(db).publish(self.principal.user_id, resume_id, payload)
        except (
            ResumeValidationError,
            ResumeConflictError,
            ResumeNotFoundError,
            StorageWriteError,
            ValueError,
        ) as exc:
            self._raise_resume_error(exc)

    def get_application(self, application_id: str) -> ApplicationResponse:
        self._require("applications:read")
        try:
            with self._session_factory() as db:
                return ApplicationService(db).get(self.principal.user_id, application_id)
        except (ApplicationNotFoundError, ApplicationValidationError) as exc:
            self._raise_application_error(exc)

    def create_application(self, payload: ApplicationCreate) -> ApplicationResponse:
        self._require("applications:write")
        try:
            with self._session_factory() as db:
                return ApplicationService(db).create(self.principal.user_id, payload)
        except (
            ApplicationNotFoundError,
            ApplicationConflictError,
            ApplicationValidationError,
        ) as exc:
            self._raise_application_error(exc)

    def append_application_event(
        self, application_id: str, payload: ApplicationEventCreate
    ) -> ApplicationResponse:
        self._require("applications:write")
        try:
            with self._session_factory() as db:
                return ApplicationService(db).append_event(
                    self.principal.user_id, application_id, payload
                )
        except (
            ApplicationNotFoundError,
            ApplicationConflictError,
            ApplicationValidationError,
        ) as exc:
            self._raise_application_error(exc)

    def update_application_preparation(
        self, application_id: str, payload: ApplicationPreparationUpdate
    ) -> ApplicationResponse:
        self._require("applications:write")
        try:
            with self._session_factory() as db:
                return ApplicationService(db).update_preparation(
                    self.principal.user_id, application_id, payload
                )
        except (
            ApplicationNotFoundError,
            ApplicationConflictError,
            ApplicationValidationError,
        ) as exc:
            self._raise_application_error(exc)

    def create_application_task(
        self, application_id: str, payload: ApplicationTaskCreate
    ) -> ApplicationResponse:
        self._require("applications:write")
        try:
            with self._session_factory() as db:
                return ApplicationService(db).create_task(
                    self.principal.user_id, application_id, payload
                )
        except (
            ApplicationNotFoundError,
            ApplicationConflictError,
            ApplicationValidationError,
        ) as exc:
            self._raise_application_error(exc)

    def update_application_task(
        self,
        application_id: str,
        task_id: str,
        payload: ApplicationTaskUpdate,
    ) -> ApplicationResponse:
        self._require("applications:write")
        try:
            with self._session_factory() as db:
                return ApplicationService(db).update_task(
                    self.principal.user_id, application_id, task_id, payload
                )
        except (
            ApplicationNotFoundError,
            ApplicationConflictError,
            ApplicationValidationError,
        ) as exc:
            self._raise_application_error(exc)

    def get_application_dossier_draft(
        self, application_id: str
    ) -> ApplicationDossierDraftResponse | None:
        self._require("applications:read")
        try:
            with self._session_factory() as db:
                return ApplicationService(db).get_dossier_draft(
                    self.principal.user_id, application_id
                )
        except (ApplicationNotFoundError, ApplicationValidationError) as exc:
            self._raise_application_error(exc)

    def put_application_dossier_draft(
        self,
        application_id: str,
        payload: ApplicationDossierDraftPut,
    ) -> ApplicationDossierDraftResponse:
        self._require("applications:write")
        try:
            with self._session_factory() as db:
                return ApplicationService(db).put_dossier_draft(
                    self.principal.user_id, application_id, payload
                )
        except (
            ApplicationNotFoundError,
            ApplicationConflictError,
            ApplicationValidationError,
        ) as exc:
            self._raise_application_error(exc)

    def delete_application_dossier_draft(
        self,
        application_id: str,
        *,
        expected_revision: int,
    ) -> dict[str, bool]:
        self._require("applications:write")
        try:
            with self._session_factory() as db:
                ApplicationService(db).delete_dossier_draft(
                    self.principal.user_id,
                    application_id,
                    expected_revision,
                )
        except (ApplicationNotFoundError, ApplicationConflictError) as exc:
            self._raise_application_error(exc)
        return {"deleted": True}

    def publish_application_dossier(
        self,
        application_id: str,
        payload: ApplicationDossierCreate,
    ) -> ApplicationResponse:
        self._require("applications:write")
        try:
            with self._session_factory() as db:
                return ApplicationService(db).publish_dossier(
                    self.principal.user_id, application_id, payload
                )
        except (
            ApplicationNotFoundError,
            ApplicationConflictError,
            ApplicationValidationError,
        ) as exc:
            self._raise_application_error(exc)
