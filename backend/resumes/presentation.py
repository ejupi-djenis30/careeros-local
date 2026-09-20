"""Apply versioned presentation defaults without resynchronizing career claims."""

from backend.resumes.canvas_schemas import CanvasStyle, ResumeCanvasDocument
from backend.resumes.templates import (
    SECTION_HEADINGS_DE,
    SECTION_HEADINGS_EN,
    TemplatePreset,
)


def apply_presentation(
    canvas: ResumeCanvasDocument,
    preset: TemplatePreset,
    *,
    locale: str,
    previous: TemplatePreset | None = None,
) -> ResumeCanvasDocument:
    data = canvas.model_dump(mode="json")
    headings = SECTION_HEADINGS_DE if locale == "de" else SECTION_HEADINGS_EN
    old_defaults = previous.preview_style if previous else CanvasStyle().model_dump()
    for name in CanvasStyle.model_fields:
        value = data["style"][name]
        if value == old_defaults.get(name):
            data["style"][name] = preset.preview_style[name]
    # Layout columns describe the selected preset, not career content.
    data["style"]["columns"] = preset.preview_style["columns"]
    for section in data["sections"]:
        kind = section["kind"]
        defaults = {SECTION_HEADINGS_EN.get(kind), SECTION_HEADINGS_DE.get(kind)}
        if section["title"] in defaults and kind in headings:
            section["title"] = headings[kind]
    return ResumeCanvasDocument.model_validate(data)
