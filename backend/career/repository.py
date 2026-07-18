import uuid

from sqlalchemy.orm import Session

from backend.career.models import CandidateProfile, CareerFact, CareerGoal, SourceDocument
from backend.career.schemas import CareerProfileWrite
from backend.storage.atomic import StorageWriteError, is_storage_exhaustion


class CareerProfileConflictError(RuntimeError):
    pass


class CareerProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_user(self, user_id: int) -> CandidateProfile | None:
        return self.db.query(CandidateProfile).filter(CandidateProfile.user_id == user_id).first()

    def save(self, user_id: int, data: CareerProfileWrite) -> CandidateProfile:
        profile = self.get_by_user(user_id)
        if profile is None:
            if data.expected_revision != 0:
                raise CareerProfileConflictError("Profile does not exist at that revision")
            profile = CandidateProfile(user_id=user_id, revision=0, display_name=data.display_name)
            self.db.add(profile)
            self.db.flush()
        elif profile.revision != data.expected_revision:
            raise CareerProfileConflictError(
                f"Expected revision {data.expected_revision}, current revision is {profile.revision}"
            )

        for field in (
            "display_name",
            "headline",
            "summary",
            "email",
            "phone",
            "location",
            "birth_date",
            "nationality",
            "work_authorization",
            "website",
            "linkedin",
            "github",
            "preferences",
        ):
            setattr(profile, field, getattr(data, field))

        existing_facts = {item.id: item for item in profile.facts}
        retained_fact_ids: set[str] = set()
        for fact_input in data.facts:
            fact_id = fact_input.id or str(uuid.uuid4())
            fact = existing_facts.get(fact_id)
            if fact_input.id and fact is None:
                owner = (
                    self.db.query(CareerFact.profile_id)
                    .filter(CareerFact.id == fact_id)
                    .scalar()
                )
                if owner is not None:
                    raise ValueError(f"Career fact '{fact_id}' does not belong to this profile")
            if fact_input.source_document_id:
                source_exists = (
                    self.db.query(SourceDocument.id)
                    .filter(
                        SourceDocument.id == fact_input.source_document_id,
                        SourceDocument.profile_id == profile.id,
                    )
                    .first()
                )
                if source_exists is None:
                    raise ValueError("source_document_id does not belong to this profile")
            if fact is None:
                fact = CareerFact(id=fact_id, profile_id=profile.id)
                self.db.add(fact)
            fact.fact_type = fact_input.fact_type
            fact.position = fact_input.position
            fact.payload = fact_input.payload
            fact.source_document_id = fact_input.source_document_id
            fact.source_locator = fact_input.source_locator
            fact.confidence = fact_input.confidence
            fact.verification_status = fact_input.verification_status
            retained_fact_ids.add(fact_id)
        for fact_id, fact in existing_facts.items():
            if fact_id not in retained_fact_ids:
                self.db.delete(fact)

        existing_goals = {item.id: item for item in profile.goals}
        retained_goal_ids: set[str] = set()
        for goal_input in data.goals:
            goal_id = goal_input.id or str(uuid.uuid4())
            goal = existing_goals.get(goal_id)
            if goal_input.id and goal is None:
                owner = (
                    self.db.query(CareerGoal.profile_id)
                    .filter(CareerGoal.id == goal_id)
                    .scalar()
                )
                if owner is not None:
                    raise ValueError(f"Career goal '{goal_id}' does not belong to this profile")
            if goal is None:
                goal = CareerGoal(id=goal_id, profile_id=profile.id)
                self.db.add(goal)
            goal.name = goal_input.name
            goal.is_primary = goal_input.is_primary
            goal.payload = goal_input.payload
            retained_goal_ids.add(goal_id)
        for goal_id, goal in existing_goals.items():
            if goal_id not in retained_goal_ids:
                self.db.delete(goal)

        profile.revision += 1
        try:
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            if is_storage_exhaustion(exc):
                raise StorageWriteError(
                    "Career Vault could not be saved because local storage is full."
                ) from exc
            raise
        self.db.expire_all()
        result = self.get_by_user(user_id)
        if result is None:
            raise RuntimeError("Profile disappeared after commit")
        return result
