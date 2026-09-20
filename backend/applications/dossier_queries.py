"""Orchestration service for application dossiers, draft bindings, and enhanced packets."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.applications.exceptions import (
    ApplicationNotFoundError,
    ApplicationValidationError,
)
from backend.applications.exports import (
    MAX_DOSSIER_ARTIFACT_BYTES,
)
from backend.applications.models import (
    Application,
)
from backend.career.models import CandidateProfile
from backend.resumes.artifact_policy import read_verified_resume_artifact
from backend.resumes.models import ResumeDraft, ResumeVersion


class DossierQueryService:
    def __init__(self, db: Session):
        self.db = db

    def _application(self, user_id: int, application_id: str) -> Application:
        app = (
            self.db.query(Application)
            .filter(Application.id == application_id, Application.user_id == user_id)
            .populate_existing()
            .first()
        )
        if app is None:
            raise ApplicationNotFoundError("Application not found")
        return app

    def _resume_version(self, user_id: int, version_id: str | None) -> ResumeVersion | None:
        if not version_id:
            return None
        return (
            self.db.query(ResumeVersion)
            .join(ResumeDraft)
            .join(CandidateProfile, ResumeDraft.profile_id == CandidateProfile.id)
            .filter(ResumeVersion.id == version_id, CandidateProfile.user_id == user_id)
            .first()
        )

    def _resume_draft(self, user_id: int, draft_id: str | None) -> ResumeDraft | None:
        if not draft_id:
            return None
        return (
            self.db.query(ResumeDraft)
            .join(CandidateProfile, ResumeDraft.profile_id == CandidateProfile.id)
            .filter(ResumeDraft.id == draft_id, CandidateProfile.user_id == user_id)
            .first()
        )

    def _verified_resume_artifacts(self, version: ResumeVersion) -> dict[str, tuple[bytes, str]]:
        artifacts: dict[str, tuple[bytes, str]] = {}
        for artifact in version.artifacts:
            if artifact.format not in {"pdf", "docx"}:
                continue
            if (
                isinstance(artifact.byte_size, bool)
                or not isinstance(artifact.byte_size, int)
                or artifact.byte_size <= 0
                or artifact.byte_size > MAX_DOSSIER_ARTIFACT_BYTES
            ):
                raise ApplicationValidationError(
                    f"The stored {artifact.format.upper()} resume artifact exceeds the dossier limit"
                )
            try:
                data = read_verified_resume_artifact(
                    artifact.storage_path,
                    expected_sha256=artifact.sha256,
                    expected_size=artifact.byte_size,
                )
            except (OSError, ValueError) as exc:
                raise ApplicationValidationError(
                    f"The stored {artifact.format.upper()} resume artifact failed verification"
                ) from exc
            artifacts[artifact.format] = (data, artifact.media_type)
        if not artifacts:
            raise ApplicationValidationError("The linked resume has no verified export artifact")
        return artifacts
