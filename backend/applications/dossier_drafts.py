"""Orchestration service for application dossiers, draft bindings, and enhanced packets."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from backend.applications.dossier_queries import DossierQueryService
from backend.applications.exceptions import (
    ApplicationConflictError,
    ApplicationNotFoundError,
    ApplicationValidationError,
)
from backend.applications.models import (
    Application,
    ApplicationDossierDraft,
)
from backend.applications.schemas import (
    ApplicationDossierDraftPut,
    ApplicationDossierDraftResponse,
)
from backend.resumes.models import ResumeDraft


class DossierDraftService(DossierQueryService):
    def get_dossier_draft(
        self,
        user_id: int,
        application_id: str,
    ) -> ApplicationDossierDraftResponse | None:
        application = self._application(user_id, application_id)
        draft = (
            self.db.query(ApplicationDossierDraft)
            .filter(ApplicationDossierDraft.application_id == application.id)
            .one_or_none()
        )
        if draft is None:
            return None
        return ApplicationDossierDraftResponse.model_validate(draft)

    def _ensure_current_dossier_draft_binding(
        self,
        user_id: int,
        application_id: str,
        application_revision: int,
        resume_version_id: str | None,
    ) -> None:
        current = (
            self.db.query(Application.revision, Application.resume_version_id)
            .filter(Application.id == application_id, Application.user_id == user_id)
            .one_or_none()
        )
        if (
            current is None
            or current.revision != application_revision
            or (resume_version_id is not None and current.resume_version_id != resume_version_id)
        ):
            raise ApplicationConflictError("The application or linked resume changed while saving")

    def mutate_dossier_draft_flush_only(
        self,
        user_id: int,
        application_id: str,
        data: ApplicationDossierDraftPut,
    ) -> ApplicationDossierDraft:
        """Mutate one dossier draft and flush without committing or publishing.

        This focused seam is safe for outer transaction orchestrators (e.g.
        agent material acceptance) that need to enforce ownership, binding,
        and CAS checks atomically with their own domain models.
        """
        self._application(user_id, application_id)
        with self.db.no_autoflush:
            locked = (
                self.db.query(Application)
                .filter(
                    Application.id == application_id,
                    Application.user_id == user_id,
                    Application.revision == data.expected_application_revision,
                )
                .update({Application.revision: Application.revision}, synchronize_session=False)
            )
        if locked != 1:
            raise ApplicationConflictError("The application changed while saving the dossier")
        application = self._application(user_id, application_id)
        if application.revision != data.expected_application_revision:
            raise ApplicationConflictError(
                "The application changed while this dossier draft was being edited"
            )

        # Exactly-one binding check
        has_version = data.resume_version_id is not None
        has_draft = data.resume_draft_id is not None
        if has_version == has_draft:
            raise ApplicationValidationError(
                "Dossier draft must bind exactly one of resume_draft_id or resume_version_id"
            )

        resume_version_id: str | None = None
        resume_draft_id: str | None = None
        resume_draft_revision: int | None = None

        if has_version:
            v_id = str(data.resume_version_id)
            version = self._resume_version(user_id, v_id)
            if version is None:
                raise ApplicationValidationError("The linked resume version is unavailable")
            if application.resume_version_id and application.resume_version_id != v_id:
                raise ApplicationConflictError(
                    "The linked resume changed while this dossier draft was being edited"
                )
            resume_version_id = v_id
        else:
            d_id = str(data.resume_draft_id)
            rdraft = self._resume_draft(user_id, d_id)
            if rdraft is None:
                raise ApplicationValidationError("The linked resume draft is unavailable")
            if (
                data.expected_resume_draft_revision is not None
                and rdraft.revision != data.expected_resume_draft_revision
            ):
                raise ApplicationConflictError(
                    "The linked resume draft changed in another editor; reload before saving"
                )
            with self.db.no_autoflush:
                locked_resume = (
                    self.db.query(ResumeDraft)
                    .filter(
                        ResumeDraft.id == d_id,
                        ResumeDraft.revision == data.expected_resume_draft_revision,
                    )
                    .update({ResumeDraft.revision: ResumeDraft.revision}, synchronize_session=False)
                )
            if locked_resume != 1:
                raise ApplicationConflictError("The linked resume draft changed while saving")
            resume_draft_id = d_id
            resume_draft_revision = data.expected_resume_draft_revision

        content = data.content.model_dump(mode="json")
        now = datetime.now(timezone.utc)

        existing = (
            self.db.query(ApplicationDossierDraft)
            .filter(ApplicationDossierDraft.application_id == application.id)
            .one_or_none()
        )

        if data.expected_revision is None:
            if existing is not None:
                raise ApplicationConflictError(
                    "The dossier draft already exists; reload before saving"
                )
            draft = ApplicationDossierDraft(
                application_id=application.id,
                resume_version_id=resume_version_id,
                resume_draft_id=resume_draft_id,
                resume_draft_revision=resume_draft_revision,
                application_revision=application.revision,
                revision=1,
                content=content,
                created_at=now,
                updated_at=now,
            )
            self.db.add(draft)
            try:
                self.db.flush()
            except IntegrityError as exc:
                raise ApplicationConflictError(
                    "The application, linked resume or dossier draft changed while saving"
                ) from exc
            self._ensure_current_dossier_draft_binding(
                user_id, application.id, data.expected_application_revision, resume_version_id
            )
            return draft

        # Updating existing draft
        if existing is None:
            raise ApplicationConflictError("The dossier draft no longer exists")
        if existing.revision != data.expected_revision:
            raise ApplicationConflictError(
                "The dossier draft changed in another editor; reload before saving"
            )

        with self.db.no_autoflush:
            changed = (
                self.db.query(ApplicationDossierDraft)
                .filter(
                    ApplicationDossierDraft.id == existing.id,
                    ApplicationDossierDraft.revision == data.expected_revision,
                )
                .update(
                    dict(
                        resume_version_id=resume_version_id,
                        resume_draft_id=resume_draft_id,
                        resume_draft_revision=resume_draft_revision,
                        application_revision=data.expected_application_revision,
                        revision=data.expected_revision + 1,
                        content=content,
                        updated_at=now,
                    ),
                    synchronize_session=False,
                )
            )
        if changed != 1:
            raise ApplicationConflictError("The dossier draft changed while saving")
        self.db.flush()
        self.db.refresh(existing)

        self._ensure_current_dossier_draft_binding(
            user_id, application.id, data.expected_application_revision, resume_version_id
        )
        return existing

    def put_dossier_draft(
        self,
        user_id: int,
        application_id: str,
        data: ApplicationDossierDraftPut,
    ) -> ApplicationDossierDraftResponse:
        try:
            stored = self.mutate_dossier_draft_flush_only(user_id, application_id, data)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.expire_all()
        refreshed = (
            self.db.query(ApplicationDossierDraft)
            .filter(ApplicationDossierDraft.id == stored.id)
            .one()
        )
        return ApplicationDossierDraftResponse.model_validate(refreshed)

    def delete_dossier_draft(
        self,
        user_id: int,
        application_id: str,
        expected_revision: int,
    ) -> None:
        application = self._application(user_id, application_id)
        result = self.db.execute(
            delete(ApplicationDossierDraft).where(
                ApplicationDossierDraft.application_id == application.id,
                ApplicationDossierDraft.revision == expected_revision,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            self.db.rollback()
            existing = (
                self.db.query(ApplicationDossierDraft.application_id)
                .filter(ApplicationDossierDraft.application_id == application.id)
                .first()
            )
            if existing is None:
                raise ApplicationNotFoundError("Application dossier draft not found")
            raise ApplicationConflictError(
                "The dossier draft changed in another editor; reload before deleting"
            )
        self.db.commit()
