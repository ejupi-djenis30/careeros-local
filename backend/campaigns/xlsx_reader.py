"""Standard-library XLSX workbook reader for Applications and Credentials sheets."""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any, Mapping

from backend.campaigns.xlsx_cells import (
    clean_header_key,
    coerce_date,
    coerce_text,
    find_field,
    json_safe_val,
    parse_date_styles,
    read_sheet_grid,
)
from backend.campaigns.xlsx_security import (
    XlsxReadError,
    XlsxSecurityError,
    normalize_opc_target,
    safe_read_xml,
    validate_xlsx_archive_security,
)
from backend.campaigns.xlsx_stream import (
    CredentialRowProbe,
    parse_shared_strings_stream,
    scan_credentials_worksheet_stream,
)

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

ACCEPTED_ID_ALIASES = frozenset({
    "applicationid",
    "sourceapplicationid",
    "id",
    "appid",
    "codice",
})


@dataclass(frozen=True, slots=True)
class TrackerApplicationRow:
    source_application_id: str
    title: str
    company: str
    location: str | None
    status: str | None
    priority: str | None
    platform: str | None
    category: str | None
    outcome: str | None
    found_at: date | None
    applied_at: date | None
    follow_up_at: date | None
    last_update_at: date | None
    next_action: str | None
    notes: str | None
    platform_url: str | None
    job_posting_url: str | None
    url: str | None
    raw_record: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class WorkbookReadResult:
    rows: tuple[TrackerApplicationRow, ...] = ()
    credentials_count: int = 0
    headers: tuple[str, ...] = ()


def _collect_shared_indices(root: ET.Element) -> set[int]:
    indices: set[int] = set()
    for c_elem in root.iter(f"{{{MAIN_NS}}}c"):
        if c_elem.attrib.get("t") == "s":
            v_elem = c_elem.find(f"{{{MAIN_NS}}}v")
            if v_elem is not None and v_elem.text and v_elem.text.strip():
                try:
                    indices.add(int(v_elem.text.strip()))
                except ValueError as exc:
                    raise XlsxReadError(f"Malformed shared-string index: {v_elem.text.strip()}") from exc
    return indices


def read_campaign_workbook(data: bytes) -> WorkbookReadResult:
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            validate_xlsx_archive_security(zf)

            wb_root = safe_read_xml(zf, "xl/workbook.xml")
            rels_root = safe_read_xml(zf, "xl/_rels/workbook.xml.rels")

            rel_map: dict[str, str] = {}
            declared_shared: str | None = None
            declared_styles: str | None = None

            for rel in rels_root.iter(f"{{{PKG_REL_NS}}}Relationship"):
                rid = rel.attrib.get("Id")
                target_raw = rel.attrib.get("Target", "")
                target_mode = rel.attrib.get("TargetMode")
                rel_type = rel.attrib.get("Type", "")
                if rid:
                    try:
                        normalized = normalize_opc_target("xl", target_raw, target_mode)
                    except XlsxSecurityError as exc:
                        raise XlsxReadError(str(exc)) from exc
                    rel_map[rid] = normalized
                    if rel_type.endswith("/sharedStrings"):
                        declared_shared = normalized
                    elif rel_type.endswith("/styles"):
                        declared_styles = normalized

            if declared_shared and declared_shared not in zf.namelist():
                raise XlsxReadError(f"Declared sharedStrings member not found in package: {declared_shared}")
            if declared_styles and declared_styles not in zf.namelist():
                raise XlsxReadError(f"Declared styles member not found in package: {declared_styles}")

            shared_path = declared_shared or ("xl/sharedStrings.xml" if "xl/sharedStrings.xml" in zf.namelist() else None)
            styles_path = declared_styles or ("xl/styles.xml" if "xl/styles.xml" in zf.namelist() else None)

            app_sheet_path: str | None = None
            cred_sheet_path: str | None = None

            for sheet in wb_root.iter(f"{{{MAIN_NS}}}sheet"):
                name_raw = sheet.attrib.get("name", "").strip()
                name_lower = name_raw.lower()
                rid = sheet.attrib.get(f"{{{REL_NS}}}id")
                is_app = name_lower == "applications"
                is_cred = "credential" in name_lower

                if is_app or is_cred:
                    if not rid:
                        raise XlsxReadError(f"Sheet '{name_raw}' is missing relationship ID")
                    if rid not in rel_map:
                        raise XlsxReadError(f"Sheet '{name_raw}' references missing relationship: {rid}")
                    target = rel_map[rid]
                    if target not in zf.namelist():
                        raise XlsxReadError(f"Package member for sheet '{name_raw}' not found: {target}")
                    if is_app:
                        app_sheet_path = target
                    else:
                        cred_sheet_path = target

            if not app_sheet_path:
                raise XlsxReadError("Applications sheet not found in workbook")

            app_root = safe_read_xml(zf, app_sheet_path)
            app_indices = _collect_shared_indices(app_root)

            row_probes: list[CredentialRowProbe] = []
            cred_indices: set[int] = set()
            if cred_sheet_path:
                cred_bytes = zf.read(cred_sheet_path)
                row_probes = scan_credentials_worksheet_stream(cred_bytes, cred_sheet_path)
                cred_indices = {idx for probe in row_probes for idx in probe.shared_indices}

            if app_indices and not shared_path:
                raise XlsxReadError("Workbook contains shared-string cells but sharedStrings part is absent")
            if cred_indices and not shared_path:
                raise XlsxReadError("Credentials sheet contains shared-string cells but sharedStrings part is absent")

            app_strings: dict[int, str] | None = None
            cred_non_empty: dict[int, bool] = {}
            if shared_path:
                sst_bytes = zf.read(shared_path)
                app_strings, cred_non_empty, total_sst = parse_shared_strings_stream(
                    sst_bytes, app_indices, cred_indices, shared_path
                )
                for idx in cred_indices:
                    if idx < 0 or idx >= total_sst:
                        raise XlsxReadError(f"Shared-string index out of range in credentials sheet: {idx}")

            date_styles = parse_date_styles(zf, styles_path)
            grid = read_sheet_grid(app_root, app_strings, date_styles)

            if not grid:
                raise XlsxReadError("Applications sheet contains no rows")

            header_row_idx = 0
            headers: dict[int, str] = {}
            for idx, row in enumerate(grid[:10]):
                str_vals = [str(v).strip() for v in row.values() if isinstance(v, str)]
                has_id_alias = any(clean_header_key(v) in ACCEPTED_ID_ALIASES for v in str_vals)
                if has_id_alias and len(str_vals) >= 3:
                    header_row_idx = idx
                    headers = {col: str(val).strip() for col, val in row.items()}
                    break

            if not headers:
                raise XlsxReadError("Applications sheet header row not found")

            cleaned_headers = [clean_header_key(h) for h in headers.values()]
            if len(cleaned_headers) != len(set(cleaned_headers)):
                raise XlsxReadError("Duplicate header columns in Applications sheet")

            seen_ids: set[str] = set()
            result_rows: list[TrackerApplicationRow] = []

            for row in grid[header_row_idx + 1 :]:
                raw_record = MappingProxyType({h_name: json_safe_val(row.get(col)) for col, h_name in headers.items()})
                raw_id = find_field(raw_record, tuple(ACCEPTED_ID_ALIASES))
                app_id = str(raw_id).strip() if raw_id is not None else ""
                if not app_id:
                    raise XlsxReadError("Applications row is missing source application ID")
                if app_id in seen_ids:
                    raise XlsxReadError(f"Duplicate source application ID: {app_id}")
                seen_ids.add(app_id)

                raw_platform_url = find_field(raw_record, ("platform url", "source url"))
                platform_url = (
                    str(raw_platform_url).strip()
                    if raw_platform_url is not None and str(raw_platform_url).strip()
                    else None
                )

                raw_job_url = find_field(raw_record, ("job posting url", "job url", "posting url"))
                job_posting_url = (
                    str(raw_job_url).strip()
                    if raw_job_url is not None and str(raw_job_url).strip()
                    else None
                )

                raw_generic_url = find_field(raw_record, ("application url", "url", "link"))
                generic_url = (
                    str(raw_generic_url).strip()
                    if raw_generic_url is not None and str(raw_generic_url).strip()
                    else None
                )

                preferred_url = job_posting_url or platform_url or generic_url

                result_rows.append(
                    TrackerApplicationRow(
                        source_application_id=app_id,
                        title=coerce_text(find_field(raw_record, ("role title", "job title", "role", "title"))) or "Untitled role",
                        company=coerce_text(find_field(raw_record, ("company name", "company", "employer"))) or "Unknown company",
                        location=coerce_text(find_field(raw_record, ("location", "workplace location", "city"))),
                        status=coerce_text(find_field(raw_record, ("status", "source status", "stage"))),
                        priority=coerce_text(find_field(raw_record, ("priority",))),
                        platform=coerce_text(
                            find_field(
                                raw_record,
                                ("platform / source", "platform source", "source platform", "platform", "source"),
                            )
                        ),
                        category=coerce_text(find_field(raw_record, ("job category", "category"))),
                        outcome=coerce_text(find_field(raw_record, ("outcome", "result"))),
                        found_at=coerce_date(find_field(raw_record, ("date found", "found date", "found at"))),
                        applied_at=coerce_date(
                            find_field(raw_record, ("application date", "applied date", "date applied", "applied at"))
                        ),
                        follow_up_at=coerce_date(
                            find_field(
                                raw_record,
                                ("follow-up date", "follow up date", "followup date", "next follow up", "follow up"),
                            )
                        ),
                        last_update_at=coerce_date(
                            find_field(raw_record, ("last update", "last update date", "updated at", "last updated"))
                        ),
                        next_action=coerce_text(find_field(raw_record, ("next action", "action"))),
                        notes=coerce_text(find_field(raw_record, ("notes", "note", "comments"))),
                        platform_url=platform_url,
                        job_posting_url=job_posting_url,
                        url=preferred_url,
                        raw_record=raw_record,
                    )
                )

            credentials_count = 0
            if row_probes:
                first_row = True
                for probe in row_probes:
                    if probe.is_non_empty(cred_non_empty):
                        if first_row:
                            first_row = False
                        else:
                            credentials_count += 1

            ordered_headers = tuple(headers[col] for col in sorted(headers.keys()))
            return WorkbookReadResult(
                rows=tuple(result_rows),
                credentials_count=credentials_count,
                headers=ordered_headers,
            )
    except (zipfile.BadZipFile, OSError) as exc:
        raise XlsxReadError("Invalid XLSX archive") from exc
    except XlsxSecurityError as exc:
        raise XlsxReadError(str(exc)) from exc
