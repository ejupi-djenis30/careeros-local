"""Deterministic local campaign ZIP archive builder (FR-002, C050)."""

from __future__ import annotations

import hashlib
import io
import os
import stat
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import backend.campaigns.archive_policy as policy
from backend.campaigns.archive_policy import inspect_and_validate_campaign_archive

MAX_COMPRESSED_BYTES: int = policy.MAX_COMPRESSED_BYTES
MAX_EXPANDED_BYTES: int = policy.MAX_EXPANDED_BYTES
MAX_MEMBERS: int = policy.MAX_MEMBERS
MAX_FILE_BYTES: int = policy.MAX_FILE_BYTES

ALLOWED_ROOT_FILES: Final = policy.ALLOWED_ROOT_FILES
ALLOWED_ROOT_DIRECTORIES: Final = policy.ALLOWED_ROOT_DIRECTORIES
REPARSE_POINT_ATTR: Final[int] = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)


class CampaignArchiveBuildError(ValueError):
    """Raised when campaign archive construction fails boundaries or policy limits."""


@dataclass(frozen=True, slots=True)
class CampaignArchiveBuildResult:
    archive_sha256: str
    member_count: int
    source_fingerprint: str
    total_byte_size: int


def _is_link_junction_or_reparse(path: Path) -> bool:
    """Detect symlinks, junctions, or reparse points without following them."""
    try:
        if path.is_symlink():
            return True
        if hasattr(path, "is_junction") and path.is_junction():
            return True
        st = path.lstat()
        if stat.S_ISLNK(st.st_mode):
            return True
        attrs = getattr(st, "st_file_attributes", 0)
        if attrs & REPARSE_POINT_ATTR:
            return True
        return False
    except FileNotFoundError:
        return False
    except OSError:
        return True


def build_campaign_archive(
    source_dir: Path | str,
    output_zip: Path | str,
) -> CampaignArchiveBuildResult:
    """Build a deterministic allowlist-only campaign archive from a source directory."""
    source_raw = Path(source_dir)
    output_raw = Path(output_zip)

    if _is_link_junction_or_reparse(source_raw):
        raise CampaignArchiveBuildError("Source directory cannot be a symlink, junction, or reparse point")

    if _is_link_junction_or_reparse(output_raw):
        raise CampaignArchiveBuildError("Output target cannot be a symlink, junction, or reparse point")

    try:
        source_path = source_raw.resolve()
    except OSError as exc:
        raise CampaignArchiveBuildError(f"Cannot resolve source directory: {exc}") from exc

    try:
        output_path = output_raw.resolve()
    except OSError as exc:
        raise CampaignArchiveBuildError(f"Cannot resolve output path: {exc}") from exc

    if not source_path.is_dir():
        raise CampaignArchiveBuildError("Source must be an existing directory")

    if output_path == source_path or output_path.is_relative_to(source_path):
        raise CampaignArchiveBuildError("Output ZIP cannot be inside source tree")

    candidates: list[tuple[str, Path]] = []
    seen_casefold: dict[str, str] = {}

    try:
        root_entries = sorted(source_path.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        raise CampaignArchiveBuildError(f"Cannot read source directory: {exc}") from exc

    def _on_walk_error(err: OSError) -> None:
        raise CampaignArchiveBuildError(f"Directory traversal error: {err}") from err

    for entry in root_entries:
        rel_name = entry.name
        is_allowed_file = rel_name in ALLOWED_ROOT_FILES or rel_name.lower().endswith(".pdf")
        is_allowed_dir = rel_name in ALLOWED_ROOT_DIRECTORIES

        if not (is_allowed_file or is_allowed_dir):
            continue

        if _is_link_junction_or_reparse(entry):
            raise CampaignArchiveBuildError(f"Root entry cannot be link, junction, or reparse point: {rel_name}")

        try:
            st = entry.lstat()
        except OSError as exc:
            raise CampaignArchiveBuildError(f"Cannot inspect root entry {rel_name}: {exc}") from exc

        if is_allowed_file and stat.S_ISREG(st.st_mode):
            if not unicodedata.is_normalized("NFC", rel_name):
                raise CampaignArchiveBuildError(f"Filename is not NFC normalized: {rel_name}")
            cf_key = unicodedata.normalize("NFC", rel_name).casefold()
            if cf_key in seen_casefold:
                raise CampaignArchiveBuildError(f"Duplicate path collision: {rel_name}")
            seen_casefold[cf_key] = rel_name
            candidates.append((rel_name, entry))

        elif is_allowed_dir and stat.S_ISDIR(st.st_mode):
            try:
                for dirpath, dirnames, filenames in entry.walk(
                    top_down=True, on_error=_on_walk_error, follow_symlinks=False
                ):
                    for d in dirnames:
                        subdir = dirpath / d
                        if _is_link_junction_or_reparse(subdir):
                            raise CampaignArchiveBuildError(
                                f"Directory cannot be link, junction, or reparse point: {subdir}"
                            )

                    for f in filenames:
                        file_path = dirpath / f
                        if _is_link_junction_or_reparse(file_path):
                            raise CampaignArchiveBuildError(
                                f"File cannot be link, junction, or reparse point: {file_path}"
                            )
                        try:
                            fst = file_path.lstat()
                        except OSError as exc:
                            raise CampaignArchiveBuildError(f"Cannot inspect file {file_path}: {exc}") from exc
                        if not stat.S_ISREG(fst.st_mode):
                            raise CampaignArchiveBuildError(f"Special files are not permitted: {file_path}")

                        rel_path = file_path.relative_to(source_path).as_posix()
                        if "\\" in rel_path or rel_path.startswith("/") or ":" in rel_path:
                            raise CampaignArchiveBuildError(f"Invalid path syntax: {rel_path}")
                        if any(part in ("..", ".") for part in rel_path.split("/")):
                            raise CampaignArchiveBuildError(f"Path contains traversal: {rel_path}")
                        if not unicodedata.is_normalized("NFC", rel_path):
                            raise CampaignArchiveBuildError(f"Path is not NFC normalized: {rel_path}")

                        cf_key = unicodedata.normalize("NFC", rel_path).casefold()
                        if cf_key in seen_casefold:
                            raise CampaignArchiveBuildError(f"Duplicate path collision: {rel_path}")
                        seen_casefold[cf_key] = rel_path
                        candidates.append((rel_path, file_path))
            except OSError as exc:
                raise CampaignArchiveBuildError(f"Directory traversal failed: {exc}") from exc
        else:
            raise CampaignArchiveBuildError(f"Entry {rel_name} is not a regular file or directory")

    if not candidates:
        raise CampaignArchiveBuildError("No allowlisted files found in source directory")

    if len(candidates) > MAX_MEMBERS:
        raise CampaignArchiveBuildError(f"Member count exceeds limit of {MAX_MEMBERS}")

    candidates.sort(key=lambda item: item[0])

    total_expanded = 0
    member_contents: list[tuple[str, bytes]] = []

    for rel_path, file_path in candidates:
        st = file_path.lstat()
        if st.st_size > MAX_FILE_BYTES:
            raise CampaignArchiveBuildError(f"File exceeds limit of {MAX_FILE_BYTES} bytes: {rel_path}")
        total_expanded += st.st_size
        if total_expanded > MAX_EXPANDED_BYTES:
            raise CampaignArchiveBuildError(f"Expanded size exceeds limit of {MAX_EXPANDED_BYTES} bytes")

        try:
            content = file_path.read_bytes()
        except OSError as exc:
            raise CampaignArchiveBuildError(f"Failed to read file {rel_path}: {exc}") from exc

        if len(content) > MAX_FILE_BYTES:
            raise CampaignArchiveBuildError(f"File exceeds limit of {MAX_FILE_BYTES} bytes: {rel_path}")
        if len(content) != st.st_size:
            total_expanded = total_expanded - st.st_size + len(content)
            if total_expanded > MAX_EXPANDED_BYTES:
                raise CampaignArchiveBuildError(f"Expanded size exceeds limit of {MAX_EXPANDED_BYTES} bytes")

        member_contents.append((rel_path, content))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.comment = b""
        for rel_path, content in member_contents:
            zinfo = zipfile.ZipInfo(rel_path, date_time=(1980, 1, 1, 0, 0, 0))
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zinfo.comment = b""
            zinfo.extra = b""
            zinfo.create_system = 0
            zinfo.external_attr = 0o644 << 16
            zf.writestr(zinfo, content)

    zip_bytes = buf.getvalue()
    if len(zip_bytes) > MAX_COMPRESSED_BYTES:
        raise CampaignArchiveBuildError(f"Compressed size exceeds limit of {MAX_COMPRESSED_BYTES} bytes")

    try:
        inspected = inspect_and_validate_campaign_archive(zip_bytes)
    except Exception as exc:
        raise CampaignArchiveBuildError(f"Archive reparse validation failed: {exc}") from exc

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CampaignArchiveBuildError(f"Cannot create output directory: {exc}") from exc

    temp_file = output_path.with_name(f".tmp_{output_path.name}_{uuid.uuid4().hex}")
    try:
        temp_file.write_bytes(zip_bytes)
        os.replace(temp_file, output_path)
    except OSError as exc:
        raise CampaignArchiveBuildError(f"Failed to write output ZIP: {exc}") from exc
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass

    archive_sha256 = hashlib.sha256(zip_bytes).hexdigest()
    return CampaignArchiveBuildResult(
        archive_sha256=archive_sha256,
        member_count=inspected.member_count,
        source_fingerprint=inspected.fingerprint,
        total_byte_size=inspected.total_byte_size,
    )
