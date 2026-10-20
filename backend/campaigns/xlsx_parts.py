"""Resolve worksheet and metadata parts in an already validated XLSX package."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable

from backend.campaigns.xlsx_security import XlsxReadError, XlsxSecurityError


def resolve_workbook_parts(
    zf: zipfile.ZipFile,
    wb_root: ET.Element,
    rels_root: ET.Element,
    *,
    main_ns: str,
    rel_ns: str,
    pkg_rel_ns: str,
    normalize_target: Callable[[str, str, str | None], str],
) -> tuple[str | None, str | None, str, str | None]:
    rel_map: dict[str, str] = {}
    declared_shared: str | None = None
    declared_styles: str | None = None

    for rel in rels_root.iter(f"{{{pkg_rel_ns}}}Relationship"):
        rid = rel.attrib.get("Id")
        target_raw = rel.attrib.get("Target", "")
        target_mode = rel.attrib.get("TargetMode")
        rel_type = rel.attrib.get("Type", "")
        if rid:
            try:
                normalized = normalize_target("xl", target_raw, target_mode)
            except XlsxSecurityError as exc:
                raise XlsxReadError(str(exc)) from exc
            rel_map[rid] = normalized
            if rel_type.endswith("/sharedStrings"):
                declared_shared = normalized
            elif rel_type.endswith("/styles"):
                declared_styles = normalized

    if declared_shared and declared_shared not in zf.namelist():
        raise XlsxReadError(
            f"Declared sharedStrings member not found in package: {declared_shared}"
        )
    if declared_styles and declared_styles not in zf.namelist():
        raise XlsxReadError(f"Declared styles member not found in package: {declared_styles}")

    shared_path = declared_shared or (
        "xl/sharedStrings.xml" if "xl/sharedStrings.xml" in zf.namelist() else None
    )
    styles_path = declared_styles or ("xl/styles.xml" if "xl/styles.xml" in zf.namelist() else None)

    app_sheet_path: str | None = None
    cred_sheet_path: str | None = None

    for sheet in wb_root.iter(f"{{{main_ns}}}sheet"):
        name_raw = sheet.attrib.get("name", "").strip()
        name_lower = name_raw.lower()
        rid = sheet.attrib.get(f"{{{rel_ns}}}id")
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
    return shared_path, styles_path, app_sheet_path, cred_sheet_path
