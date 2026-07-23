from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.career.models import CareerFact
from backend.career.schemas import CareerFactInput
from backend.resumes.canvas import legacy_fields, normalize_canvas
from backend.resumes.draft_service import ResumeDraftService
from backend.resumes.exceptions import ResumeConflictError, ResumeValidationError
from backend.resumes.schemas import ResumeClaimPromote, ResumeDraftResponse


class ResumeClaimService:
    def __init__(self, db: Session, drafts: ResumeDraftService):
        self.db = db
        self.drafts = drafts

    def promote(
        self,
        user_id: int,
        draft_id: str,
        data: ResumeClaimPromote,
    ) -> ResumeDraftResponse:
        draft = self.drafts.draft(user_id, draft_id)
        profile = self.drafts.profile(user_id)
        if draft.revision != data.expected_revision:
            raise ResumeConflictError(
                f"Expected revision {data.expected_revision}, current revision is {draft.revision}"
            )
        if profile.revision != data.expected_profile_revision:
            raise ResumeConflictError(
                "Expected profile revision "
                f"{data.expected_profile_revision}, current revision is {profile.revision}"
            )
        if len(draft.selected_fact_ids) >= 300:
            raise ResumeValidationError("The resume already contains the maximum number of facts")

        facts = self.drafts.ordered_facts(profile, list(draft.selected_fact_ids))
        canvas = normalize_canvas(
            draft.canvas_document,
            profile=profile,
            facts=facts,
            template_kind=draft.template_kind,
            section_config=draft.section_config,
            content_overrides=draft.content_overrides,
        )
        selected_section = None
        selected_block = None
        for section in canvas.sections:
            for block in section.blocks:
                if block.id == data.block_id:
                    selected_section, selected_block = section, block
                    break
            if selected_block:
                break
        if selected_block is None or selected_section is None:
            raise ResumeValidationError("Manual claim block not found")
        if selected_section.kind != "achievement" or selected_block.kind != "fact":
            raise ResumeValidationError("Only manual achievement claims can be promoted")
        if selected_block.fact_ids:
            raise ResumeValidationError("The claim is already linked to a career fact")
        if not selected_block.content.title:
            raise ResumeValidationError("Add a claim title before promoting it")

        next_position = int(
            self.db.query(func.coalesce(func.max(CareerFact.position), -1))
            .filter(CareerFact.profile_id == profile.id)
            .scalar()
        ) + 1
        fact_data = CareerFactInput(
            fact_type="achievement",
            position=next_position,
            payload={
                "title": selected_block.content.title,
                "description": selected_block.content.description,
                "details": selected_block.content.bullets,
                "context": selected_block.content.subtitle or None,
            },
            source_locator=f"resume:{draft.id}:block:{selected_block.id}",
            confidence=1,
            verification_status="confirmed",
        )
        fact_id = str(uuid4())
        self.db.add(
            CareerFact(
                id=fact_id,
                profile_id=profile.id,
                fact_type=fact_data.fact_type,
                position=fact_data.position,
                payload=fact_data.payload,
                source_document_id=None,
                source_locator=fact_data.source_locator,
                confidence=fact_data.confidence,
                verification_status=fact_data.verification_status,
            )
        )
        selected_block.fact_ids = [fact_id]
        selected_block.manual_fields = [
            "title",
            "subtitle",
            "date_range",
            "description",
            "bullets",
        ]
        config, overrides = legacy_fields(canvas, draft.section_config)
        draft.section_config = config.model_dump(mode="json")
        draft.content_overrides = overrides
        draft.canvas_document = canvas.model_dump(mode="json")
        draft.selected_fact_ids = [*draft.selected_fact_ids, fact_id]
        profile.revision += 1
        draft.profile_revision = profile.revision
        draft.revision += 1
        self.db.commit()
        self.db.expire_all()
        refreshed_profile = self.drafts.profile(user_id)
        refreshed_draft = self.drafts.draft(user_id, draft_id)
        return self.drafts.response(refreshed_profile, refreshed_draft)
