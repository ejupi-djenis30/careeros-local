"""Pure synthetic fixture builders for campaign ZIP archives and XLSX workbooks."""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime
from typing import Any


def col_to_letter(col_idx: int) -> str:
    """Convert 0-indexed column index to Excel column letters (0 -> A, 27 -> AB)."""
    result = ""
    col_idx += 1
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _date_to_excel_serial(d: date) -> int:
    """Convert Python date to Excel serial number (days since 1899-12-30)."""
    delta = d - date(1899, 12, 30)
    return delta.days


AUDITED_28_HEADERS: list[str] = [
    "Application ID", "Role Title", "Company Name", "Location", "Job Category",
    "Platform / Source", "Status", "Priority", "Platform URL", "Job Posting URL",
    "Outcome", "Date Found", "Application Date", "Follow-up Date", "Last Update",
    "Next Action", "Notes", "Contact Person", "Contact Email", "Salary Range",
    "Workplace Type", "Contract Type", "Requirements Summary", "CV Template Used",
    "Cover Letter Sent", "Referral", "Archive Reason", "Comments"
]


def build_fictional_xlsx_bytes(
    applications_rows: list[dict[str, Any]] | None = None,
    credentials_count: int = 0,
    *,
    custom_headers: list[str] | None = None,
    use_inline_strings: bool = False,
    include_credentials_sheet: bool = True,
    applications_sheet_name: str = "Applications",
    credentials_sheet_name: str = "Platform Credentials",
    use_opc_absolute_targets: bool = False,
    custom_wb_rels: list[str] | None = None,
) -> bytes:
    """Build a minimal, valid XLSX workbook using only Python standard library.

    Uses purely fictional headers and test data.
    """
    if custom_headers is not None:
        headers = custom_headers
    elif applications_rows is not None:
        seen_keys: list[str] = []
        for r in applications_rows:
            for k in r.keys():
                if k not in seen_keys:
                    seen_keys.append(k)
        headers = list(seen_keys)
        for dh in AUDITED_28_HEADERS:
            if dh not in headers and len(headers) < 28:
                headers.append(dh)
    else:
        headers = list(AUDITED_28_HEADERS)

    if applications_rows is None:
        applications_rows = [
            {
                "Application ID": "APP-001",
                "Role Title": "Software Engineer",
                "Company Name": "Acme Corp",
                "Location": "Zurich",
                "Job Category": "Engineering",
                "Platform / Source": "LinkedIn",
                "Status": "Applied",
                "Priority": "High",
                "Platform URL": "https://linkedin.com/jobs/view/1001",
                "Job Posting URL": "https://careers.acme.com/jobs/1001",
                "Date Found": date(2026, 1, 10),
                "Application Date": date(2026, 1, 12),
                "Follow-up Date": date(2026, 1, 26),
                "Last Update": date(2026, 1, 15),
                "Next Action": "Follow up with recruiter",
                "Notes": "Synthetic fictional note",
            },
            {
                "Application ID": "APP-002",
                "Role Title": "Systems Architect",
                "Company Name": "Globex Inc",
                "Location": "Remote",
                "Job Category": "Architecture",
                "Platform / Source": "Direct",
                "Status": "Closed",
                "Priority": "Medium",
                "Platform URL": "https://jobs.globex.com/platform",
                "Job Posting URL": "https://jobs.globex.com/view/2002",
                "Date Found": date(2026, 1, 5),
                "Application Date": date(2026, 1, 8),
                "Follow-up Date": date(2026, 1, 15),
                "Last Update": date(2026, 1, 20),
                "Outcome": "Position cancelled",
            },
            {
                "Application ID": "APP-003",
                "Role Title": "Frontend Developer",
                "Company Name": "Initech Ltd",
                "Location": "Geneva",
                "Job Category": "Frontend",
                "Platform / Source": "JobBoard",
                "Status": "Preparing",
                "Priority": "Low",
                "Date Found": date(2026, 2, 1),
            },
            {
                "Application ID": "APP-004",
                "Role Title": "DevOps Engineer",
                "Company Name": "Hooli",
                "Location": "Bern",
                "Job Category": "Operations",
                "Platform / Source": "Indeed",
                "Status": "Saved",
                "Priority": "Low",
                "Date Found": date(2026, 2, 5),
            },
        ]

    shared_strings: list[str] = []
    string_map: dict[str, int] = {}

    def get_shared_str_idx(s: str) -> int:
        if s not in string_map:
            string_map[s] = len(shared_strings)
            shared_strings.append(s)
        return string_map[s]

    # Build sheet1 (Applications)
    sheet1_rows_xml: list[str] = []
    # Header row at r=1
    header_cells: list[str] = []
    for c_idx, h in enumerate(headers):
        ref = f"{col_to_letter(c_idx)}1"
        if use_inline_strings:
            header_cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{h}</t></is></c>')
        else:
            idx = get_shared_str_idx(h)
            header_cells.append(f'<c r="{ref}" t="s"><v>{idx}</v></c>')
    sheet1_rows_xml.append(f'<row r="1">{"".join(header_cells)}</row>')

    # Data rows
    for r_idx, row_dict in enumerate(applications_rows, start=2):
        cells: list[str] = []
        for c_idx, h in enumerate(headers):
            ref = f"{col_to_letter(c_idx)}{r_idx}"
            val = row_dict.get(h)
            if val is None:
                continue
            if isinstance(val, (date, datetime)):
                serial = _date_to_excel_serial(val.date() if isinstance(val, datetime) else val)
                # s="1" corresponds to date style
                cells.append(f'<c r="{ref}" s="1"><v>{serial}</v></c>')
            elif isinstance(val, bool):
                cells.append(f'<c r="{ref}" t="b"><v>{1 if val else 0}</v></c>')
            elif isinstance(val, (int, float)):
                cells.append(f'<c r="{ref}"><v>{val}</v></c>')
            elif use_inline_strings:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{val}</t></is></c>')
            else:
                idx = get_shared_str_idx(str(val))
                cells.append(f'<c r="{ref}" t="s"><v>{idx}</v></c>')
        if cells:
            sheet1_rows_xml.append(f'<row r="{r_idx}">{"".join(cells)}</row>')

    sheet1_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        f'  <sheetData>{"".join(sheet1_rows_xml)}</sheetData>\n'
        '</worksheet>'
    )

    # Build sheet2 (Platform Credentials)
    sheet2_rows_xml: list[str] = []
    # Header row
    sheet2_rows_xml.append(
        '<row r="1">'
        '<c r="A1" t="inlineStr"><is><t>Platform</t></is></c>'
        '<c r="B1" t="inlineStr"><is><t>Username</t></is></c>'
        '<c r="C1" t="inlineStr"><is><t>Password</t></is></c>'
        '</row>'
    )
    for c_idx in range(credentials_count):
        r = c_idx + 2
        # Synthetic credentials data
        sheet2_rows_xml.append(
            f'<row r="{r}">'
            f'<c r="A{r}" t="inlineStr"><is><t>Platform{c_idx}</t></is></c>'
            f'<c r="B{r}" t="inlineStr"><is><t>user{c_idx}</t></is></c>'
            f'<c r="C{r}" t="inlineStr"><is><t>pass{c_idx}</t></is></c>'
            f'</row>'
        )

    sheet2_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        f'  <sheetData>{"".join(sheet2_rows_xml)}</sheetData>\n'
        '</worksheet>'
    )

    # sharedStrings.xml
    sst_items = "".join(f"<si><t>{s}</t></si>" for s in shared_strings)
    sst_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">\n'
        f"  {sst_items}\n"
        "</sst>"
    )

    # styles.xml with a date numFmt at xf id=1
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        '  <numFmts count="1">\n'
        '    <numFmt numFmtId="165" formatCode="yyyy-mm-dd"/>\n'
        '  </numFmts>\n'
        '  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>\n'
        '  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>\n'
        '  <borders count="1"><border><left/><right/><top/><bottom/></border></borders>\n'
        '  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>\n'
        '  <cellXfs count="2">\n'
        '    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>\n'
        '    <xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>\n'
        '  </cellXfs>\n'
        '</styleSheet>'
    )

    # workbook.xml
    sheets_xml = f'<sheet name="{applications_sheet_name}" sheetId="1" r:id="rId1"/>'
    if include_credentials_sheet:
        sheets_xml += f'<sheet name="{credentials_sheet_name}" sheetId="2" r:id="rId2"/>'

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
        f"  <sheets>{sheets_xml}</sheets>\n"
        "</workbook>"
    )

    # workbook.xml.rels
    if custom_wb_rels is not None:
        rels = custom_wb_rels
    else:
        prefix = "/xl/" if use_opc_absolute_targets else ""
        rels = [
            f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="{prefix}worksheets/sheet1.xml"/>'
        ]
        if include_credentials_sheet:
            rels.append(
                f'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="{prefix}worksheets/sheet2.xml"/>'
            )
        rels.append(
            f'<Relationship Id="rId{len(rels)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="{prefix}sharedStrings.xml"/>'
        )
        rels.append(
            f'<Relationship Id="rId{len(rels)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="{prefix}styles.xml"/>'
        )

    wb_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        f'  {"".join(rels)}\n'
        "</Relationships>"
    )

    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>\n'
        "</Relationships>"
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="xml" ContentType="application/xml"/>\n'
        '  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>\n'
        '  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
    )
    if include_credentials_sheet:
        content_types_xml += '  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
    content_types_xml += (
        '  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>\n'
        '  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>\n'
        '</Types>'
    )

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels_xml)
        zf.writestr("xl/styles.xml", styles_xml)
        zf.writestr("xl/sharedStrings.xml", sst_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet1_xml)
        if include_credentials_sheet:
            zf.writestr("xl/worksheets/sheet2.xml", sheet2_xml)

    return out.getvalue()


_MINIMAL_PDF_BYTES: bytes | None = None


def build_minimal_pdf_bytes() -> bytes:
    """Build a minimal valid, text-bearing PDF for source extraction tests."""
    global _MINIMAL_PDF_BYTES
    if _MINIMAL_PDF_BYTES is None:
        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        pdf = canvas.Canvas(
            buf,
            pagesize=(144, 144),
            pageCompression=0,
            invariant=1,
        )
        pdf.drawString(18, 72, "Fictional diploma evidence")
        pdf.showPage()
        pdf.save()
        _MINIMAL_PDF_BYTES = buf.getvalue()
    return _MINIMAL_PDF_BYTES


def build_fictional_campaign_zip(
    members: dict[str, bytes | str] | None = None,
    *,
    prefix: str = "",
    xlsx_bytes: bytes | None = None,
    credentials_count: int = 0,
) -> bytes:
    """Build a complete synthetic campaign ZIP archive for testing."""
    if xlsx_bytes is None:
        xlsx_bytes = build_fictional_xlsx_bytes(credentials_count=credentials_count)

    data: dict[str, bytes | str] = {
        "ApplicationTracker.xlsx": xlsx_bytes,
        "Profile.md": "# Fictional Profile\n\nExperienced Engineer with track record in distributed systems.\n",
        "Goal.md": "# Fictional Goal\n\nTargeting Senior or Staff Systems roles in Switzerland.\n",
        "Storytelling.md": "# Fictional Stories\n\nSTAR narrative on incident resolution.\n",
        "Diploma.pdf": build_minimal_pdf_bytes(),
        "assets/photo.jpg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb",
        "application-packets/APP-001/cv.pdf": b"%PDF-1.4 fictional cv bytes",
        "application-packets/APP-001/cover_letter.pdf": b"%PDF-1.4 fictional letter bytes",
        "application-packets/APP-001/vacancy.md": "# Software Engineer\n\n**Company:** Acme Corp\n**Location:** Zurich\n\nRequirements:\n- Python\n",
        "application-packets/APP-002/cv.docx": b"PK\x03\x04fictional docx bytes",
        "application-packets/dossier-only-001/vacancy.md": "# Lead Architect\n\n**Company:** Fictional Pioneer AG\n**Location:** Basel\n**Category:** Architecture\n\nArchitectural responsibilities.\n",
        "cv-templates/modern.html": "<html><body>Fictional CV Template</body></html>",
        "cover-letter-templates/standard.md": "# Cover Letter Template\n\nDear Hiring Manager,\n",
        "email-templates/follow_up.md": "Subject: Follow-up on application\n\nHi,\n",
        "html-templates/card.html": "<div>Fictional card</div>",
        "scripts/export_notes.py": "# Synthetic export script\nprint('fictional')\n",
    }
    if members:
        data.update(members)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in data.items():
            full_path = f"{prefix}{path}" if prefix else path
            payload = content.encode("utf-8") if isinstance(content, str) else content
            zf.writestr(full_path, payload)
    return out.getvalue()
