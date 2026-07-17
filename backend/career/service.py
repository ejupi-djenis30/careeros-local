from collections import Counter

from sqlalchemy.orm import Session

from backend.career.repository import CareerProfileRepository
from backend.career.schemas import (
    CareerProfileResponse,
    CareerProfileSummary,
    CareerProfileWrite,
)


class CareerProfileService:
    def __init__(self, db: Session):
        self.repository = CareerProfileRepository(db)

    def get(self, user_id: int) -> CareerProfileResponse | None:
        profile = self.repository.get_by_user(user_id)
        return CareerProfileResponse.model_validate(profile) if profile else None

    def save(self, user_id: int, data: CareerProfileWrite) -> CareerProfileResponse:
        profile = self.repository.save(user_id, data)
        return CareerProfileResponse.model_validate(profile)

    def summary(self, user_id: int) -> CareerProfileSummary | None:
        profile = self.repository.get_by_user(user_id)
        if profile is None:
            return None
        counts = Counter(item.fact_type for item in profile.facts)
        return CareerProfileSummary(
            id=profile.id,
            revision=profile.revision,
            display_name=profile.display_name,
            headline=profile.headline,
            fact_counts=dict(sorted(counts.items())),
            goal_count=len(profile.goals),
            updated_at=profile.updated_at,
        )
