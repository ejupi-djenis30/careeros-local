"""Low-level cell value decoding and styling for XLSX reading."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from backend.campaigns.xlsx_security import XlsxReadError, safe_read_xml

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
EXCEL_BASE_DATE = date(1899, 12, 30)


def col_idx(ref: str) -> int:
    idx = 0
    for char in "".join(c for c in ref if c.isalpha()).upper():
        idx = idx * 26 + (ord(char) - ord("A") + 1)
    return idx - 1


def parse_date_styles(zf: Any, path: str | None) -> set[int]:
    if not path or path not in zf.namelist():
        return set()
    root = safe_read_xml(zf, path)
    builtin_date_ids = {14, 15, 16, 17, 18, 19, 20, 21, 22, 27, 30, 36, 45, 46, 47, 50, 57, 58}
    custom_date_ids: set[int] = set()
    for num_fmt in root.iter(f"{{{MAIN_NS}}}numFmt"):
        fmt_id = int(num_fmt.attrib.get("numFmtId", 0))
        code = re.sub(r'\[[^\]]*\]', '', num_fmt.attrib.get("formatCode", "").lower())
        if any(token in code for token in ("yy", "mm", "dd", "hh", "ss")):
            custom_date_ids.add(fmt_id)

    all_date_ids = builtin_date_ids | custom_date_ids
    date_style_indices: set[int] = set()
    cell_xfs = root.find(f"{{{MAIN_NS}}}cellXfs")
    if cell_xfs is not None:
        for idx, xf in enumerate(cell_xfs.iter(f"{{{MAIN_NS}}}xf")):
            if int(xf.attrib.get("numFmtId", 0)) in all_date_ids:
                date_style_indices.add(idx)
    return date_style_indices


def parse_cell_value(c_elem: ET.Element, shared: dict[int, str] | None, date_styles: set[int]) -> Any:
    cell_type = c_elem.attrib.get("t")
    style_idx = int(c_elem.attrib.get("s", 0)) if "s" in c_elem.attrib else None
    v_elem = c_elem.find(f"{{{MAIN_NS}}}v")
    val_text = v_elem.text if v_elem is not None else None

    if cell_type == "s":
        if shared is None:
            raise XlsxReadError("Workbook contains shared-string cells but sharedStrings part is absent")
        if val_text is None or not val_text.strip():
            raise XlsxReadError("Shared-string cell has missing index value")
        try:
            idx = int(val_text.strip())
        except ValueError as exc:
            raise XlsxReadError(f"Malformed shared-string index: {val_text}") from exc
        if idx < 0:
            raise XlsxReadError(f"Negative shared-string index: {idx}")
        if idx not in shared:
            raise XlsxReadError(f"Shared-string index out of range: {idx}")
        return shared[idx]
    if cell_type == "inlineStr":
        is_elem = c_elem.find(f"{{{MAIN_NS}}}is")
        return "".join(t.text or "" for t in is_elem.iter(f"{{{MAIN_NS}}}t")) if is_elem is not None else ""
    if cell_type == "b" and val_text is not None:
        return val_text in ("1", "true", "TRUE")
    if cell_type in ("str", "e") and val_text is not None:
        return val_text
    if val_text is not None:
        try:
            num = float(val_text)
            if style_idx is not None and style_idx in date_styles:
                return EXCEL_BASE_DATE + timedelta(days=int(num))
            return int(num) if num.is_integer() else num
        except ValueError:
            return val_text
    return None


def coerce_date(val: Any) -> date | None:
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str) and val.strip():
        try:
            return date.fromisoformat(val.strip().split("T")[0])
        except ValueError:
            return None
    return None


def coerce_text(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, str):
        return val if val.strip() else None
    return str(val)




def json_safe_val(val: Any) -> Any:
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return val


def clean_header_key(k: str) -> str:
    return re.sub(r"[_\s\-/]+", "", k.lower().strip())


def find_field(record: Mapping[str, Any], candidates: tuple[str, ...]) -> Any:
    lookup = {clean_header_key(k): v for k, v in record.items()}
    for cand in candidates:
        cleaned = clean_header_key(cand)
        if cleaned in lookup:
            val = lookup[cleaned]
            if val is not None and (not isinstance(val, str) or val.strip()):
                return val
    return None


def read_sheet_grid(root: ET.Element, shared: dict[int, str] | None, dates: set[int]) -> list[dict[int, Any]]:
    rows: list[dict[int, Any]] = []
    for row_elem in root.iter(f"{{{MAIN_NS}}}row"):
        row_dict: dict[int, Any] = {}
        for c_elem in row_elem.iter(f"{{{MAIN_NS}}}c"):
            ref = c_elem.attrib.get("r")
            if ref:
                val = parse_cell_value(c_elem, shared, dates)
                if val is not None and (not isinstance(val, str) or val.strip()):
                    row_dict[col_idx(ref)] = val
        if row_dict:
            rows.append(row_dict)
    return rows
