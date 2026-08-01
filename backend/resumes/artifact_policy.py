"""Shared safety policy for immutable resume export artifacts."""

from __future__ import annotations

import re
import unicodedata

from backend.storage.atomic import read_verified

MAX_RESUME_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_RESUME_DOCX_ENTRIES = 256
MAX_RESUME_DOCX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024

PDF_MEDIA_TYPE = "application/pdf"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
RESUME_ARTIFACT_MEDIA_TYPES = {
    "docx": DOCX_MEDIA_TYPE,
    "pdf": PDF_MEDIA_TYPE,
}

_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def ensure_resume_artifact_size(data: bytes, *, label: str) -> bytes:
    if len(data) > MAX_RESUME_ARTIFACT_BYTES:
        raise ValueError(
            f"Generated {label} exceeds the {MAX_RESUME_ARTIFACT_BYTES}-byte artifact limit"
        )
    return data


def read_verified_resume_artifact(
    relative_path: str,
    *,
    expected_sha256: str,
    expected_size: int,
) -> bytes:
    """Read one immutable artifact without permitting record/file size amplification."""

    if (
        isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or expected_size <= 0
        or expected_size > MAX_RESUME_ARTIFACT_BYTES
        or not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise ValueError("Resume artifact metadata is invalid")
    try:
        return read_verified(
            relative_path,
            expected_sha256,
            expected_size=expected_size,
            maximum_size=MAX_RESUME_ARTIFACT_BYTES,
        )
    except ValueError as exc:
        raise ValueError("Resume artifact failed its integrity check") from exc


def safe_resume_filename(title: object, artifact_format: str) -> str:
    """Return a short ASCII basename that is safe across browser and Windows downloads."""

    if artifact_format not in RESUME_ARTIFACT_MEDIA_TYPES:
        raise ValueError("Unsupported resume artifact format")
    normalized = unicodedata.normalize("NFKD", str(title or ""))
    ascii_title = normalized.encode("ascii", "ignore").decode("ascii")
    suffix = f".{artifact_format}"
    if ascii_title.casefold().endswith(suffix):
        ascii_title = ascii_title[: -len(suffix)]
    basename = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_title)
    basename = basename.strip(" .-_")[:120].rstrip(" .-_")
    if not basename:
        basename = "resume"
    if basename.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        basename = f"resume-{basename}"
    return f"{basename}.{artifact_format}"
