from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping, cast

from backend.career.schemas import FactType
from backend.resumes.canvas_schemas import (
    CanvasBlock,
    CanvasContent,
    CanvasSection,
    CanvasSectionKind,
    CanvasStyle,
    ResumeCanvasDocument,
)
from backend.resumes.schemas import ResumeSectionConfig, TemplateKind

SECTION_TITLES = {
    "experience": "EXPERIENCE",
    "education": "EDUCATION",
    "project": "PROJECTS",
    "skill": "SKILLS",
    "language": "LANGUAGES",
    "certification": "CERTIFICATIONS",
    "achievement": "ACHIEVEMENTS",
    "volunteering": "VOLUNTEERING",
    "publication": "PUBLICATIONS",
    "link": "LINKS",
    "award": "AWARDS",
    "membership": "MEMBERSHIPS",
    "portfolio": "PORTFOLIO",
}


def _read(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _date_label(value: str | date | None) -> str:
    if not value:
        return ""
    try:
        parsed = value if isinstance(value, date) else date.fromisoformat(str(value))
        return parsed.strftime("%b %Y")
    except ValueError:
        return str(value)


def _date_range(payload: Mapping[str, Any]) -> str:
    start = _date_label(
        payload.get("start_date") or payload.get("issued_on") or payload.get("awarded_on")
    )
    end = "Present" if payload.get("current") else _date_label(
        payload.get("end_date") or payload.get("expires_on") or payload.get("published_on")
    )
    return " – ".join(item for item in (start, end) if item)


def _join(*values: Any, separator: str = " · ") -> str:
    return separator.join(str(value).strip() for value in values if value not in (None, ""))


def fact_content(fact: Any) -> CanvasContent:
    fact_type = _read(fact, "fact_type")
    payload = _read(fact, "payload", {})
    if fact_type == "experience":
        return CanvasContent(
            title=payload["role"],
            subtitle=_join(payload["organization"], payload.get("location")),
            date_range=_date_range(payload),
            description=payload.get("description", ""),
            bullets=list(payload.get("achievements") or payload.get("responsibilities") or []),
        )
    if fact_type == "education":
        details = list(payload.get("activities", [])) + list(payload.get("coursework", []))
        return CanvasContent(
            title=payload["qualification"],
            subtitle=_join(payload["institution"], payload.get("field"), payload.get("grade")),
            date_range=_date_range(payload),
            description=payload.get("description") or payload.get("thesis", ""),
            bullets=details,
        )
    if fact_type == "project":
        return CanvasContent(
            title=payload["name"],
            subtitle=_join(
                payload.get("role"), payload.get("organization"), payload.get("client")
            ),
            date_range=_date_range(payload),
            description=payload.get("description", ""),
            bullets=list(payload.get("achievements", [])),
        )
    if fact_type == "skill":
        years = payload.get("years")
        years_label = f"{years:g} years" if isinstance(years, (int, float)) else ""
        return CanvasContent(
            title=payload["name"],
            subtitle=_join(payload.get("category"), payload.get("level"), years_label),
        )
    if fact_type == "language":
        return CanvasContent(title=payload["language"], subtitle=str(payload["level"]))
    if fact_type == "certification":
        return CanvasContent(
            title=payload["name"],
            subtitle=_join(payload.get("issuer"), payload.get("credential_id")),
            date_range=_date_range(payload),
        )
    if fact_type == "achievement":
        metric = _join(payload.get("metric_value"), payload.get("metric_unit"), separator=" ")
        return CanvasContent(
            title=payload["title"],
            subtitle=_join(metric, payload.get("context")),
            date_range=_date_label(payload.get("achieved_on")),
            description=payload.get("description", ""),
            bullets=list(payload.get("details", [])),
        )
    if fact_type == "link":
        return CanvasContent(title=payload["label"], subtitle=payload["url"])
    if fact_type == "award":
        return CanvasContent(
            title=payload["title"],
            subtitle=_join(payload.get("issuer"), payload.get("url")),
            date_range=_date_label(payload.get("awarded_on")),
            description=payload.get("description", ""),
        )
    if fact_type == "membership":
        return CanvasContent(
            title=payload["role"],
            subtitle=_join(payload["organization"], payload.get("url")),
            date_range=_date_range(payload),
            description=payload.get("description", ""),
        )
    if fact_type == "portfolio":
        return CanvasContent(
            title=payload["name"],
            subtitle=payload["url"],
            description=payload.get("description", ""),
            bullets=list(payload.get("skills", [])),
        )
    return CanvasContent(
        title=payload["title"],
        subtitle=_join(payload.get("organization"), payload.get("publisher")),
        date_range=_date_range(payload),
        description=payload.get("description", ""),
        bullets=list(payload.get("achievements", [])),
    )


def _profile_contact(profile: Any, config: ResumeSectionConfig) -> str:
    contact: list[str] = []
    if config.include_email and _read(profile, "email"):
        contact.append(_read(profile, "email"))
    if config.include_phone and _read(profile, "phone"):
        contact.append(_read(profile, "phone"))
    location = _read(profile, "location", {})
    if config.include_location and location:
        contact.append(
            _join(*location.values(), separator=", ")
            if isinstance(location, dict)
            else str(location)
        )
    if config.include_links:
        contact.extend(
            value
            for value in (
                _read(profile, "website"),
                _read(profile, "linkedin"),
                _read(profile, "github"),
            )
            if value
        )
    return " | ".join(contact)


def build_canvas(
    *,
    profile: Any,
    facts: Iterable[Any],
    template_kind: TemplateKind,
    section_config: ResumeSectionConfig | Mapping[str, Any] | None = None,
    content_overrides: Mapping[str, Any] | None = None,
) -> ResumeCanvasDocument:
    config = (
        section_config
        if isinstance(section_config, ResumeSectionConfig)
        else ResumeSectionConfig.model_validate(section_config or {})
    )
    overrides = content_overrides or {}
    ordered_facts = list(facts)
    selected_ids = [str(_read(fact, "id")) for fact in ordered_facts]
    sections: list[CanvasSection] = [
        CanvasSection(
            id="identity",
            kind="identity",
            title="IDENTITY",
            blocks=[
                CanvasBlock(
                    id="identity-main",
                    kind="identity",
                    content=CanvasContent(
                        title=_read(profile, "display_name", ""),
                        subtitle=_read(profile, "headline", ""),
                        description=_profile_contact(profile, config),
                    ),
                )
            ],
        )
    ]
    summary = _read(profile, "summary", "")
    if config.include_summary and summary and selected_ids:
        sections.append(
            CanvasSection(
                id="summary",
                kind="summary",
                title="PROFILE",
                blocks=[
                    CanvasBlock(
                        id="summary-main",
                        kind="summary",
                        fact_ids=selected_ids[:100],
                        content=CanvasContent(description=summary),
                    )
                ],
            )
        )
    grouped: dict[str, list[Any]] = {}
    for fact in ordered_facts:
        grouped.setdefault(str(_read(fact, "fact_type")), []).append(fact)
    for fact_type in config.order:
        blocks: list[CanvasBlock] = []
        for fact in grouped.get(fact_type, []):
            fact_id = str(_read(fact, "id"))
            content = fact_content(fact)
            override = overrides.get(fact_id) or {}
            if hasattr(override, "model_dump"):
                override = override.model_dump(exclude_none=True)
            data = content.model_dump()
            manual_fields = [key for key, value in override.items() if value is not None]
            data.update({key: value for key, value in override.items() if value is not None})
            blocks.append(
                CanvasBlock(
                    id=f"fact-{fact_id}",
                    kind="fact",
                    fact_ids=[fact_id],
                    content=CanvasContent.model_validate(data),
                    manual_fields=manual_fields,
                )
            )
        if blocks:
            sections.append(
                CanvasSection(
                    id=fact_type,
                    kind=cast(CanvasSectionKind, fact_type),
                    title=SECTION_TITLES[fact_type],
                    blocks=blocks,
                )
            )
    return ResumeCanvasDocument(
        sections=sections,
        style=CanvasStyle(columns=1),
    )


def normalize_canvas(
    document: Mapping[str, Any] | ResumeCanvasDocument | None,
    *,
    profile: Any,
    facts: Iterable[Any],
    template_kind: TemplateKind,
    section_config: ResumeSectionConfig | Mapping[str, Any] | None = None,
    content_overrides: Mapping[str, Any] | None = None,
) -> ResumeCanvasDocument:
    canvas = (
        ResumeCanvasDocument.model_validate(document)
        if document
        else build_canvas(
            profile=profile,
            facts=facts,
            template_kind=template_kind,
            section_config=section_config,
            content_overrides=content_overrides,
        )
    )
    if template_kind == "ats" and canvas.style.columns != 1:
        raise ValueError("ATS resumes must use a single-column canvas")
    return canvas


def legacy_fields(
    canvas: ResumeCanvasDocument,
    base_config: ResumeSectionConfig | Mapping[str, Any] | None = None,
) -> tuple[ResumeSectionConfig, dict[str, dict]]:
    base = (
        base_config
        if isinstance(base_config, ResumeSectionConfig)
        else ResumeSectionConfig.model_validate(base_config or {})
    )
    canvas_order: list[FactType] = [
        cast(FactType, section.kind)
        for section in canvas.sections
        if section.kind not in {"identity", "summary"}
    ]
    order = [*canvas_order, *(kind for kind in base.order if kind not in canvas_order)]
    config = ResumeSectionConfig(
        order=order or [cast(FactType, key) for key in SECTION_TITLES],
        include_summary=any(section.kind == "summary" and section.visible for section in canvas.sections),
        include_email=base.include_email,
        include_phone=base.include_phone,
        include_location=base.include_location,
        include_links=base.include_links,
    )
    overrides: dict[str, dict] = {}
    for section in canvas.sections:
        for block in section.blocks:
            if block.kind != "fact" or not block.fact_ids or not block.manual_fields:
                continue
            values = block.content.model_dump()
            overrides[block.fact_ids[0]] = {
                field: values[field]
                for field in block.manual_fields
                if field in {"title", "subtitle", "description", "bullets"}
            }
    return config, overrides
