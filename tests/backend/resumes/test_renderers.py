from io import BytesIO

import pytest
from docx import Document
from pypdf import PdfReader

from backend.core.config import settings
from backend.resumes.quality import ResumeQualityError, validate_resume_artifacts
from backend.resumes.renderers.ats import render_ats_docx, render_ats_pdf


def _snapshot(entry_count: int = 2) -> dict:
    blocks = [
        {
            "id": f"fact-{index}",
            "kind": "fact",
            "fact_ids": [f"10000000-0000-4000-8000-{index:012d}"],
            "visible": True,
            "content": {
                "title": f"Role {index}",
                "subtitle": "Local Systems",
                "date_range": "2020 – 2026",
                "description": "Built dependable private systems. " * 8,
                "bullets": ["Reduced lead time by 40 percent."],
            },
            "manual_fields": [],
            "layout": {"spacing_before_pt": 0, "keep_together": True},
        }
        for index in range(entry_count)
    ]
    return {
        "profile": {
            "display_name": "Mira Vale",
            "headline": "Principal Engineer",
            "email": "mira@example.test",
        },
        "resume": {
            "title": "Private systems CV",
            "template_kind": "ats",
            "section_config": {"order": ["experience"]},
            "content_overrides": {},
            "canvas_document": {
                "schema_version": 2,
                "style": {
                    "font_family": "Helvetica",
                    "base_font_size": 10,
                    "line_height": 1.3,
                    "section_spacing": 10,
                    "margin_mm": 18,
                    "accent_color": "#243B53",
                    "columns": 1,
                },
                "sections": [
                    {
                        "id": "identity",
                        "kind": "identity",
                        "title": "IDENTITY",
                        "visible": True,
                        "page_break_before": False,
                        "blocks": [
                            {
                                "id": "identity-main",
                                "kind": "identity",
                                "fact_ids": [],
                                "visible": True,
                                "content": {
                                    "title": "Mira Vale",
                                    "subtitle": "Principal Engineer",
                                    "date_range": "",
                                    "description": "mira@example.test",
                                    "bullets": [],
                                },
                                "manual_fields": [],
                                "layout": {"spacing_before_pt": 0, "keep_together": True},
                            }
                        ],
                    },
                    {
                        "id": "experience",
                        "kind": "experience",
                        "title": "EXPERIENCE",
                        "visible": True,
                        "page_break_before": False,
                        "blocks": blocks,
                    },
                ],
            },
        },
        "facts": [],
    }


def test_ats_renderers_preserve_text_order_and_local_metadata():
    snapshot = _snapshot()
    pdf = render_ats_pdf(snapshot)
    docx = render_ats_docx(snapshot)
    report = validate_resume_artifacts(
        pdf=pdf,
        docx=docx,
        required_headings=["EXPERIENCE"],
        required_text=["Mira Vale", "Role 0", "Role 1"],
        template_kind="ats",
        expect_photo=False,
    )

    pdf_document = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in pdf_document.pages)
    assert pdf_document.metadata is not None
    assert pdf_document.metadata.author == "CareerOS Local"
    assert pdf_document.metadata.title == "Mira Vale"
    word = Document(BytesIO(docx))
    word_text = "\n".join(paragraph.text for paragraph in word.paragraphs)
    assert word.core_properties.author == "CareerOS Local"
    assert word.core_properties.comments == "Generated locally"
    assert text.index("EXPERIENCE") < text.index("Role 0") < text.index("Role 1")
    assert word_text.index("EXPERIENCE") < word_text.index("Role 0") < word_text.index("Role 1")
    assert report["text_order_verified"] is True
    assert report["metadata_sanitized"] is True


def test_quality_gate_rejects_page_overflow(monkeypatch):
    monkeypatch.setattr(settings, "RESUME_MAX_PAGES", 1)
    snapshot = _snapshot(entry_count=24)
    pdf = render_ats_pdf(snapshot)
    docx = render_ats_docx(snapshot)
    with pytest.raises(ResumeQualityError, match="page"):
        validate_resume_artifacts(
            pdf=pdf,
            docx=docx,
            required_headings=["EXPERIENCE"],
            required_text=["Mira Vale"],
            template_kind="ats",
            expect_photo=False,
        )
