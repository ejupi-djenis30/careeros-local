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
from backend.resumes.schemas import ResumeDraftCreate, ResumeVersionResponse
from backend.storage.atomic import read_verified


class ResumePublicationService:
    def __init__(self, db: Session, drafts: ResumeDraftService):
        self.db = db
        self.drafts = drafts

    def publish(self, user_id: int, draft_id: str) -> ResumeVersionResponse:
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
        )
        return ResumeVersionResponse.model_validate(version)

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
