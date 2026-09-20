"""Campaign ZIP archive validation, boundary checks, and fingerprint derivation."""

from __future__ import annotations

import hashlib
import io
import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping

MAX_COMPRESSED_BYTES: Final = 128 * 1024 * 1024  # 128 MiB
MAX_EXPANDED_BYTES: Final = 256 * 1024 * 1024    # 256 MiB
MAX_MEMBERS: Final = 5000
MAX_FILE_BYTES: Final = 10 * 1024 * 1024         # 10 MiB

ALLOWED_ROOT_FILES: Final = frozenset({
    "ApplicationTracker.xlsx",
    "Profile.md",
    "Goal.md",
    "Storytelling.md",
})

ALLOWED_ROOT_DIRECTORIES: Final = frozenset({
    "assets",
    "application-packets",
    "cv-templates",
    "cover-letter-templates",
    "email-templates",
    "html-templates",
    "scripts",
})


class ArchivePolicyError(ValueError):
    """Raised when an archive violates structure, security boundaries, or limits."""


@dataclass(frozen=True, slots=True)
class CampaignArchiveMember:
    canonical_path: str
    byte_size: int
    sha256: str
    raw_bytes: bytes


@dataclass(frozen=True, slots=True)
class CampaignArchiveInspection:
    fingerprint: str
    common_prefix: str
    members: Mapping[str, CampaignArchiveMember]
    total_byte_size: int
    member_count: int


def _is_symlink_or_special(zinfo: zipfile.ZipInfo) -> bool:
    mode = (zinfo.external_attr >> 16) & 0o170000
    return mode in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFSOCK)


def _validate_path_syntax(name: str) -> None:
    if any(unicodedata.category(c).startswith("C") for c in name):
        raise ArchivePolicyError(f"Entry contains control characters: {name!r}")
    if "\\" in name:
        raise ArchivePolicyError(f"Entry contains backslash: {name}")
    if ":" in name or name.startswith("//") or name.startswith("\\\\"):
        raise ArchivePolicyError(f"Entry contains drive or UNC prefix: {name}")
    if name.startswith("/"):
        raise ArchivePolicyError(f"Entry contains absolute path: {name}")

    parts = name.split("/")
    for part in parts:
        if part in ("..", "."):
            raise ArchivePolicyError(f"Entry contains traversal segment: {name}")


def _detect_common_prefix(names: list[str]) -> str:
    """If all non-empty entries share a single top-level directory, return it unless allowlisted."""
    first_segments = set()
    for name in names:
        parts = [p for p in name.split("/") if p]
        if len(parts) > 1:
            first_segments.add(parts[0])
        elif len(parts) == 1 and name.endswith("/"):
            first_segments.add(parts[0])
        elif len(parts) == 1:
            # File at root -> no common folder prefix
            return ""
    if len(first_segments) == 1:
        candidate = next(iter(first_segments))
        if candidate in ALLOWED_ROOT_DIRECTORIES:
            return ""
        return candidate
    return ""


def _is_allowed_root(canonical_path: str) -> bool:
    parts = canonical_path.split("/")
    if len(parts) == 1:
        if canonical_path in ALLOWED_ROOT_FILES:
            return True
        if canonical_path.lower().endswith(".pdf"):
            return True
        return False
    root_dir = parts[0]
    return root_dir in ALLOWED_ROOT_DIRECTORIES


def inspect_and_validate_campaign_archive(data: bytes) -> CampaignArchiveInspection:
    """Validate archive integrity and boundaries, returning inert inspected members."""
    if len(data) > MAX_COMPRESSED_BYTES:
        raise ArchivePolicyError(f"Archive exceeds compressed limit of {MAX_COMPRESSED_BYTES} bytes")

    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            infolist = zf.infolist()
            if len(infolist) > MAX_MEMBERS:
                raise ArchivePolicyError(f"Archive exceeds members limit of {MAX_MEMBERS}")

            for zinfo in infolist:
                orig_name = getattr(zinfo, "orig_filename", zinfo.filename)
                _validate_path_syntax(zinfo.filename)
                if orig_name != zinfo.filename:
                    _validate_path_syntax(orig_name)

            all_names = [info.filename for info in infolist]
            common_prefix = _detect_common_prefix(all_names)
            prefix_len = len(common_prefix) + 1 if common_prefix else 0

            seen_canonical: dict[str, str] = {}
            members: dict[str, CampaignArchiveMember] = {}
            total_expanded = 0

            for zinfo in infolist:
                if zinfo.flag_bits & 0x1:
                    raise ArchivePolicyError(f"Archive contains encrypted entry: {zinfo.filename}")
                if _is_symlink_or_special(zinfo):
                    raise ArchivePolicyError(f"Archive contains symlink or special file: {zinfo.filename}")

                raw_name = zinfo.filename[prefix_len:] if prefix_len else zinfo.filename
                cleaned = "/".join(p for p in raw_name.split("/") if p)

                # Directory entries themselves do not become file members
                if zinfo.filename.endswith("/") or (not cleaned and zinfo.is_dir()):
                    continue

                if not cleaned:
                    raise ArchivePolicyError(f"Entry normalizes to empty path: {zinfo.filename}")

                canonical_path = unicodedata.normalize("NFC", cleaned)
                canonical_key = canonical_path.casefold()
                if canonical_key in seen_canonical:
                    raise ArchivePolicyError(
                        f"Archive contains duplicate entry: {cleaned} and {seen_canonical[canonical_key]}"
                    )
                seen_canonical[canonical_key] = canonical_path

                if not _is_allowed_root(canonical_path):
                    raise ArchivePolicyError(f"Archive contains unsupported root entry: {canonical_path}")

                if zinfo.file_size > MAX_FILE_BYTES:
                    raise ArchivePolicyError(f"Entry {canonical_path} exceeds file size limit of {MAX_FILE_BYTES}")

                total_expanded += zinfo.file_size
                if total_expanded > MAX_EXPANDED_BYTES:
                    raise ArchivePolicyError(f"Archive exceeds expanded limit of {MAX_EXPANDED_BYTES}")

                try:
                    content = zf.read(zinfo)
                except (zipfile.BadZipFile, OSError) as exc:
                    raise ArchivePolicyError(f"Failed to read entry {canonical_path}") from exc

                if len(content) != zinfo.file_size:
                    raise ArchivePolicyError(f"Entry {canonical_path} byte size mismatch")

                digest = hashlib.sha256(content).hexdigest()
                members[canonical_path] = CampaignArchiveMember(
                    canonical_path=canonical_path,
                    byte_size=len(content),
                    sha256=digest,
                    raw_bytes=content,
                )

            if not members:
                raise ArchivePolicyError("Archive contains no valid allowlisted files")

            # Deterministic fingerprint: sort by canonical path, hash path, size, and digest
            hasher = hashlib.sha256()
            for path in sorted(members.keys()):
                m = members[path]
                hasher.update(f"{m.canonical_path}\t{m.byte_size}\t{m.sha256}\n".encode("utf-8"))
            fingerprint = hasher.hexdigest()

            return CampaignArchiveInspection(
                fingerprint=fingerprint,
                common_prefix=common_prefix,
                members=MappingProxyType(members),
                total_byte_size=total_expanded,
                member_count=len(members),
            )
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchivePolicyError("Archive is not a valid ZIP file") from exc
