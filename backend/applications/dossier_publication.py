"""Orchestration service for application dossiers, draft bindings, and enhanced packets."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import delete, text

from backend.applications.dossier_content import (
    _publishable_draft_content,
    _requested_dossier_content,
)
from backend.applications.dossier_materials import build_packet_materials
from backend.applications.dossier_queries import DossierQueryService
from backend.applications.exceptions import (
    ApplicationConflictError,
    ApplicationValidationError,
)
from backend.applications.models import (
    ApplicationDossierDraft,
    ApplicationEvent,
    ApplicationPacketArtifact,
)
from backend.applications.packet_storage import (
    read_verified_packet_artifact,
    reconcile_packet_journals,
    remove_packet_journal,
    store_packet_artifact,
)
from backend.applications.readiness import ApplicationReadinessService
from backend.applications.schemas import (
    ApplicationDossierCreate,
    ApplicationResponse,
)
from backend.career.models import CandidateProfile
from backend.desktop.lifecycle import desktop_vault_lock
from backend.models.user import VAULT_STATE_READY, User
from backend.storage.atomic import StorageWriteError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from backend.applications.service import ApplicationService


class DossierPublicationService(DossierQueryService):
    def publish_dossier(
        self,
        user_id: int,
        application_id: str,
        data: ApplicationDossierCreate,
        application_service_helper: ApplicationService,
    ) -> ApplicationResponse:
        with desktop_vault_lock():
            self.db.rollback()
            self.db.execute(text("BEGIN IMMEDIATE"))
            try:
                reconcile_packet_journals(self.db)
                if (
                    self.db.query(User.vault_lifecycle_state).filter(User.id == user_id).scalar()
                    != VAULT_STATE_READY
                ):
                    raise ApplicationConflictError("Vault maintenance is pending")
                return self._publish_locked(
                    user_id, application_id, data, application_service_helper
                )
            except Exception:
                self.db.rollback()
                self.db.execute(text("BEGIN IMMEDIATE"))
                try:
                    reconcile_packet_journals(self.db)
                finally:
                    self.db.rollback()
                raise

    def _publish_locked(
        self,
        user_id: int,
        application_id: str,
        data: ApplicationDossierCreate,
        application_service_helper: ApplicationService,
    ) -> ApplicationResponse:
        """Publish an Enhanced 3.0 dossier packet atomically with durable artifact storage."""
        application = self._application(user_id, application_id)
        if application.revision != data.expected_revision:
            raise ApplicationConflictError(
                f"Expected revision {data.expected_revision}, current revision is {application.revision}"
            )

        draft = (
            self.db.query(ApplicationDossierDraft)
            .filter(ApplicationDossierDraft.application_id == application.id)
            .one_or_none()
        )
        if draft is None and data.expected_draft_revision is not None:
            raise ApplicationConflictError("The dossier draft no longer exists")

        effective_version_id: str | None = None
        if draft is not None:
            if (
                data.expected_draft_revision is None
                or draft.revision != data.expected_draft_revision
            ):
                raise ApplicationConflictError(
                    "The dossier draft changed in another editor; reload before publishing"
                )
            if draft.application_revision != application.revision:
                raise ApplicationConflictError(
                    "Save the dossier draft against the current application before publishing"
                )

            # Binding checks
            if draft.resume_draft_id is not None:
                # Draft bound to unpublished resume draft
                target_version_id = str(data.resume_version_id) if data.resume_version_id else None
                if not target_version_id:
                    raise ApplicationValidationError(
                        "Publishing an unpublished-draft-bound packet requires an explicit verified version of the same draft"
                    )
                version = self._resume_version(user_id, target_version_id)
                if version is None:
                    raise ApplicationValidationError("The linked resume version is unavailable")
                if version.draft_id != draft.resume_draft_id:
                    raise ApplicationValidationError(
                        "The specified resume version was not published from the bound resume draft"
                    )
                current_rdraft = self._resume_draft(user_id, draft.resume_draft_id)
                current_profile = (
                    self.db.query(CandidateProfile)
                    .filter(CandidateProfile.user_id == user_id)
                    .one()
                )
                published_revision = (
                    (version.snapshot or {}).get("resume", {}).get("draft_revision")
                )
                if (
                    current_rdraft is None
                    or published_revision != draft.resume_draft_revision
                    or current_rdraft.revision != draft.resume_draft_revision
                    or current_rdraft.profile_revision != current_profile.revision
                    or version.profile_revision != current_profile.revision
                ):
                    raise ApplicationConflictError(
                        "Publish the current approved resume draft before publishing its packet"
                    )
                effective_version_id = version.id
            else:
                # Draft bound to resume_version_id
                if (
                    data.resume_version_id is not None
                    and str(data.resume_version_id) != draft.resume_version_id
                ):
                    raise ApplicationConflictError(
                        "The selected resume differs from the saved dossier binding"
                    )
                if draft.resume_version_id != application.resume_version_id:
                    raise ApplicationConflictError(
                        "Save the dossier draft against the current application before publishing"
                    )
                effective_version_id = draft.resume_version_id

            # Content equality check
            publishable_saved = _publishable_draft_content(draft.content)
            publishable_req = _requested_dossier_content(data)
            # Compare core components
            for key in publishable_saved:
                if publishable_saved[key] != publishable_req[key]:
                    raise ApplicationConflictError(
                        "The published dossier does not match the saved draft"
                    )
        else:
            effective_version_id = (
                str(data.resume_version_id)
                if data.resume_version_id
                else application.resume_version_id
            )

        if not effective_version_id:
            raise ApplicationValidationError("Link a published resume before creating a dossier")

        version = self._resume_version(user_id, effective_version_id)
        if version is None:
            raise ApplicationValidationError("Link a published resume before creating a dossier")
        if not bool((version.quality_report or {}).get("passed")):
            raise ApplicationValidationError("The linked resume did not pass its quality checks")

        original_version_id = application.resume_version_id
        with self.db.no_autoflush:
            application.resume_version_id = effective_version_id
            readiness = ApplicationReadinessService(self.db).build(user_id, application)
            application.resume_version_id = original_version_id
        if readiness.blocker_count:
            raise ApplicationValidationError(
                "Resolve the application readiness blockers before publishing a dossier"
            )

        dossier_id, now, bundle, event_payload = build_packet_materials(
            self,
            application=application,
            data=data,
            version=version,
            readiness=readiness,
            application_service_helper=application_service_helper,
        )
        # Store ZIP bytes atomically with journal
        stored_artifact = store_packet_artifact(
            application_id=application.id,
            dossier_id=dossier_id,
            data=bundle.data,
        )

        try:
            # Delete consumed draft with CAS
            if draft is not None:
                consumed = self.db.execute(
                    delete(ApplicationDossierDraft)
                    .where(
                        ApplicationDossierDraft.id == draft.id,
                        ApplicationDossierDraft.revision == draft.revision,
                        ApplicationDossierDraft.application_revision == draft.application_revision,
                    )
                    .execution_options(synchronize_session=False)
                )
                if getattr(consumed, "rowcount", 0) != 1:
                    raise ApplicationConflictError(
                        "The dossier draft changed in another editor; reload before publishing"
                    )

            # Persist ApplicationPacketArtifact
            packet_row = ApplicationPacketArtifact(
                id=str(uuid.uuid4()),
                application_id=application.id,
                dossier_id=dossier_id,
                storage_path=stored_artifact.relative_path,
                sha256=stored_artifact.sha256,
                byte_size=stored_artifact.byte_size,
                media_type="application/zip",
                created_at=now,
            )
            self.db.add(packet_row)

            # Update application resume_version_id and advance revision
            application.resume_version_id = version.id
            application_service_helper._advance_revision(application, data.expected_revision, now)

            self.db.add(
                ApplicationEvent(
                    id=dossier_id,
                    application_id=application.id,
                    event_type="dossier_published",
                    stage=None,
                    occurred_at=now,
                    note=None,
                    payload=event_payload,
                    created_at=now,
                )
            )

            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
                self.db.execute(text("BEGIN IMMEDIATE"))
                committed = (
                    self.db.query(ApplicationPacketArtifact)
                    .filter(
                        ApplicationPacketArtifact.application_id == application_id,
                        ApplicationPacketArtifact.dossier_id == dossier_id,
                    )
                    .one_or_none()
                )
                event = (
                    self.db.query(ApplicationEvent)
                    .filter(ApplicationEvent.id == dossier_id)
                    .one_or_none()
                )
                if committed is None or event is None:
                    raise
                # A lost acknowledgement must never remove a committed artifact.
                read_verified_packet_artifact(
                    committed.storage_path,
                    expected_sha256=committed.sha256,
                    expected_size=committed.byte_size,
                )
                self.db.rollback()
        except Exception:
            self.db.rollback()
            raise
        try:
            remove_packet_journal(dossier_id)
        except (OSError, ValueError, StorageWriteError):
            # Durable bytes and DB state are already committed. Next recovery retries cleanup.
            logger.warning("Packet committed; recovery journal cleanup deferred")

        self.db.expire_all()
        return application_service_helper._response(
            application_service_helper._application(user_id, application_id)
        )
