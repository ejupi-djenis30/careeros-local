from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from backend.career.models import CandidateProfile, CareerAsset, CareerFact, CareerGoal
from backend.career.repository import CareerProfileRepository
from backend.models.job import Job
from backend.resumes.canvas import normalize_canvas
from backend.resumes.draft_mutations import apply_draft_data
from backend.resumes.exceptions import (
    ResumeConflictError,
    ResumeNotFoundError,
    ResumeValidationError,
)
from backend.resumes.generator import generate_resume
from backend.resumes.models import ResumeDraft, ResumeVersion
from backend.resumes.schemas import (
    ResumeDraftCreate,
    ResumeDraftResponse,
    ResumeDraftUpdate,
    ResumeDuplicate,
    ResumeGenerate,
    ResumeSummary,
    ResumeVersionLinkOption,
)
from backend.resumes.storage import remove_stored_artifact


class ResumeDraftService:
    def __init__(self, db: Session):
        self.db = db

    def profile(self, user_id: int) -> CandidateProfile:
        profile = CareerProfileRepository(self.db).get_by_user(user_id)
        if profile is None:
            raise ResumeValidationError("Create the career profile before creating a resume")
        return profile

    def draft(self, user_id: int, draft_id: str) -> ResumeDraft:
        draft = (
            self.db.query(ResumeDraft)
            .join(CandidateProfile, ResumeDraft.profile_id == CandidateProfile.id)
            .filter(ResumeDraft.id == draft_id, CandidateProfile.user_id == user_id)
            .first()
        )
        if draft is None:
            raise ResumeNotFoundError("Resume draft not found")
        return draft

    def validate_selection(self, profile: CandidateProfile, data: Any) -> list[CareerFact]:
        if data.template_kind == "photo" and not data.photo_asset_id:
            raise ResumeValidationError("Photo resumes require a normalized profile photo")
        facts = (
            self.db.query(CareerFact)
            .filter(
                CareerFact.profile_id == profile.id,
                CareerFact.id.in_(data.selected_fact_ids),
                CareerFact.archived_at.is_(None),
            )
            .all()
        )
        by_id = {fact.id: fact for fact in facts}
        missing = [fact_id for fact_id in data.selected_fact_ids if fact_id not in by_id]
        if missing:
            raise ResumeValidationError(
                "Resume references missing career facts: " + ", ".join(missing)
            )
        unsafe = [
            fact.id
            for fact in facts
            if fact.verification_status != "confirmed" or fact.fact_type == "reference"
        ]
        if unsafe:
            raise ResumeValidationError(
                "Resumes can use only confirmed, non-private career facts: "
                + ", ".join(sorted(unsafe))
            )
        if data.photo_asset_id:
            self.photo(profile, data.photo_asset_id)
        return [by_id[fact_id] for fact_id in data.selected_fact_ids]

    def photo(self, profile: CandidateProfile, asset_id: str) -> CareerAsset:
        asset = (
            self.db.query(CareerAsset)
            .filter(
                CareerAsset.id == asset_id,
                CareerAsset.profile_id == profile.id,
                CareerAsset.kind == "profile_photo",
                CareerAsset.normalized.is_(True),
            )
            .first()
        )
        if asset is None:
            raise ResumeValidationError("Photo asset is missing or does not belong to this profile")
        return asset

    def ordered_facts(self, profile: CandidateProfile, ids: list[str]) -> list[CareerFact]:
        facts = (
            self.db.query(CareerFact)
            .filter(CareerFact.profile_id == profile.id, CareerFact.id.in_(ids))
            .all()
        )
        by_id = {fact.id: fact for fact in facts}
        return [by_id[fact_id] for fact_id in ids if fact_id in by_id]

    def response(self, profile: CandidateProfile, draft: ResumeDraft) -> ResumeDraftResponse:
        facts = self.ordered_facts(profile, list(draft.selected_fact_ids))
        canvas = normalize_canvas(
            draft.canvas_document,
            profile=profile,
            facts=facts,
            template_kind=draft.template_kind,
            section_config=draft.section_config,
            content_overrides=draft.content_overrides,
        )
        return ResumeDraftResponse.model_validate(
            {
                "id": draft.id,
                "profile_id": draft.profile_id,
                "revision": draft.revision,
                "profile_revision": draft.profile_revision,
                "title": draft.title,
                "template_kind": draft.template_kind,
                "section_config": draft.section_config,
                "selected_fact_ids": draft.selected_fact_ids,
                "content_overrides": draft.content_overrides,
                "photo_asset_id": draft.photo_asset_id,
                "canvas_document": canvas,
                "generation_context": draft.generation_context or None,
                "versions": draft.versions,
                "created_at": draft.created_at,
                "updated_at": draft.updated_at,
            }
        )

    def create(self, user_id: int, data: ResumeDraftCreate) -> ResumeDraftResponse:
        profile = self.profile(user_id)
        facts = self.validate_selection(profile, data)
        draft = ResumeDraft(
            profile_id=profile.id,
            revision=1,
            profile_revision=profile.revision,
            generation_context={},
        )
        apply_draft_data(draft, data, facts, profile)
        self.db.add(draft)
        self.db.commit()
        self.db.refresh(draft)
        return self.response(profile, draft)

    def update(self, user_id: int, draft_id: str, data: ResumeDraftUpdate) -> ResumeDraftResponse:
        draft = self.draft(user_id, draft_id)
        if draft.revision != data.expected_revision:
            raise ResumeConflictError(
                f"Expected revision {data.expected_revision}, current revision is {draft.revision}"
            )
        profile = self.profile(user_id)
        facts = self.validate_selection(profile, data)
        apply_draft_data(draft, data, facts, profile)
        draft.revision += 1
        self.db.commit()
        self.db.expire_all()
        return self.response(profile, self.draft(user_id, draft_id))

    def get(self, user_id: int, draft_id: str) -> ResumeDraftResponse:
        profile = self.profile(user_id)
        return self.response(profile, self.draft(user_id, draft_id))

    def list_resumes(self, user_id: int) -> list[ResumeSummary]:
        profile = CareerProfileRepository(self.db).get_by_user(user_id)
        if profile is None:
            return []
        drafts = (
            self.db.query(ResumeDraft)
            .filter(ResumeDraft.profile_id == profile.id)
            .order_by(ResumeDraft.updated_at.desc())
            .all()
        )
        return [
            ResumeSummary(
                id=draft.id,
                revision=draft.revision,
                title=draft.title,
                template_kind=draft.template_kind,
                selected_fact_count=len(draft.selected_fact_ids),
                latest_version=draft.versions[0].semantic_version if draft.versions else None,
                updated_at=draft.updated_at,
            )
            for draft in drafts
        ]

    def list_versions(self, user_id: int) -> list[ResumeVersionLinkOption]:
        profile = CareerProfileRepository(self.db).get_by_user(user_id)
        if profile is None:
            return []
        versions = (
            self.db.query(ResumeVersion)
            .join(ResumeDraft, ResumeVersion.draft_id == ResumeDraft.id)
            .filter(ResumeDraft.profile_id == profile.id)
            .order_by(ResumeVersion.published_at.desc())
            .all()
        )
        return [
            ResumeVersionLinkOption(
                id=version.id,
                draft_id=version.draft_id,
                draft_title=version.draft.title,
                semantic_version=version.semantic_version,
                name=version.name,
                published_at=version.published_at,
            )
            for version in versions
        ]

    def generate(self, user_id: int, data: ResumeGenerate) -> ResumeDraftResponse:
        profile = self.profile(user_id)
        goal = None
        if data.career_goal_id:
            goal = (
                self.db.query(CareerGoal)
                .filter(
                    CareerGoal.id == data.career_goal_id,
                    CareerGoal.profile_id == profile.id,
                )
                .first()
            )
            if goal is None:
                raise ResumeValidationError("The selected career goal does not belong to this profile")
        target_snapshot: dict[str, Any] = {}
        if data.target_job_id:
            job = self.db.query(Job).filter(
                Job.id == data.target_job_id, Job.user_id == user_id
            ).first()
            if job is None:
                raise ResumeValidationError("The selected target job does not belong to this user")
            target_snapshot = {
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "required_skills": (job.normalized_job or {}).get("required_skills", []),
            }
        result = generate_resume(
            profile,
            profile.facts,
            template_kind=data.template_kind,
            goal=goal,
            target_job_id=data.target_job_id,
            target_snapshot=target_snapshot,
        )
        create_data = ResumeDraftCreate(
            title=data.title,
            template_kind=data.template_kind,
            section_config=result.section_config,
            selected_fact_ids=result.selected_fact_ids,
            canvas_document=result.canvas,
            photo_asset_id=data.photo_asset_id,
        )
        facts = self.validate_selection(profile, create_data)
        draft = ResumeDraft(
            profile_id=profile.id,
            revision=1,
            profile_revision=profile.revision,
            generation_context=result.generation_context.model_dump(mode="json", exclude_none=True),
        )
        apply_draft_data(draft, create_data, facts, profile)
        self.db.add(draft)
        self.db.commit()
        self.db.refresh(draft)
        return self.response(profile, draft)

    def duplicate(
        self, user_id: int, draft_id: str, data: ResumeDuplicate
    ) -> ResumeDraftResponse:
        profile = self.profile(user_id)
        source = self.draft(user_id, draft_id)
        duplicate = ResumeDraft(
            profile_id=source.profile_id,
            revision=1,
            profile_revision=source.profile_revision,
            title=data.title or f"{source.title} · copia",
            template_kind=source.template_kind,
            section_config=deepcopy(source.section_config),
            selected_fact_ids=list(source.selected_fact_ids),
            content_overrides=deepcopy(source.content_overrides),
            canvas_document=deepcopy(source.canvas_document),
            generation_context=deepcopy(source.generation_context),
            photo_asset_id=source.photo_asset_id,
        )
        self.db.add(duplicate)
        self.db.commit()
        self.db.refresh(duplicate)
        return self.response(profile, duplicate)

    def delete(self, user_id: int, draft_id: str) -> None:
        draft = self.draft(user_id, draft_id)
        paths = [
            artifact.storage_path for version in draft.versions for artifact in version.artifacts
        ]
        self.db.delete(draft)
        self.db.commit()
        for path in paths:
            remove_stored_artifact(path)
