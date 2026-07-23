from __future__ import annotations

import re

from sqlalchemy.orm import Session

from backend.career.models import CandidateProfile
from backend.resumes.canvas import normalize_canvas
from backend.resumes.canvas_validation import validate_publishable_canvas
from backend.resumes.draft_service import ResumeDraftService
from backend.resumes.exceptions import ResumeNotFoundError, ResumeValidationError
from backend.resumes.models import ResumeArtifact, ResumeDraft, ResumeVersion
from backend.resumes.publishing import publish_draft
from backend.resumes.schemas import (
    ResumeDraftCreate,
    ResumeDraftResponse,
    ResumeDraftUpdate,
    ResumeVersionComparison,
    ResumeVersionResponse,
)
from backend.storage.atomic import read_verified


class ResumePublicationService:
    def __init__(self, db: Session, drafts: ResumeDraftService):
        self.db = db
        self.drafts = drafts

    def publish(
        self, user_id: int, draft_id: str, version_name: str | None = None
    ) -> ResumeVersionResponse:
        draft = self.drafts.draft(user_id, draft_id)
        profile = self.drafts.profile(user_id)
        data = ResumeDraftCreate.model_validate(
            {
                "title": draft.title,
                "template_kind": draft.template_kind,
                "section_config": draft.section_config,
                "selected_fact_ids": draft.selected_fact_ids,
                "content_overrides": draft.content_overrides,
                "photo_asset_id": draft.photo_asset_id,
                "canvas_document": draft.canvas_document or None,
            }
        )
        facts = self.drafts.validate_selection(profile, data)
        canvas = normalize_canvas(
            data.canvas_document,
            profile=profile,
            facts=facts,
            template_kind=draft.template_kind,
            section_config=draft.section_config,
            content_overrides=draft.content_overrides,
        )
        try:
            validate_publishable_canvas(canvas, {fact.id for fact in facts})
        except ValueError as exc:
            raise ResumeValidationError(str(exc)) from exc
        draft.canvas_document = canvas.model_dump(mode="json")
        photo = self.drafts.photo(profile, draft.photo_asset_id) if draft.photo_asset_id else None
        photo_bytes = None
        if photo:
            try:
                photo_bytes = read_verified(photo.storage_path, photo.sha256)
            except (OSError, ValueError) as exc:
                raise ResumeValidationError(
                    "The normalized photo failed its integrity check"
                ) from exc
        version = publish_draft(
            self.db,
            profile=profile,
            draft=draft,
            facts=facts,
            photo=photo,
            photo_bytes=photo_bytes,
            version_name=version_name,
        )
        return ResumeVersionResponse.model_validate(version)

    def _version(self, user_id: int, version_id: str) -> ResumeVersion:
        version = (
            self.db.query(ResumeVersion)
            .join(ResumeDraft, ResumeVersion.draft_id == ResumeDraft.id)
            .join(CandidateProfile, ResumeDraft.profile_id == CandidateProfile.id)
            .filter(ResumeVersion.id == version_id, CandidateProfile.user_id == user_id)
            .first()
        )
        if version is None:
            raise ResumeNotFoundError("Resume version not found")
        return version

    @staticmethod
    def _changed_keys(left: dict, right: dict) -> list[str]:
        return sorted(
            key for key in set(left) | set(right) if left.get(key) != right.get(key)
        )

    def compare(
        self, user_id: int, left_version_id: str, right_version_id: str
    ) -> ResumeVersionComparison:
        left = self._version(user_id, left_version_id)
        right = self._version(user_id, right_version_id)
        if left.draft_id != right.draft_id:
            raise ResumeValidationError("Only versions of the same resume can be compared")
        left_facts = {item["id"]: item for item in left.snapshot.get("facts", [])}
        right_facts = {item["id"]: item for item in right.snapshot.get("facts", [])}
        shared = set(left_facts) & set(right_facts)
        return ResumeVersionComparison(
            left_version_id=left.id,
            right_version_id=right.id,
            left_name=left.name,
            right_name=right.name,
            profile_changes=self._changed_keys(
                left.snapshot.get("profile", {}), right.snapshot.get("profile", {})
            ),
            resume_changes=self._changed_keys(
                left.snapshot.get("resume", {}), right.snapshot.get("resume", {})
            ),
            added_fact_ids=sorted(set(right_facts) - set(left_facts)),
            removed_fact_ids=sorted(set(left_facts) - set(right_facts)),
            changed_fact_ids=sorted(
                fact_id
                for fact_id in shared
                if left_facts[fact_id] != right_facts[fact_id]
            ),
        )

    def restore(
        self,
        user_id: int,
        draft_id: str,
        version_id: str,
        expected_revision: int,
    ) -> ResumeDraftResponse:
        current = self.drafts.draft(user_id, draft_id)
        version = self._version(user_id, version_id)
        if version.draft_id != current.id:
            raise ResumeValidationError("Resume version does not belong to this draft")
        snapshot = version.snapshot
        resume = snapshot.get("resume", {})
        photo = snapshot.get("photo") or {}
        data = ResumeDraftUpdate.model_validate(
            {
                "expected_revision": expected_revision,
                "title": resume.get("title", current.title),
                "template_kind": resume.get("template_kind", version.template_kind),
                "section_config": resume.get("section_config", {}),
                "selected_fact_ids": snapshot.get("selected_fact_ids", []),
                "content_overrides": resume.get("content_overrides", {}),
                "canvas_document": resume.get("canvas_document"),
                "photo_asset_id": photo.get("asset_id"),
            }
        )
        restored = self.drafts.update(user_id, draft_id, data)
        persisted = self.drafts.draft(user_id, draft_id)
        persisted.generation_context = resume.get("generation_context", {})
        self.db.commit()
        return self.drafts.get(user_id, restored.id)

    def artifact(self, user_id: int, artifact_id: str) -> tuple[ResumeArtifact, bytes, str]:
        result = (
            self.db.query(ResumeArtifact, ResumeDraft.title)
            .join(ResumeVersion, ResumeArtifact.version_id == ResumeVersion.id)
            .join(ResumeDraft, ResumeVersion.draft_id == ResumeDraft.id)
            .join(CandidateProfile, ResumeDraft.profile_id == CandidateProfile.id)
            .filter(ResumeArtifact.id == artifact_id, CandidateProfile.user_id == user_id)
            .first()
        )
        if result is None:
            raise ResumeNotFoundError("Resume artifact not found")
        artifact, title = result
        try:
            data = read_verified(artifact.storage_path, artifact.sha256)
        except (OSError, ValueError) as exc:
            raise ResumeValidationError("Resume artifact failed its integrity check") from exc
        safe_title = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-") or "resume"
        return artifact, data, f"{safe_title}.{artifact.format}"
