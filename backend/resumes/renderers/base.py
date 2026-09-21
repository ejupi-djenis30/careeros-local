import zipfile
from datetime import datetime, timezone
from html import escape
from io import BytesIO

from docx import Document as create_document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Mm, Pt, RGBColor
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from backend.resumes import artifact_policy
from backend.resumes.artifact_policy import (
    MAX_RESUME_ARTIFACT_BYTES,
    MAX_RESUME_DOCX_ENTRIES,
    MAX_RESUME_DOCX_UNCOMPRESSED_BYTES,
    ensure_resume_artifact_size,
)
from backend.resumes.content import ResumeContent, build_content
from backend.resumes.renderers.fonts import ensure_unicode_font_registered
from backend.resumes.renderers.links import add_docx_hyperlink, format_pdf_link, is_safe_url

_DOCX_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_DOCUMENT_TIMESTAMP = datetime(2000, 1, 1, tzinfo=timezone.utc)
DOCX_MEDIA_TYPE = artifact_policy.DOCX_MEDIA_TYPE
PDF_MEDIA_TYPE = artifact_policy.PDF_MEDIA_TYPE


def _paragraph_text(value: str) -> str:
    return escape(value).replace("\n", "<br/>")


def render_pdf(snapshot: dict, *, photo: bytes | None = None) -> bytes:
    content = build_content(snapshot)
    style = content.style
    margin = float(style.get("margin_mm", 17))
    base_size = float(style.get("base_font_size", 9))
    line_height = float(style.get("line_height", 1.3))
    spacing = float(style.get("section_spacing", 8))
    accent = str(style.get("accent_color", "#111827"))
    normal_font, bold_font, italic_font = ensure_unicode_font_registered()
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
    base_styles = getSampleStyleSheet()
    name_style = ParagraphStyle(
        "ResumeName",
        parent=base_styles["Title"],
        fontName=bold_font,
        fontSize=20,
        leading=23,
        alignment=TA_CENTER,
        spaceAfter=3,
    )
    headline_style = ParagraphStyle(
        "ResumeHeadline",
        parent=base_styles["Normal"],
        fontName=normal_font,
        fontSize=base_size + 2,
        leading=(base_size + 2) * line_height,
        alignment=TA_CENTER,
        textColor=HexColor("#30343B"),
        spaceAfter=3,
    )
    contact_style = ParagraphStyle(
        "ResumeContact",
        parent=base_styles["Normal"],
        fontName=normal_font,
        fontSize=8.5,
        leading=11,
        alignment=TA_CENTER,
        textColor=HexColor("#4B5563"),
        spaceAfter=8,
    )
    section_style = ParagraphStyle(
        "ResumeSection",
        parent=base_styles["Heading2"],
        fontName=bold_font,
        fontSize=base_size + 1,
        leading=(base_size + 1) * line_height,
        textColor=HexColor(accent),
        spaceBefore=spacing,
        spaceAfter=4,
        borderWidth=0,
        borderPadding=0,
    )
    entry_title_style = ParagraphStyle(
        "ResumeEntryTitle",
        parent=base_styles["Normal"],
        fontName=bold_font,
        fontSize=base_size + 0.5,
        leading=(base_size + 0.5) * line_height,
        spaceBefore=3,
        spaceAfter=1,
    )
    meta_style = ParagraphStyle(
        "ResumeMeta",
        parent=base_styles["Normal"],
        fontName=italic_font,
        fontSize=8.5,
        leading=11,
        textColor=HexColor("#374151"),
        spaceAfter=2,
    )
    body_style = ParagraphStyle(
        "ResumeBody",
        parent=base_styles["Normal"],
        fontName=normal_font,
        fontSize=base_size,
        leading=base_size * line_height,
        spaceAfter=2,
    )
    bullet_style = ParagraphStyle(
        "ResumeBullet",
        parent=body_style,
        leftIndent=10,
        firstLineIndent=-7,
        bulletIndent=2,
    )

    story: list[Flowable] = []
    if photo:
        image = Image(BytesIO(photo), width=28 * mm, height=28 * mm)
        image.hAlign = "CENTER"
        story.extend([image, Spacer(1, 4)])
    story.append(Paragraph(_paragraph_text(content.display_name), name_style))
    if content.headline:
        story.append(Paragraph(_paragraph_text(content.headline), headline_style))
    if content.contact_line:
        contact_parts: list[str] = []
        for item in content.contact_line.split(" | "):
            cleaned = item.strip()
            if not cleaned:
                continue
            if is_safe_url(cleaned):
                contact_parts.append(format_pdf_link(cleaned, cleaned, accent))
            else:
                contact_parts.append(_paragraph_text(cleaned))
        story.append(Paragraph(" | ".join(contact_parts), contact_style))
    if content.summary:
        story.append(Paragraph(_paragraph_text(content.summary_heading), section_style))
        story.append(Paragraph(_paragraph_text(content.summary), body_style))
    for section in content.sections:
        if section.page_break_before:
            story.append(PageBreak())
        story.append(Paragraph(_paragraph_text(section.heading), section_style))
        for entry in section.entries:
            flowables: list[Flowable] = []
            spacing_before = float(entry.layout.get("spacing_before_pt", 0))
            if spacing_before:
                flowables.append(Spacer(1, spacing_before))
            flowables.append(Paragraph(_paragraph_text(entry.title), entry_title_style))
            meta_parts: list[str] = []
            if entry.subtitle:
                for sub in entry.subtitle.split(" | "):
                    c_sub = sub.strip()
                    if is_safe_url(c_sub):
                        meta_parts.append(format_pdf_link(c_sub, c_sub, accent))
                    else:
                        meta_parts.append(_paragraph_text(c_sub))
            if entry.date_range:
                meta_parts.append(_paragraph_text(entry.date_range))
            if meta_parts:
                flowables.append(Paragraph(" | ".join(meta_parts), meta_style))
            if entry.description:
                flowables.append(Paragraph(_paragraph_text(entry.description), body_style))
            for bullet in entry.bullets:
                flowables.append(Paragraph(f"&bull;&nbsp;{_paragraph_text(bullet)}", bullet_style))
            if entry.layout.get("keep_together", True):
                story.append(KeepTogether(flowables))
            else:
                story.extend(flowables)
    document.build(story)
    return ensure_resume_artifact_size(output.getvalue(), label="PDF")


def _configure_docx(document: DocxDocument, title: str, style: dict) -> None:
    section = document.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    margin_inches = float(style.get("margin_mm", 16.5)) / 25.4
    section.top_margin = Inches(margin_inches)
    section.bottom_margin = Inches(margin_inches)
    section.left_margin = Inches(margin_inches)
    section.right_margin = Inches(margin_inches)
    normal = document.styles["Normal"]
    normal.font.name = str(style.get("font_family", "Arial"))
    normal.font.size = Pt(float(style.get("base_font_size", 9.5)))
    normal.paragraph_format.space_after = Pt(2)
    normal.paragraph_format.line_spacing = float(style.get("line_height", 1.3))
    heading = document.styles["Heading 2"]
    heading.font.name = normal.font.name
    heading.font.size = Pt(float(style.get("base_font_size", 9.5)) + 1)
    heading.font.bold = True
    heading.font.color.rgb = RGBColor.from_string(
        str(style.get("accent_color", "#111827")).lstrip("#")
    )
    heading.paragraph_format.space_before = Pt(float(style.get("section_spacing", 8)))
    heading.paragraph_format.space_after = Pt(3)
    properties = document.core_properties
    properties.title = title
    properties.author = "CareerOS Local"
    properties.subject = "Resume"
    properties.keywords = ""
    properties.comments = "Generated locally"
    properties.last_modified_by = "CareerOS Local"
    properties.created = _DOCUMENT_TIMESTAMP
    properties.modified = _DOCUMENT_TIMESTAMP
    properties.category = ""
    properties.content_status = ""
    properties.identifier = ""
    properties.language = ""
    properties.version = ""


def _canonicalize_docx(data: bytes) -> bytes:
    """Strip ZIP timestamps/extra fields and bound expansion before returning a DOCX."""

    if len(data) > MAX_RESUME_ARTIFACT_BYTES:
        raise ValueError(
            f"Generated DOCX exceeds the {MAX_RESUME_ARTIFACT_BYTES}-byte artifact limit"
        )
    output = BytesIO()
    try:
        with zipfile.ZipFile(BytesIO(data)) as source:
            entries = source.infolist()
            if len(entries) > MAX_RESUME_DOCX_ENTRIES:
                raise ValueError("Generated DOCX contains too many archive entries")
            if sum(entry.file_size for entry in entries) > MAX_RESUME_DOCX_UNCOMPRESSED_BYTES:
                raise ValueError("Generated DOCX expands beyond the local artifact limit")
            if len({entry.filename for entry in entries}) != len(entries):
                raise ValueError("Generated DOCX contains duplicate archive entries")
            with zipfile.ZipFile(
                output,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
                allowZip64=False,
            ) as target:
                for entry in entries:
                    canonical = zipfile.ZipInfo(entry.filename, date_time=_DOCX_TIMESTAMP)
                    canonical.compress_type = zipfile.ZIP_DEFLATED
                    canonical.create_system = 3
                    canonical.external_attr = (0o600 if not entry.is_dir() else 0o700) << 16
                    target.writestr(canonical, source.read(entry))
    except zipfile.BadZipFile as exc:
        raise ValueError("Generated DOCX is not a valid archive") from exc
    return ensure_resume_artifact_size(output.getvalue(), label="DOCX")


def _add_docx_heading(document: DocxDocument, text: str) -> None:
    document.add_paragraph(text, style="Heading 2")


def _add_docx_entry(document: DocxDocument, entry) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(
        max(3, float(entry.layout.get("spacing_before_pt", 0)))
    )
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.keep_with_next = True
    paragraph.paragraph_format.keep_together = bool(entry.layout.get("keep_together", True))
    run = paragraph.add_run(entry.title)
    run.bold = True
    run.font.name = "Arial"
    run.font.size = Pt(9.5)
    meta_parts = (
        [p.strip() for p in entry.subtitle.split(" | ") if p.strip()] if entry.subtitle else []
    )
    if meta_parts or entry.date_range:
        p_meta = document.add_paragraph()
        p_meta.paragraph_format.space_after = Pt(1)
        for i, part in enumerate(meta_parts):
            if is_safe_url(part):
                add_docx_hyperlink(p_meta, part, part, font_size_pt=8.5)
            else:
                r = p_meta.add_run(part)
                r.italic = True
                r.font.size = Pt(8.5)
            if i < len(meta_parts) - 1 or entry.date_range:
                sep = p_meta.add_run(" | ")
                sep.italic = True
                sep.font.size = Pt(8.5)
        if entry.date_range:
            rd = p_meta.add_run(entry.date_range)
            rd.italic = True
            rd.font.size = Pt(8.5)
    if entry.description:
        document.add_paragraph(entry.description)
    for bullet in entry.bullets:
        paragraph = document.add_paragraph(bullet, style="List Bullet")
        paragraph.paragraph_format.space_after = Pt(1)


def render_docx(snapshot: dict, *, photo: bytes | None = None) -> bytes:
    content: ResumeContent = build_content(snapshot)
    document = create_document()
    _configure_docx(document, content.display_name, content.style)
    if photo:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.add_run().add_picture(BytesIO(photo), width=Inches(1.05))
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(1)
    run = paragraph.add_run(content.display_name)
    run.bold = True
    run.font.name = "Arial"
    run.font.size = Pt(20)
    if content.headline:
        paragraph = document.add_paragraph(content.headline)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(1)
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
    for section in content.sections:
        if section.page_break_before:
            document.add_page_break()
        _add_docx_heading(document, section.heading)
        for entry in section.entries:
            _add_docx_entry(document, entry)
    output = BytesIO()
    document.save(output)
    return _canonicalize_docx(output.getvalue())
