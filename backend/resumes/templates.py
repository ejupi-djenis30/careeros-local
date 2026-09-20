from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from backend.resumes.canvas_schemas import CanvasStyle

TemplateLayout = Literal["ats", "swiss-photo", "swiss-operational"]
PhotoPolicy = Literal["forbidden", "optional"]
TemplateLocale = Literal["en", "de"]

SECTION_HEADINGS_EN: dict[str, str] = {
    "identity": "IDENTITY",
    "summary": "PROFILE",
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

SECTION_HEADINGS_DE: dict[str, str] = {
    "identity": "PERSÖNLICHE ANGABEN",
    "summary": "KURZPROFIL",
    "experience": "BERUFSERFAHRUNG",
    "education": "AUSBILDUNG",
    "project": "PROJEKTE",
    "skill": "KOMPETENZEN",
    "language": "SPRACHEN",
    "certification": "ZERTIFIKATE",
    "achievement": "ERFOLGE",
    "volunteering": "ENGAGEMENT",
    "publication": "PUBLIKATIONEN",
    "link": "LINKS",
    "award": "AUSZEICHNUNGEN",
    "membership": "MITGLIEDSCHAFTEN",
    "portfolio": "PORTFOLIO",
}


@dataclass(frozen=True)
class TemplatePreset:
    id: str
    version: int
    name: str
    family: str
    locale: TemplateLocale
    layout: TemplateLayout
    template_kind: Literal["ats", "photo"]
    photo_policy: PhotoPolicy
    page_budget: int
    letter_pairing: str
    description: str
    preview_style: Mapping[str, Any] = field(default_factory=dict)
    section_headings: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validate actual canvas defaults and copy mappings before freezing them.
        style = CanvasStyle.model_validate(dict(self.preview_style)).model_dump()
        style["has_sidebar"] = self.layout != "ats"
        object.__setattr__(self, "preview_style", MappingProxyType(style))
        object.__setattr__(self, "section_headings", MappingProxyType(dict(self.section_headings)))

    @property
    def allows_photo(self) -> bool:
        return self.photo_policy == "optional"


PRESETS: tuple[TemplatePreset, ...] = (
    TemplatePreset(
        id="software-en",
        version=1,
        name="Software Engineer (ATS)",
        family="software",
        locale="en",
        layout="ats",
        template_kind="ats",
        photo_policy="forbidden",
        page_budget=2,
        letter_pairing="software-letter-en",
        description="Clean, single-column international ATS layout tailored for software engineering.",
        preview_style={
            "columns": 1,
            "font_family": "Helvetica",
            "accent_color": "#111827",
            "base_font_size": 9.5,
            "margin_mm": 16.5,
            "has_sidebar": False,
        },
        section_headings=SECTION_HEADINGS_EN,
    ),
    TemplatePreset(
        id="cloud-platform-en",
        version=1,
        name="Cloud & Platform (ATS)",
        family="cloud-platform",
        locale="en",
        layout="ats",
        template_kind="ats",
        photo_policy="forbidden",
        page_budget=2,
        letter_pairing="cloud-letter-en",
        description="High-clarity single-column ATS layout for cloud, DevOps, and platform roles.",
        preview_style={
            "columns": 1,
            "font_family": "Helvetica",
            "accent_color": "#0369A1",
            "base_font_size": 9.5,
            "margin_mm": 16.5,
            "has_sidebar": False,
        },
        section_headings=SECTION_HEADINGS_EN,
    ),
    TemplatePreset(
        id="swiss-software-en",
        version=1,
        name="Swiss Software (EN)",
        family="swiss-software",
        locale="en",
        layout="swiss-photo",
        template_kind="photo",
        photo_policy="optional",
        page_budget=2,
        letter_pairing="swiss-letter-en",
        description="Modern Swiss dual-column layout with optional profile photo for tech roles in Switzerland.",
        preview_style={
            "columns": 2,
            "font_family": "Arial",
            "accent_color": "#1E3A8A",
            "base_font_size": 9.0,
            "margin_mm": 15.0,
            "has_sidebar": True,
        },
        section_headings=SECTION_HEADINGS_EN,
    ),
    TemplatePreset(
        id="swiss-software-de",
        version=1,
        name="Schweizer Software (DE)",
        family="swiss-software",
        locale="de",
        layout="swiss-photo",
        template_kind="photo",
        photo_policy="optional",
        page_budget=2,
        letter_pairing="swiss-letter-de",
        description="Modernes Schweizer Zweispalten-Layout mit optionalem Bewerbungsfoto für IT-Fachkräfte.",
        preview_style={
            "columns": 2,
            "font_family": "Arial",
            "accent_color": "#1E3A8A",
            "base_font_size": 9.0,
            "margin_mm": 15.0,
            "has_sidebar": True,
        },
        section_headings=SECTION_HEADINGS_DE,
    ),
    TemplatePreset(
        id="swiss-infrastructure-en",
        version=1,
        name="Swiss Infrastructure (EN)",
        family="swiss-infrastructure",
        locale="en",
        layout="swiss-photo",
        template_kind="photo",
        photo_policy="optional",
        page_budget=2,
        letter_pairing="swiss-infra-letter-en",
        description="Structured Swiss layout with sidebar and optional photo for systems and network engineering.",
        preview_style={
            "columns": 2,
            "font_family": "Arial",
            "accent_color": "#0F766E",
            "base_font_size": 9.0,
            "margin_mm": 15.0,
            "has_sidebar": True,
        },
        section_headings=SECTION_HEADINGS_EN,
    ),
    TemplatePreset(
        id="swiss-infrastructure-de",
        version=1,
        name="Schweizer Infrastruktur (DE)",
        family="swiss-infrastructure",
        locale="de",
        layout="swiss-photo",
        template_kind="photo",
        photo_policy="optional",
        page_budget=2,
        letter_pairing="swiss-infra-letter-de",
        description="Klares Schweizer Zweispalten-Layout für Systemtechnik, Netzwerke und IT-Betrieb.",
        preview_style={
            "columns": 2,
            "font_family": "Arial",
            "accent_color": "#0F766E",
            "base_font_size": 9.0,
            "margin_mm": 15.0,
            "has_sidebar": True,
        },
        section_headings=SECTION_HEADINGS_DE,
    ),
    TemplatePreset(
        id="logistics-de",
        version=1,
        name="Logistik & Disposition (DE)",
        family="logistics",
        locale="de",
        layout="swiss-operational",
        template_kind="photo",
        photo_policy="optional",
        page_budget=1,
        letter_pairing="operational-letter-de",
        description="Kompaktes, einseitiges Schweizer Betriebs-Layout für Logistik, Lager und Disposition.",
        preview_style={
            "columns": 2,
            "font_family": "Arial",
            "accent_color": "#854D0E",
            "base_font_size": 9.0,
            "margin_mm": 12.0,
            "has_sidebar": True,
        },
        section_headings=SECTION_HEADINGS_DE,
    ),
    TemplatePreset(
        id="retail-de",
        version=1,
        name="Detailhandel & Kundendienst (DE)",
        family="retail",
        locale="de",
        layout="swiss-operational",
        template_kind="photo",
        photo_policy="optional",
        page_budget=1,
        letter_pairing="operational-letter-de",
        description="Kompaktes, übersichtliches Betriebs-Layout für Verkauf, Detailhandel und Service.",
        preview_style={
            "columns": 2,
            "font_family": "Arial",
            "accent_color": "#9A3412",
            "base_font_size": 9.0,
            "margin_mm": 12.0,
            "has_sidebar": True,
        },
        section_headings=SECTION_HEADINGS_DE,
    ),
    TemplatePreset(
        id="operational-de",
        version=1,
        name="Betrieb & Technik (DE)",
        family="operational",
        locale="de",
        layout="swiss-operational",
        template_kind="photo",
        photo_policy="optional",
        page_budget=1,
        letter_pairing="operational-letter-de",
        description="Kompaktes einseitiges Arbeits- und Technik-Layout für operative Fachkräfte.",
        preview_style={
            "columns": 2,
            "font_family": "Arial",
            "accent_color": "#374151",
            "base_font_size": 9.0,
            "margin_mm": 12.0,
            "has_sidebar": True,
        },
        section_headings=SECTION_HEADINGS_DE,
    ),
)

PRESETS_BY_ID: Mapping[str, TemplatePreset] = MappingProxyType(
    {preset.id: preset for preset in PRESETS}
)
DEFAULT_ATS_PRESET_ID = "software-en"
DEFAULT_PHOTO_PRESET_ID = "swiss-software-en"


def get_template_preset(template_id: str, version: int | None = None) -> TemplatePreset:
    preset = PRESETS_BY_ID.get(template_id)
    if preset is None:
        raise ValueError(f"Unknown template preset '{template_id}'")
    if version is not None and preset.version != version:
        raise ValueError(f"Unknown version {version} for template preset '{template_id}'")
    return preset


def list_template_presets() -> list[TemplatePreset]:
    return list(PRESETS)


def resolve_template_defaults(
    template_id: str | None = None,
    template_version: int | None = None,
    locale: str | None = None,
    template_kind: str | None = None,
) -> tuple[TemplatePreset, str]:
    """Resolve preset, version, locale, and legacy template_kind deterministically."""
    if locale is not None and locale not in {"en", "de"}:
        raise ValueError("Unsupported template locale")
    if template_id is not None and not template_id.strip():
        raise ValueError("Template preset ID cannot be empty")
    if not template_id and template_version is not None:
        raise ValueError("Template version requires an explicit template preset ID")
    if template_id:
        preset = get_template_preset(template_id, template_version)
    elif template_kind == "photo":
        # Legacy template_kind fallback
        preset = get_template_preset(DEFAULT_PHOTO_PRESET_ID)
    else:
        # Default to ATS
        preset = get_template_preset(DEFAULT_ATS_PRESET_ID)
    if locale is not None and locale != preset.locale:
        raise ValueError(f"Template locale does not match preset '{preset.id}'")
    return preset, preset.locale
