from sqlalchemy.orm import Session

from backend.resumes.claim_service import ResumeClaimService
from backend.resumes.draft_service import ResumeDraftService
from backend.resumes.exceptions import (
    ResumeConflictError,
    ResumeNotFoundError,
    ResumeValidationError,
)
from backend.resumes.models import ResumeArtifact
from backend.resumes.publication_service import ResumePublicationService
from backend.resumes.schemas import (
    ResumeClaimPromote,
    ResumeDraftCreate,
    ResumeDraftResponse,
    ResumeDraftUpdate,
    ResumeDuplicate,
    ResumeGenerate,
    ResumeSummary,
    ResumeSync,
    ResumeSyncResponse,
    ResumeVersionResponse,
)
from backend.resumes.sync_service import ResumeSynchronizationService

__all__ = [
    "ResumeConflictError",
    "ResumeNotFoundError",
    "ResumeService",
    "ResumeValidationError",
]


class ResumeService:
    """Small use-case facade for the resume bounded context."""

    def __init__(self, db: Session):
        self.drafts = ResumeDraftService(db)
        self.claims = ResumeClaimService(db, self.drafts)
        self.publication = ResumePublicationService(db, self.drafts)
        self.synchronization = ResumeSynchronizationService(db, self.drafts)

    def create(self, user_id: int, data: ResumeDraftCreate) -> ResumeDraftResponse:
        return self.drafts.create(user_id, data)

    def update(self, user_id: int, draft_id: str, data: ResumeDraftUpdate) -> ResumeDraftResponse:
        return self.drafts.update(user_id, draft_id, data)

    def get(self, user_id: int, draft_id: str) -> ResumeDraftResponse:
        return self.drafts.get(user_id, draft_id)

    def list_resumes(self, user_id: int) -> list[ResumeSummary]:
        return self.drafts.list_resumes(user_id)

    def generate(self, user_id: int, data: ResumeGenerate) -> ResumeDraftResponse:
        return self.drafts.generate(user_id, data)

    def duplicate(
        self, user_id: int, draft_id: str, data: ResumeDuplicate
    ) -> ResumeDraftResponse:
        return self.drafts.duplicate(user_id, draft_id, data)

    def promote_claim(
        self, user_id: int, draft_id: str, data: ResumeClaimPromote
    ) -> ResumeDraftResponse:
        return self.claims.promote(user_id, draft_id, data)

    def synchronize(
        self, user_id: int, draft_id: str, data: ResumeSync
    ) -> ResumeSyncResponse:
        return self.synchronization.synchronize(user_id, draft_id, data)

    def publish(self, user_id: int, draft_id: str) -> ResumeVersionResponse:
        return self.publication.publish(user_id, draft_id)

    def artifact(self, user_id: int, artifact_id: str) -> tuple[ResumeArtifact, bytes, str]:
        return self.publication.artifact(user_id, artifact_id)

    def delete(self, user_id: int, draft_id: str) -> None:
        self.drafts.delete(user_id, draft_id)
