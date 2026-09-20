"""Security boundaries and OPC target normalization for inner XLSX archives."""

from __future__ import annotations

import re
import stat
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from typing import Final

XLSX_MAX_MEMBERS: Final = 100
XLSX_MAX_EXPANDED_BYTES: Final = 32 * 1024 * 1024  # 32 MiB
XLSX_MAX_MEMBER_BYTES: Final = 10 * 1024 * 1024    # 10 MiB


class XlsxReadError(ValueError):
    """Raised when an XLSX workbook is malformed, missing sheets, or has invalid data."""


class XlsxSecurityError(XlsxReadError):
    """Raised when an XLSX archive violates security bounds or path policies."""


def check_no_dtd_or_entity(content: bytes, path: str = "XML") -> None:
    """Reject DTD, DOCTYPE, and ENTITY declarations in XML content."""
    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)", content, re.IGNORECASE):
        raise XlsxSecurityError(f"Package member {path} contains forbidden DTD or ENTITY declaration")


def safe_read_xml(zf: zipfile.ZipFile, path: str) -> ET.Element:
    """Safely read and parse an XML package member, converting errors to XlsxReadError."""
    try:
        content = zf.read(path)
    except KeyError as exc:
        raise XlsxReadError(f"Required package member not found: {path}") from exc
    except (zipfile.BadZipFile, OSError) as exc:
        raise XlsxReadError(f"Failed to read package member: {path}") from exc

    check_no_dtd_or_entity(content, path)
    try:
        parser = ET.XMLParser()
        parser.entity.clear()
        return ET.fromstring(content, parser=parser)
    except ET.ParseError as exc:
        raise XlsxReadError(f"Package member {path} contains invalid XML") from exc


def normalize_opc_target(base_dir: str, target: str, target_mode: str | None = None) -> str:
    """Safely resolve an OPC relationship target against package base_dir."""
    if target_mode and target_mode.strip().lower() == "external":
        raise XlsxSecurityError(f"External relationship target not permitted: {target}")
    if not target or not target.strip():
        raise XlsxSecurityError("Relationship target is empty")
    cleaned = target.strip()
    if any(unicodedata.category(c).startswith("C") for c in cleaned):
        raise XlsxSecurityError(f"Relationship target contains control characters: {cleaned!r}")
    if "\\" in cleaned:
        raise XlsxSecurityError(f"Relationship target contains backslash: {cleaned}")
    if ":" in cleaned or cleaned.startswith("//") or cleaned.startswith("\\\\") or "://" in cleaned:
        raise XlsxSecurityError(f"Relationship target contains drive/UNC/URL prefix: {cleaned}")

    norm_path = cleaned.lstrip("/") if cleaned.startswith("/") else f"{base_dir}/{cleaned}"
    parts: list[str] = []
    for segment in norm_path.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            raise XlsxSecurityError(f"Relationship target contains traversal: {cleaned}")
        parts.append(segment)
    if not parts:
        raise XlsxSecurityError("Resolved relationship target is empty")
    return "/".join(parts)


def _is_symlink_or_special(zinfo: zipfile.ZipInfo) -> bool:
    mode = (zinfo.external_attr >> 16) & 0o170000
    return mode in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFSOCK)


def validate_xlsx_archive_security(zf: zipfile.ZipFile) -> None:
    """Validate archive-level limits and entry policies for an XLSX ZIP package."""
    infolist = zf.infolist()
    if len(infolist) > XLSX_MAX_MEMBERS:
        raise XlsxSecurityError(f"XLSX exceeds members limit of {XLSX_MAX_MEMBERS}")

    total_expanded = 0
    seen_canonical: set[str] = set()

    for zinfo in infolist:
        if zinfo.flag_bits & 0x1:
            raise XlsxSecurityError(f"XLSX contains encrypted entry: {zinfo.filename}")
        if _is_symlink_or_special(zinfo):
            raise XlsxSecurityError(f"XLSX contains symlink or special file: {zinfo.filename}")

        orig_name = getattr(zinfo, "orig_filename", zinfo.filename)
        names_to_check = {zinfo.filename, orig_name}
        for name in names_to_check:
            if any(unicodedata.category(c).startswith("C") for c in name):
                raise XlsxSecurityError(f"XLSX entry contains control characters: {name!r}")
            if "\\" in name:
                raise XlsxSecurityError(f"XLSX entry contains backslash: {name}")
            if ":" in name or name.startswith("//") or name.startswith("\\\\"):
                raise XlsxSecurityError(f"XLSX entry contains drive or UNC prefix: {name}")
            if name.startswith("/"):
                raise XlsxSecurityError(f"XLSX entry contains absolute path: {name}")
            parts = [p for p in name.split("/") if p]
            if ".." in parts or "." in parts:
                raise XlsxSecurityError(f"XLSX entry contains traversal: {name}")

        cleaned = "/".join(p for p in zinfo.filename.split("/") if p)
        if not cleaned:
            continue

        canonical_key = unicodedata.normalize("NFC", cleaned).casefold()
        if canonical_key in seen_canonical:
            raise XlsxSecurityError(f"XLSX contains duplicate entry: {cleaned}")
        seen_canonical.add(canonical_key)

        if zinfo.file_size > XLSX_MAX_MEMBER_BYTES:
            raise XlsxSecurityError(f"XLSX entry {cleaned} exceeds size limit of {XLSX_MAX_MEMBER_BYTES}")

        total_expanded += zinfo.file_size
        if total_expanded > XLSX_MAX_EXPANDED_BYTES:
            raise XlsxSecurityError(f"XLSX exceeds expanded limit of {XLSX_MAX_EXPANDED_BYTES}")
