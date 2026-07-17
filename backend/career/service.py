from collections import Counter

from sqlalchemy.orm import Session

from backend.career.completeness import analyze_profile
from backend.career.models import CandidateProfile
from backend.career.repository import CareerProfileRepository
from backend.career.schemas import (
    CareerProfileResponse,
    CareerProfileSummary,
    CareerProfileWrite,
)
from backend.resumes.models import ResumeDraft, ResumeVersion
from backend.storage.atomic import StorageWriteError, is_storage_exhaustion


class CareerProfileService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = CareerProfileRepository(db)

    def get(self, user_id: int) -> CareerProfileResponse | None:
        profile = self.repository.get_by_user(user_id)
        return self._response(profile) if profile else None

    def save(self, user_id: int, data: CareerProfileWrite) -> CareerProfileResponse:
        try:
            self._validate_resume_version_links(user_id, data)
            profile = self.repository.save(user_id, data)
            return self._response(profile)
        except Exception as exc:
            self.db.rollback()
            if is_storage_exhaustion(exc) and not isinstance(exc, StorageWriteError):
                raise StorageWriteError(
                    "Career Vault could not be saved because local storage is full."
                ) from exc
            raise

    def _validate_resume_version_links(
        self, user_id: int, data: CareerProfileWrite
    ) -> None:
        requested = {
            version_id
            for goal in data.goals
            for action in goal.payload.get("actions", [])
            for version_id in action.get("linked_resume_version_ids", [])
        }
        if not requested:
            return
        owned = {
            item[0]
            for item in (
                self.db.query(ResumeVersion.id)
                .join(ResumeDraft, ResumeVersion.draft_id == ResumeDraft.id)
                .join(CandidateProfile, ResumeDraft.profile_id == CandidateProfile.id)
                .filter(
                    CandidateProfile.user_id == user_id,
                    ResumeVersion.id.in_(requested),
                )
                .all()
            )
        }
        if requested - owned:
            raise ValueError("resume version links must belong to the same career profile")

    @staticmethod
    def _response(profile) -> CareerProfileResponse:
        response = CareerProfileResponse.model_validate(profile)
        return response.model_copy(update={"analysis": analyze_profile(response)})

    def summary(self, user_id: int) -> CareerProfileSummary | None:
        profile = self.repository.get_by_user(user_id)
        if profile is None:
            return None
        counts = Counter(item.fact_type for item in profile.facts)
        analysis = analyze_profile(profile)
        return CareerProfileSummary(
            id=profile.id,
            revision=profile.revision,
            display_name=profile.display_name,
            headline=profile.headline,
            fact_counts=dict(sorted(counts.items())),
            goal_count=len(profile.goals),
            completeness_score=analysis.completeness_score,
            issue_count=len(analysis.issues),
            updated_at=profile.updated_at,
        )
