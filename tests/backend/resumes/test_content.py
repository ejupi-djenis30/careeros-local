from datetime import date
from typing import Any

import pytest

from backend.resumes.content import (
    ResumeEntry,
    _apply_override,
    _base_entry,
    _date_label,
    _date_range,
    build_content,
)


@pytest.mark.parametrize(
    ("fact_type", "payload", "title"),
    [
        (
            "experience",
            {
                "role": "Engineer",
                "organization": "Local Systems",
                "location": "Zurich",
                "start_date": "2024-01-01",
                "current": True,
                "description": "Built private software.",
                "achievements": ["Shipped the desktop app."],
            },
            "Engineer",
        ),
        (
            "education",
            {
                "qualification": "BSc",
                "institution": "Example University",
                "field": "Computer Science",
                "grade": "A",
                "start_date": "2018-09-01",
                "end_date": "2021-06-01",
                "description": "Systems track.",
            },
            "BSc",
        ),
        (
            "project",
            {
                "name": "CareerOS",
                "role": "Creator",
                "url": "https://example.test",
                "start_date": "2026-07-01",
                "description": "Local-first workspace.",
                "achievements": ["Packaged locally."],
            },
            "CareerOS",
        ),
        ("skill", {"name": "Python", "level": "Advanced", "years": 6}, "Python"),
        ("language", {"language": "Italian", "level": "Native"}, "Italian"),
        (
            "certification",
            {
                "name": "Security",
                "issuer": "Example Org",
                "credential_id": "CERT-1",
                "url": "https://example.test/cert",
                "issued_on": "2025-03-01",
                "expires_on": "2027-03-01",
            },
            "Security",
        ),
        (
            "achievement",
            {
                "title": "Reduced latency",
                "metric_value": 40,
                "metric_unit": "%",
                "context": "API",
                "description": "Measured improvement.",
            },
            "Reduced latency",
        ),
        ("link", {"label": "Portfolio", "url": "https://example.test"}, "Portfolio"),
        (
            "award",
            {
                "title": "Engineering Award",
                "issuer": "Example Org",
                "url": "https://example.test/award",
                "awarded_on": "2025-05-01",
                "description": "For dependable delivery.",
            },
            "Engineering Award",
        ),
        (
            "membership",
            {
                "role": "Member",
                "organization": "Example Guild",
                "url": "https://example.test/guild",
                "start_date": "2024-01-01",
                "description": "Local chapter.",
            },
            "Member",
        ),
        (
            "portfolio",
            {
                "name": "Private AI",
                "url": "https://example.test/project",
                "description": "On-device inference.",
                "skills": ["Rust", "Python"],
            },
            "Private AI",
        ),
        (
            "volunteering",
            {
                "title": "Mentor",
                "description": "Helped new developers.",
                "start_date": "not-a-date",
            },
            "Mentor",
        ),
    ],
)
def test_resume_entries_cover_every_supported_fact_shape(
    fact_type: str, payload: dict[str, Any], title: str
) -> None:
    entry = _base_entry({"id": f"fact-{fact_type}", "fact_type": fact_type, "payload": payload})

    assert entry.fact_id == f"fact-{fact_type}"
    assert entry.title == title


def test_date_helpers_and_content_override_preserve_explicit_empty_values() -> None:
    assert _date_label(None) == ""
    assert _date_label(date(2026, 7, 1)) == "Jul 2026"
    assert _date_label("not-a-date") == "not-a-date"
    assert _date_range({"start_date": "2024-01-01", "current": True}) == "Jan 2024 – Present"
    assert _date_range({"end_date": "2025-02-01"}) == "Feb 2025"

    entry = ResumeEntry(
        fact_id="fact-1",
        title="Original",
        subtitle="Company",
        description="Original description",
        bullets=["Original bullet"],
        layout={"keep_together": True},
    )
    assert _apply_override(entry, None) is entry
    overridden = _apply_override(
        entry,
        {"title": "Edited", "description": "", "bullets": []},
    )
    assert overridden.title == "Edited"
    assert overridden.subtitle == "Company"
    assert overridden.description == ""
    assert overridden.bullets == []
    assert overridden.layout == {"keep_together": True}


def test_build_content_groups_facts_and_builds_the_selected_contact_fields() -> None:
    snapshot = {
        "profile": {
            "display_name": "Ada Example",
            "headline": "Local systems engineer",
            "summary": "Builds dependable tools.",
            "email": "ada@example.test",
            "phone": "+41 00 000 00 00",
            "location": {"city": "Zurich", "country": "Switzerland"},
            "website": "https://example.test",
            "linkedin": "https://linkedin.example/ada",
            "github": "https://github.com/example",
        },
        "facts": [
            {
                "id": "experience-1",
                "fact_type": "experience",
                "payload": {
                    "role": "Engineer",
                    "organization": "Local Systems",
                    "start_date": "2024-01-01",
                    "current": True,
                },
            }
        ],
        "resume": {
            "section_config": {
                "order": ["experience", "education"],
                "include_email": True,
                "include_phone": True,
                "include_location": True,
                "include_links": True,
                "include_summary": True,
            },
            "content_overrides": {"experience-1": {"title": "Principal Engineer"}},
        },
    }

    content = build_content(snapshot)

    assert content.display_name == "Ada Example"
    assert content.summary == "Builds dependable tools."
    assert content.required_headings == ["PROFILE", "EXPERIENCE"]
    assert content.sections[0].entries[0].title == "Principal Engineer"
    assert content.contact_line == (
        "ada@example.test | +41 00 000 00 00 | Zurich, Switzerland | "
        "https://example.test | https://linkedin.example/ada | https://github.com/example"
    )


def test_build_content_uses_visible_canvas_blocks_and_layout() -> None:
    snapshot = {
        "profile": {"display_name": "Fallback Name", "headline": "Fallback headline"},
        "facts": [],
        "resume": {
            "section_config": {"order": []},
            "canvas_document": {
                "style": {"accent": "#b9f27c"},
                "sections": [
                    {
                        "kind": "identity",
                        "blocks": [
                            {
                                "visible": True,
                                "content": {
                                    "title": "Ada Canvas",
                                    "subtitle": "Principal Engineer",
                                    "description": "ada@example.test",
                                },
                            }
                        ],
                    },
                    {
                        "kind": "summary",
                        "title": "ABOUT",
                        "visible": True,
                        "blocks": [
                            {"visible": False, "content": {"description": "Hidden"}},
                            {"visible": True, "content": {"description": "Visible summary"}},
                        ],
                    },
                    {
                        "kind": "experience",
                        "title": "SELECTED EXPERIENCE",
                        "visible": True,
                        "page_break_before": True,
                        "blocks": [
                            {"visible": False, "content": {"title": "Hidden role"}},
                            {
                                "visible": True,
                                "fact_ids": ["experience-1"],
                                "content": {
                                    "title": "Engineer",
                                    "subtitle": "Local Systems",
                                    "date_range": "2024 – Present",
                                    "description": "Built local tools.",
                                    "bullets": ["Shipped safely."],
                                },
                                "layout": {"keep_together": True},
                            },
                        ],
                    },
                    {"kind": "education", "title": "EDUCATION", "visible": False},
                ],
            },
        },
    }

    content = build_content(snapshot)

    assert content.display_name == "Ada Canvas"
    assert content.headline == "Principal Engineer"
    assert content.contact_line == "ada@example.test"
    assert content.summary == "Visible summary"
    assert content.summary_heading == "ABOUT"
    assert content.style == {"accent": "#b9f27c"}
    assert content.required_headings == ["ABOUT", "SELECTED EXPERIENCE"]
    assert content.sections[0].page_break_before is True
    assert content.sections[0].entries[0].layout == {"keep_together": True}
