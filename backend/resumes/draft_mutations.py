from typing import Any

from backend.career.models import CandidateProfile, CareerFact
from backend.resumes.canvas import build_canvas, legacy_fields, normalize_canvas
from backend.resumes.canvas_validation import validate_canvas_references
from backend.resumes.exceptions import ResumeValidationError
from backend.resumes.models import ResumeDraft
from backend.resumes.sync import apply_sync


def apply_draft_data(
    draft: ResumeDraft,
    data: Any,
    facts: list[CareerFact],
    profile: CandidateProfile,
) -> None:
    canvas = normalize_canvas(
        data.canvas_document,
        profile=profile,
        facts=facts,
        template_kind=data.template_kind,
        section_config=data.section_config,
        content_overrides=data.content_overrides,
    )
    if data.canvas_document:
        generated = build_canvas(
            profile=profile,
            facts=facts,
            template_kind=data.template_kind,
            section_config=data.section_config,
        )
        kinds: set[str] = {section.kind for section in canvas.sections} | {
            section.kind for section in generated.sections
        }
        canvas = apply_sync(canvas, generated, kinds)
    try:
        validate_canvas_references(canvas, set(data.selected_fact_ids))
    except ValueError as exc:
        raise ResumeValidationError(str(exc)) from exc
    config, overrides = legacy_fields(canvas, data.section_config)
    draft.title = data.title
    draft.template_kind = data.template_kind
    draft.section_config = config.model_dump(mode="json")
    draft.selected_fact_ids = list(data.selected_fact_ids)
    draft.content_overrides = overrides
    draft.canvas_document = canvas.model_dump(mode="json")
    draft.photo_asset_id = data.photo_asset_id
