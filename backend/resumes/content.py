from dataclasses import dataclass, field
from datetime import date
from typing import Any

SECTION_HEADINGS = {
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


@dataclass(frozen=True)
class ResumeEntry:
    fact_id: str
    title: str
    subtitle: str = ""
    date_range: str = ""
    description: str = ""
    bullets: list[str] = field(default_factory=list)
    layout: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResumeSection:
    key: str
    heading: str
    entries: list[ResumeEntry]
    page_break_before: bool = False


@dataclass(frozen=True)
class ResumeContent:
    display_name: str
    headline: str
    contact_line: str
    summary: str
    sections: list[ResumeSection]
    summary_heading: str = "PROFILE"
    style: dict[str, Any] = field(default_factory=dict)

    @property
    def required_headings(self) -> list[str]:
        headings = [section.heading for section in self.sections]
        return ([self.summary_heading] if self.summary else []) + headings


def _date_label(value: str | date | None) -> str:
    if not value:
        return ""
    try:
        parsed = value if isinstance(value, date) else date.fromisoformat(str(value))
        return parsed.strftime("%b %Y")
    except ValueError:
        return str(value)


def _date_range(payload: dict[str, Any]) -> str:
    start = _date_label(payload.get("start_date") or payload.get("issued_on"))
    if payload.get("current"):
        end = "Present"
    else:
        end = _date_label(payload.get("end_date") or payload.get("expires_on"))
    if start and end:
        return f"{start} – {end}"
    return start or end


def _join(*values: Any, separator: str = " · ") -> str:
    return separator.join(str(value).strip() for value in values if value not in (None, ""))


def _base_entry(fact: dict[str, Any]) -> ResumeEntry:
    fact_type = fact["fact_type"]
    payload = fact["payload"]
    fact_id = fact["id"]
    if fact_type == "experience":
        return ResumeEntry(
            fact_id=fact_id,
            title=payload["role"],
            subtitle=_join(payload["organization"], payload.get("location")),
            date_range=_date_range(payload),
            description=payload.get("description", ""),
            bullets=list(payload.get("achievements", [])),
        )
    if fact_type == "education":
        return ResumeEntry(
            fact_id=fact_id,
            title=payload["qualification"],
            subtitle=_join(payload["institution"], payload.get("field"), payload.get("grade")),
            date_range=_date_range(payload),
            description=payload.get("description", ""),
        )
    if fact_type == "project":
        return ResumeEntry(
            fact_id=fact_id,
            title=payload["name"],
            subtitle=_join(payload.get("role"), payload.get("url")),
            date_range=_date_range(payload),
            description=payload.get("description", ""),
            bullets=list(payload.get("achievements", [])),
        )
    if fact_type == "skill":
        years = payload.get("years")
        years_label = f"{years:g} years" if isinstance(years, (int, float)) else ""
        return ResumeEntry(
            fact_id=fact_id,
            title=payload["name"],
            subtitle=_join(payload.get("level"), years_label),
        )
    if fact_type == "language":
        return ResumeEntry(
            fact_id=fact_id,
            title=payload["language"],
            subtitle=str(payload["level"]),
        )
    if fact_type == "certification":
        return ResumeEntry(
            fact_id=fact_id,
            title=payload["name"],
            subtitle=_join(payload.get("issuer"), payload.get("credential_id"), payload.get("url")),
            date_range=_date_range(payload),
        )
    if fact_type == "achievement":
        metric = _join(payload.get("metric_value"), payload.get("metric_unit"), separator=" ")
        return ResumeEntry(
            fact_id=fact_id,
            title=payload["title"],
            subtitle=_join(metric, payload.get("context")),
            description=payload.get("description", ""),
        )
    if fact_type == "link":
        return ResumeEntry(fact_id=fact_id, title=payload["label"], subtitle=payload["url"])
    if fact_type == "award":
        return ResumeEntry(
            fact_id=fact_id,
            title=payload["title"],
            subtitle=_join(payload.get("issuer"), payload.get("url")),
            date_range=_date_label(payload.get("awarded_on")),
            description=payload.get("description", ""),
        )
    if fact_type == "membership":
        return ResumeEntry(
            fact_id=fact_id,
            title=payload["role"],
            subtitle=_join(payload["organization"], payload.get("url")),
            date_range=_date_range(payload),
            description=payload.get("description", ""),
        )
    if fact_type == "portfolio":
        return ResumeEntry(
            fact_id=fact_id,
            title=payload["name"],
            subtitle=payload["url"],
            description=payload.get("description", ""),
            bullets=list(payload.get("skills", [])),
        )
    return ResumeEntry(
        fact_id=fact_id,
        title=payload["title"],
        description=payload.get("description", ""),
        date_range=_date_range(payload),
    )


def _apply_override(entry: ResumeEntry, override: dict[str, Any] | None) -> ResumeEntry:
    if not override:
        return entry
    return ResumeEntry(
        fact_id=entry.fact_id,
        title=override.get("title") or entry.title,
        subtitle=override.get("subtitle") or entry.subtitle,
        date_range=entry.date_range,
        description=(
            override["description"]
            if override.get("description") is not None
            else entry.description
        ),
        bullets=(override["bullets"] if override.get("bullets") is not None else entry.bullets),
        layout=entry.layout,
    )


def _build_canvas_content(snapshot: dict[str, Any], canvas: dict[str, Any]) -> ResumeContent:
    profile = snapshot["profile"]
    identity = next(
        (section for section in canvas["sections"] if section["kind"] == "identity"), None
    )
    identity_block = next(
        (
            block
            for block in (identity or {}).get("blocks", [])
            if block.get("visible", True)
        ),
        None,
    )
    identity_content = (identity_block or {}).get("content", {})
    summary_section = next(
        (
            section
            for section in canvas["sections"]
            if section["kind"] == "summary" and section.get("visible", True)
        ),
        None,
    )
    summary_blocks = [
        block
        for block in (summary_section or {}).get("blocks", [])
        if block.get("visible", True)
    ]
    summary = "\n".join(
        block.get("content", {}).get("description", "")
        for block in summary_blocks
        if block.get("content", {}).get("description")
    )
    sections: list[ResumeSection] = []
    for section in canvas["sections"]:
        if section["kind"] in {"identity", "summary"} or not section.get("visible", True):
            continue
        entries = []
        for block in section.get("blocks", []):
            if not block.get("visible", True):
                continue
            content = block.get("content", {})
            entries.append(
                ResumeEntry(
                    fact_id=(block.get("fact_ids") or [""])[0],
                    title=content.get("title", ""),
                    subtitle=content.get("subtitle", ""),
                    date_range=content.get("date_range", ""),
                    description=content.get("description", ""),
                    bullets=list(content.get("bullets", [])),
                    layout=dict(block.get("layout", {})),
                )
            )
        if entries:
            sections.append(
                ResumeSection(
                    key=section["kind"],
                    heading=section["title"],
                    entries=entries,
                    page_break_before=section.get("page_break_before", False),
                )
            )
    return ResumeContent(
        display_name=identity_content.get("title") or profile["display_name"],
        headline=identity_content.get("subtitle") or profile.get("headline", ""),
        contact_line=identity_content.get("description", ""),
        summary=summary,
        summary_heading=(summary_section or {}).get("title", "PROFILE"),
        sections=sections,
        style=dict(canvas.get("style", {})),
    )


def build_content(snapshot: dict[str, Any]) -> ResumeContent:
    profile = snapshot["profile"]
    resume = snapshot["resume"]
    config = resume["section_config"]
    canvas = resume.get("canvas_document")
    if canvas and canvas.get("sections"):
        return _build_canvas_content(snapshot, canvas)
    overrides = resume.get("content_overrides", {})
    grouped: dict[str, list[ResumeEntry]] = {}
    for fact in snapshot["facts"]:
        entry = _apply_override(_base_entry(fact), overrides.get(fact["id"]))
        grouped.setdefault(fact["fact_type"], []).append(entry)

    sections = [
        ResumeSection(key=key, heading=SECTION_HEADINGS[key], entries=grouped[key])
        for key in config["order"]
        if grouped.get(key)
    ]
    contact: list[str] = []
    if config.get("include_email") and profile.get("email"):
        contact.append(profile["email"])
    if config.get("include_phone") and profile.get("phone"):
        contact.append(profile["phone"])
    if config.get("include_location") and profile.get("location"):
        location = profile["location"]
        if isinstance(location, dict):
            contact.append(_join(*location.values(), separator=", "))
        else:
            contact.append(str(location))
    if config.get("include_links"):
        contact.extend(
            value
            for value in (profile.get("website"), profile.get("linkedin"), profile.get("github"))
            if value
        )
    return ResumeContent(
        display_name=profile["display_name"],
        headline=profile.get("headline", ""),
        contact_line=" | ".join(contact),
        summary=profile.get("summary", "") if config.get("include_summary") else "",
        sections=sections,
    )
