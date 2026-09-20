from html import escape
from io import BytesIO

from docx import Document as create_document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BalancedColumns,
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from backend.resumes.artifact_policy import ensure_resume_artifact_size
from backend.resumes.content import ResumeContent, build_content
from backend.resumes.renderers.base import (
    _add_docx_entry,
    _add_docx_heading,
    _canonicalize_docx,
    _configure_docx,
)
from backend.resumes.renderers.fonts import ensure_unicode_font_registered
from backend.resumes.renderers.links import add_docx_hyperlink, format_pdf_link, is_safe_url


def _text(value: str) -> str:
    return escape(value).replace("\n", "<br/>")


def _pdf_styles(content: ResumeContent) -> dict[str, ParagraphStyle]:
    style = content.style
    base_size = float(style.get("base_font_size", 9))
    line_height = float(style.get("line_height", 1.3))
    spacing = float(style.get("section_spacing", 8))
    normal, bold, italic = ensure_unicode_font_registered()
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "PhotoBody",
        parent=base["Normal"],
        fontName=normal,
        fontSize=base_size,
        leading=base_size * line_height,
        spaceAfter=2,
    )
    return {
        "name": ParagraphStyle(
            "PhotoName",
            parent=base["Title"],
            fontName=bold,
            fontSize=20,
            leading=23,
            alignment=TA_CENTER,
            spaceAfter=3,
        ),
        "headline": ParagraphStyle(
            "PhotoHeadline",
            parent=body,
            fontSize=base_size + 2,
            leading=(base_size + 2) * line_height,
            alignment=TA_CENTER,
            textColor=HexColor("#30343B"),
        ),
        "contact": ParagraphStyle(
            "PhotoContact",
            parent=body,
            fontSize=8.5,
            leading=11,
            alignment=TA_CENTER,
            textColor=HexColor("#4B5563"),
            spaceAfter=8,
        ),
        "section": ParagraphStyle(
            "PhotoSection",
            parent=base["Heading2"],
            fontName=bold,
            fontSize=base_size + 1,
            leading=(base_size + 1) * line_height,
            textColor=HexColor(str(style.get("accent_color", "#111827"))),
            spaceBefore=spacing,
            spaceAfter=4,
        ),
        "title": ParagraphStyle(
            "PhotoEntryTitle",
            parent=body,
            fontName=bold,
            fontSize=base_size + 0.5,
            leading=(base_size + 0.5) * line_height,
            spaceBefore=3,
            spaceAfter=1,
        ),
        "meta": ParagraphStyle(
            "PhotoMeta",
            parent=body,
            fontName=italic,
            fontSize=8.5,
            leading=11,
            textColor=HexColor("#374151"),
        ),
        "body": body,
        "bullet": ParagraphStyle(
            "PhotoBullet",
            parent=body,
            leftIndent=10,
            firstLineIndent=-7,
            bulletIndent=2,
        ),
    }


def _section_flowables(
    section, styles: dict[str, ParagraphStyle], *, group_entries: bool = True
) -> list[Flowable]:
    result: list[Flowable] = [Paragraph(_text(section.heading), styles["section"])]
    for entry in section.entries:
        flowables: list[Flowable] = []
        spacing_before = float(entry.layout.get("spacing_before_pt", 0))
        if spacing_before:
            flowables.append(Spacer(1, spacing_before))
        flowables.append(Paragraph(_text(entry.title), styles["title"]))
        metadata = " | ".join(value for value in (entry.subtitle, entry.date_range) if value)
        if metadata:
            flowables.append(
                Paragraph(
                    " | ".join(format_pdf_link(part) for part in metadata.split(" | ")),
                    styles["meta"],
                )
            )
        if entry.description:
            flowables.append(Paragraph(_text(entry.description), styles["body"]))
        flowables.extend(
            Paragraph(f"&bull;&nbsp;{_text(bullet)}", styles["bullet"]) for bullet in entry.bullets
        )
        if group_entries and entry.layout.get("keep_together", True):
            result.append(KeepTogether(flowables))
        else:
            result.extend(flowables)
    return result


def render_two_column_pdf(snapshot: dict, photo: bytes | None) -> bytes:
    content = build_content(snapshot)
    margin = float(content.style.get("margin_mm", 17))
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=margin * mm,
        leftMargin=margin * mm,
        topMargin=margin * mm,
        bottomMargin=margin * mm,
        title=content.display_name,
        author="CareerOS Local",
        subject="Resume",
        creator="CareerOS Local",
        producer="CareerOS Local",
        invariant=True,
    )
    styles = _pdf_styles(content)
    story: list[Flowable] = []
    if photo:
        image = Image(BytesIO(photo), width=28 * mm, height=28 * mm)
        image.hAlign = "CENTER"
        story.extend([image, Spacer(1, 4)])
    story.append(Paragraph(_text(content.display_name), styles["name"]))
    if content.headline:
        story.append(Paragraph(_text(content.headline), styles["headline"]))
    if content.contact_line:
        accent = str(content.style.get("accent_color", "#1E3A8A"))
        parts = []
        for item in content.contact_line.split(" | "):
            cleaned = item.strip()
            if not cleaned:
                continue
            if is_safe_url(cleaned):
                parts.append(format_pdf_link(cleaned, cleaned, accent))
            else:
                parts.append(_text(cleaned))
        story.append(Paragraph(" | ".join(parts), styles["contact"]))
    if content.summary:
        story.append(Paragraph(_text(content.summary_heading), styles["section"]))
        story.append(Paragraph(_text(content.summary), styles["body"]))

    segments: list[list[Flowable]] = [[]]
    for section in content.sections:
        if section.page_break_before and segments[-1]:
            segments.append([])
        segments[-1].extend(_section_flowables(section, styles))
    for index, segment in enumerate(filter(None, segments)):
        if index:
            story.append(PageBreak())
        story.append(BalancedColumns(segment, nCols=2, innerPadding=8 * mm, endSlack=0.05))
    document.build(story)
    return ensure_resume_artifact_size(output.getvalue(), label="PDF")


def _add_header(document, content: ResumeContent, photo: bytes | None) -> None:
    if photo:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.add_run().add_picture(BytesIO(photo), width=Inches(1.05))
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(content.display_name)
    run.bold = True
    run.font.name = "Arial"
    run.font.size = Pt(20)
    if content.headline:
        paragraph = document.add_paragraph(content.headline)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if content.contact_line:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(5)
        parts = [p.strip() for p in content.contact_line.split(" | ") if p.strip()]
        for i, part in enumerate(parts):
            if is_safe_url(part):
                add_docx_hyperlink(paragraph, part, part, font_size_pt=8.5)
            else:
                r = paragraph.add_run(part)
                r.font.size = Pt(8.5)
            if i < len(parts) - 1:
                sep = paragraph.add_run(" | ")
                sep.font.size = Pt(8.5)
    if content.summary:
        _add_docx_heading(document, content.summary_heading)
        document.add_paragraph(content.summary)


def render_two_column_docx(snapshot: dict, photo: bytes | None) -> bytes:
    content = build_content(snapshot)
    document = create_document()
    _configure_docx(document, content.display_name, content.style)
    _add_header(document, content, photo)
    section = document.add_section(WD_SECTION.CONTINUOUS)
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    margin_inches = float(content.style.get("margin_mm", 15)) / 25.4
    section.top_margin = Inches(margin_inches)
    section.bottom_margin = Inches(margin_inches)
    section.left_margin = Inches(margin_inches)
    section.right_margin = Inches(margin_inches)
    columns = section._sectPr.xpath("./w:cols")[0]
    columns.set(qn("w:num"), "2")
    columns.set(qn("w:space"), "360")
    for item in content.sections:
        if item.page_break_before:
            document.add_page_break()
        _add_docx_heading(document, item.heading)
        for entry in item.entries:
            _add_docx_entry(document, entry)
    output = BytesIO()
    document.save(output)
    return _canonicalize_docx(output.getvalue())
