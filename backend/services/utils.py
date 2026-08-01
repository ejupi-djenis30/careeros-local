import asyncio
import logging
import math
import re
from io import BytesIO
from typing import TYPE_CHECKING

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader

from backend.core.config import settings
from backend.core.diagnostics import FailureCode, diagnose_failure, log_failure

if TYPE_CHECKING:
    from backend.providers.jobs.models import Coordinates

logger = logging.getLogger(__name__)

_SWISS_CITY_COORDINATES: dict[str, tuple[float, float]] = {
    "zurich": (47.3769, 8.5417),
    "zürich": (47.3769, 8.5417),
    "bern": (46.9480, 7.4474),
    "geneva": (46.2044, 6.1432),
    "genève": (46.2044, 6.1432),
    "genf": (46.2044, 6.1432),
    "basel": (47.5596, 7.5886),
    "lausanne": (46.5197, 6.6323),
    "lucerne": (47.0502, 8.3093),
    "luzern": (47.0502, 8.3093),
    "st. gallen": (47.4239, 9.3747),
    "sankt gallen": (47.4239, 9.3747),
    "lugano": (46.0037, 8.9511),
    "winterthur": (47.5000, 8.7167),
    "biel": (47.1367, 7.2467),
    "bienne": (47.1367, 7.2467),
    "thun": (46.7512, 7.6217),
    "koniz": (46.9242, 7.4202),
    "köniz": (46.9242, 7.4202),
    "fribourg": (46.8064, 7.1619),
    "freiburg": (46.8064, 7.1619),
    "schaffhausen": (47.6973, 8.6349),
    "chur": (46.8507, 9.5307),
    "neuchatel": (46.9899, 6.9290),
    "neuchâtel": (46.9899, 6.9290),
    "verniere": (46.2167, 6.0833),
    "uetikon": (47.2667, 8.6833),
    "dietikon": (47.4051, 8.4036),
    "dubendorf": (47.3969, 8.6153),
    "dübendorf": (47.3969, 8.6153),
}


def clean_html_tags(text: str) -> str:
    """Remove HTML tags like <em>, &nbsp;, etc. from text."""
    if not text:
        return ""
    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    clean = (
        clean.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    )
    # Normalize whitespace
    return " ".join(clean.split())


_ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}
# Content types that are explicitly NOT allowed regardless of extension.
# Empty/None and generic "application/octet-stream" are permitted since many
# clients and OS file pickers omit or genericize the content-type header.
_BLOCKED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
    "video/mp4",
    "video/avi",
    "video/quicktime",
    "audio/mpeg",
    "audio/wav",
    "application/zip",
    "application/x-rar-compressed",
    "application/x-msdownload",
    "application/x-executable",
    "application/javascript",
    "text/javascript",
    "application/x-sh",
    "application/x-csh",
    "application/x-python-code",
}


def safe_upload_filename(value: str | None, *, fallback: str = "upload") -> str:
    """Return a display-only basename without path or control characters."""

    candidate = str(value or "").replace("\\", "/").rsplit("/", 1)[-1]
    candidate = "".join(
        character for character in candidate if ord(character) >= 32 and ord(character) != 127
    ).strip(" .")
    return candidate[:255] or fallback


def _bounded_extracted_text(text: str) -> str:
    if len(text) > settings.CV_IMPORT_MAX_EXTRACTED_CHARS:
        raise ValueError("CV extracted text exceeded the configured safety limit")
    return text


async def extract_text_from_file(file: UploadFile) -> str:
    raw_content_type = file.content_type if isinstance(file.content_type, str) else ""
    content_type = raw_content_type.split(";")[0].strip().lower()
    filename = safe_upload_filename(file.filename).lower()
    ext = next((e for e in _ALLOWED_EXTENSIONS if filename.endswith(e)), None)

    if ext is None:
        raise HTTPException(
            status_code=400, detail="Unsupported file type. Please upload PDF, TXT, or MD."
        )

    # Block content types that are explicitly mismatched (e.g. images, executables).
    # Empty or generic content-type is allowed since OS/browsers often omit it.
    if content_type and content_type in _BLOCKED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File content type '{content_type}' is not allowed.",
        )

    try:
        content = await file.read(settings.MAX_UPLOAD_FILE_SIZE + 1)
        if len(content) > settings.MAX_UPLOAD_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="File too large for local CV processing.",
            )
        if ext == ".pdf":
            return await asyncio.to_thread(_extract_from_pdf, content)
        return _bounded_extracted_text(content.decode("utf-8"))
    except HTTPException:
        raise
    except Exception as exc:
        diagnostic = diagnose_failure(exc, FailureCode.LOCAL_RESOURCE_LOAD_FAILED)
        log_failure(logger, diagnostic, level=logging.WARNING)
        raise HTTPException(
            status_code=400,
            detail="The uploaded file could not be processed.",
        ) from exc


def _extract_from_pdf(content: bytes) -> str:
    try:
        document = PdfReader(BytesIO(content))
        if len(document.pages) > settings.CV_IMPORT_MAX_PAGES:
            raise ValueError("CV PDF exceeded the configured page limit")
        parts: list[str] = []
        extracted_characters = 0
        for page in document.pages:
            page_text = page.extract_text() or ""
            extracted_characters += len(page_text)
            if extracted_characters > settings.CV_IMPORT_MAX_EXTRACTED_CHARS:
                raise ValueError("CV extracted text exceeded the configured safety limit")
            parts.append(page_text)
        return "".join(parts)
    except Exception as exc:
        raise ValueError("PDF parsing failed") from exc


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points on Earth in km."""
    R = 6371.0  # Earth radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calculate_distance(coords1: tuple, coords2: tuple) -> float:
    """Wrapper for haversine_distance taking tuples (lat, lon)."""
    return haversine_distance(coords1[0], coords1[1], coords2[0], coords2[1])


async def geocode_location(city: str) -> "Coordinates | None":
    """Resolve a supported Swiss city without making a network request."""
    from backend.providers.jobs.models import Coordinates

    if not city:
        return None

    normalized = city.lower().strip()
    coordinates = _SWISS_CITY_COORDINATES.get(normalized)
    if coordinates is None:
        return None
    return Coordinates(lat=coordinates[0], lon=coordinates[1])
