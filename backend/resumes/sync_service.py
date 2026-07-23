from sqlalchemy.orm import Session

from backend.career.models import CareerGoal
from backend.resumes.canvas import legacy_fields, normalize_canvas
from backend.resumes.draft_service import ResumeDraftService
from backend.resumes.exceptions import ResumeConflictError, ResumeValidationError
from backend.resumes.generator import generate_resume
from backend.resumes.schemas import ResumeSync, ResumeSyncResponse
from backend.resumes.sync import apply_sync, plan_sync, selected_ids


class ResumeSynchronizationService:
    def __init__(self, db: Session, drafts: ResumeDraftService):
        self.db = db
        self.drafts = drafts

    def synchronize(
        self, user_id: int, draft_id: str, data: ResumeSync
    ) -> ResumeSyncResponse:
        profile = self.drafts.profile(user_id)
        draft = self.drafts.draft(user_id, draft_id)
        if draft.revision != data.expected_revision:
            raise ResumeConflictError(
                f"Expected revision {data.expected_revision}, current revision is {draft.revision}"
            )
        current_facts = self.drafts.ordered_facts(profile, list(draft.selected_fact_ids))
        current_canvas = normalize_canvas(
            draft.canvas_document,
            profile=profile,
            facts=current_facts,
            template_kind=draft.template_kind,
            section_config=draft.section_config,
            content_overrides=draft.content_overrides,
        )
        context = draft.generation_context or {}
        goal = None
        if context.get("career_goal_id"):
            goal = (
                self.db.query(CareerGoal)
                .filter(
                    CareerGoal.id == context["career_goal_id"],
                    CareerGoal.profile_id == profile.id,
                )
                .first()
            )
        generated = generate_resume(
            profile,
            profile.facts,
            template_kind=draft.template_kind,
            goal=goal,
            target_job_id=context.get("target_job_id"),
            target_snapshot=context.get("target_snapshot") or {},
        )
        plan = plan_sync(current_canvas, generated.canvas)
        result = ResumeSyncResponse(
            source_profile_revision=draft.profile_revision,
            current_profile_revision=profile.revision,
            sections=plan.sections,
            preserved_manual_fields=plan.preserved_manual_fields,
        )
        if data.mode == "preview":
            return result
        available = {section.kind for section in current_canvas.sections} | {
            section.kind for section in generated.canvas.sections
        }
        requested = set(data.sections)
        if data.mode == "apply" and not requested:
            raise ResumeValidationError("Select at least one canvas section to synchronize")
        if requested - available:
            raise ResumeValidationError(
                "Unknown canvas sections: " + ", ".join(sorted(requested - available))
            )
        merged = apply_sync(
            current_canvas,
            generated.canvas,
            requested,
            reset=data.mode == "reset",
        )
        ids = selected_ids(merged)
        if not ids:
            raise ResumeValidationError("Synchronized resume contains no career facts")
        config, overrides = legacy_fields(merged, draft.section_config)
        draft.canvas_document = merged.model_dump(mode="json")
        draft.selected_fact_ids = ids
        draft.section_config = config.model_dump(mode="json")
        draft.content_overrides = overrides
        draft.profile_revision = profile.revision
        draft.generation_context = generated.generation_context.model_dump(
            mode="json", exclude_none=True
        )
        draft.revision += 1
        self.db.commit()
        self.db.expire_all()
        result.applied = True
        result.draft = self.drafts.response(
            profile, self.drafts.draft(user_id, draft_id)
        )
        return result
