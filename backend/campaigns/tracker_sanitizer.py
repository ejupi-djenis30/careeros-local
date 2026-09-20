"""Deterministic, minimal, credentials-free XLSX sanitizer for ApplicationTracker.

Constructs an Applications-only XLSX package with:
- Exact original ordered Applications headers and rows.
- Inline strings only (`t="inlineStr"`), with no sharedStrings part.
- No Platform Credentials worksheet, relationships, or content.
- Fixed ZIP timestamps and canonical member ordering for 100% byte determinism.
- Parseable by `read_campaign_workbook` with `credentials_count=0`.
"""

from __future__ import annotations

import html
import io
import math
import zipfile
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from backend.campaigns.xlsx_reader import TrackerApplicationRow

FIXED_ZIP_TIMESTAMP: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)
EXCEL_BASE_DATE: date = date(1899, 12, 30)


def col_to_letter(col_idx: int) -> str:
    """Convert 0-indexed column index to Excel column letters (0 -> A, 27 -> AB)."""
    result = ""
    col_idx += 1
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _date_to_excel_serial(d: date) -> int:
    """Convert Python date to Excel serial days (days since 1899-12-30)."""
    return (d - EXCEL_BASE_DATE).days


def _format_inline_str(val: str) -> str:
    """Format inline string XML element, emitting xml:space='preserve' when needed."""
    escaped = html.escape(val, quote=True)
    if val != val.strip():
        return f'<is><t xml:space="preserve">{escaped}</t></is>'
    return f'<is><t>{escaped}</t></is>'


def sanitize_tracker_workbook(
    headers: Sequence[str],
    rows: Sequence[TrackerApplicationRow | Mapping[str, Any]],
) -> bytes:
    """Produce a deterministic, credentials-free Applications-only XLSX package."""
    effective_headers = list(headers)
    if not effective_headers and rows:
        first = rows[0]
        if isinstance(first, TrackerApplicationRow):
            effective_headers = list(first.raw_record.keys())
        elif isinstance(first, Mapping):
            effective_headers = list(first.keys())

    # Build sheet1 (Applications) header row
    header_cells: list[str] = []
    for c_idx, h in enumerate(effective_headers):
        ref = f"{col_to_letter(c_idx)}1"
        header_cells.append(f'<c r="{ref}" t="inlineStr">{_format_inline_str(str(h))}</c>')
    sheet1_rows: list[str] = [f'<row r="1">{"".join(header_cells)}</row>']

    # Build data rows
    for r_idx, row_item in enumerate(rows, start=2):
        record: Mapping[str, Any]
        if isinstance(row_item, TrackerApplicationRow):
            record = row_item.raw_record
        elif isinstance(row_item, Mapping):
            record = row_item
        else:
            record = {}
        cells: list[str] = []
        for c_idx, h in enumerate(effective_headers):
            val = record.get(h)
            if val is None:
                continue
            ref = f"{col_to_letter(c_idx)}{r_idx}"
            if isinstance(val, bool):
                cells.append(f'<c r="{ref}" t="b"><v>{1 if val else 0}</v></c>')
            elif isinstance(val, int):
                cells.append(f'<c r="{ref}"><v>{val}</v></c>')
            elif isinstance(val, float):
                if not math.isfinite(val):
                    raise ValueError(f"Non-finite float value {val} cannot be sanitized in cell {ref}")
                cells.append(f'<c r="{ref}"><v>{val}</v></c>')
            elif isinstance(val, (date, datetime)):
                d_val = val.date() if isinstance(val, datetime) else val
                serial = _date_to_excel_serial(d_val)
                cells.append(f'<c r="{ref}" s="1"><v>{serial}</v></c>')
            elif isinstance(val, str):
                if not val.strip():
                    continue
                cells.append(f'<c r="{ref}" t="inlineStr">{_format_inline_str(val)}</c>')
            else:
                s_val = str(val)
                if not s_val.strip():
                    continue
                cells.append(f'<c r="{ref}" t="inlineStr">{_format_inline_str(s_val)}</c>')
        if cells:
            sheet1_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')

    sheet1_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        f'  <sheetData>{"".join(sheet1_rows)}</sheetData>\n'
        "</worksheet>"
    )

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        '  <cellXfs count="2">\n'
        '    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>\n'
        '    <xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>\n'
        '  </cellXfs>\n'
        "</styleSheet>"
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
        '  <sheets><sheet name="Applications" sheetId="1" r:id="rId1"/></sheets>\n'
        "</workbook>"
    )

    wb_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>\n'
        '  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>\n'
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
        '  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>\n'
        "</Types>"
    )

    members: list[tuple[str, bytes]] = [
        ("[Content_Types].xml", content_types_xml.encode("utf-8")),
        ("_rels/.rels", root_rels_xml.encode("utf-8")),
        ("xl/_rels/workbook.xml.rels", wb_rels_xml.encode("utf-8")),
        ("xl/styles.xml", styles_xml.encode("utf-8")),
        ("xl/workbook.xml", workbook_xml.encode("utf-8")),
        ("xl/worksheets/sheet1.xml", sheet1_xml.encode("utf-8")),
    ]
    members.sort(key=lambda m: m[0])

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zinfo = zipfile.ZipInfo(filename=name, date_time=FIXED_ZIP_TIMESTAMP)
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zinfo.external_attr = 0o644 << 16
            zinfo.create_system = 0
            zf.writestr(zinfo, data)

    return out.getvalue()
