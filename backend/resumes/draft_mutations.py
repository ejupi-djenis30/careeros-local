from typing import Any

from backend.career.models import CandidateProfile, CareerFact
from backend.resumes.canvas import build_canvas, legacy_fields, normalize_canvas
from backend.resumes.canvas_validation import validate_canvas_references
from backend.resumes.exceptions import ResumeValidationError
from backend.resumes.models import ResumeDraft
from backend.resumes.presentation import apply_presentation
from backend.resumes.sync import apply_sync
from backend.resumes.templates import resolve_template_defaults


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
    if data.canvas_document and set(draft.selected_fact_ids or []) != set(data.selected_fact_ids):
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
    preset, locale = resolve_template_defaults(
        data.template_id, data.template_version, data.locale, data.template_kind
    )
    previous = None
    if draft.template_id:
        previous, _ = resolve_template_defaults(
            draft.template_id, draft.template_version, draft.locale, draft.template_kind
        )
    if previous is None or (previous.id, previous.version, draft.locale) != (
        preset.id,
        preset.version,
        locale,
    ):
        canvas = apply_presentation(canvas, preset, locale=locale, previous=previous)
    try:
        validate_canvas_references(canvas, set(data.selected_fact_ids))
    except ValueError as exc:
        raise ResumeValidationError(str(exc)) from exc
    config, overrides = legacy_fields(canvas, data.section_config)
    draft.title = data.title
    draft.template_kind = data.template_kind
    draft.template_id = getattr(data, "template_id", "software-en") or "software-en"
    draft.template_version = getattr(data, "template_version", 1) or 1
    draft.locale = getattr(data, "locale", "en") or "en"
    draft.section_config = config.model_dump(mode="json")
    draft.selected_fact_ids = list(data.selected_fact_ids)
    draft.content_overrides = overrides
    draft.canvas_document = canvas.model_dump(mode="json")
    # ATS suppresses the photo in output; retain the owned selection for a later switch.
    if draft.template_kind != "ats":
        draft.photo_asset_id = data.photo_asset_id
