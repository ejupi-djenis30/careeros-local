"""Focused provider schema validation contracts."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

ProviderAdapterKind = Literal["json", "html"]

ProviderRuntimeKind = Literal["json", "html", "native"]

ProviderMethod = Literal["GET", "POST"]

CANONICAL_FIELDS = frozenset(
    {
        "id",
        "title",
        "description",
        "company",
        "location",
        "url",
        "application_url",
        "application_email",
        "posted_at",
        "workload_min",
        "workload_max",
        "country_code",
    }
)

ALLOWED_TEMPLATE_VARIABLES = frozenset(
    {
        "query",
        "location",
        "language",
        "page",
        "page_one_based",
        "page_size",
        "offset",
        "workload_min",
        "workload_max",
    }
)

PRESERVE_SECRET = "__CAREEROS_PRESERVE_SECRET__"

REDACTED_SECRET = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"

_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")

_HEADER_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,80}$")

_FIELD_PATH_RE = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$")

_JSON_PATH_RE = re.compile(
    r"^(?:\$|(?:\$\.)?[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)$"
)

_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")

_PACK_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,159}$")

_PACK_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")

class StrictProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

def normalize_printable(value: str, *, maximum: int, label: str) -> str:
    normalized = unicodedata.normalize("NFC", value).strip()
    if (
        not normalized
        or len(normalized) > maximum
        or any(unicodedata.category(character).startswith("C") for character in normalized)
    ):
        raise ValueError(f"{label} must contain printable text")
    return normalized

def secret_header(_name: str) -> bool:
    """Treat every user-supplied header value as confidential.

    Header-name heuristics are not a security boundary: providers routinely use custom names for
    API credentials. Redacting and omitting every configured header prevents an innocuous-looking
    name from leaking its value through API, MCP or portable archives.
    """

    return True

def _validate_template(value: str) -> str:
    unknown = set(_PLACEHOLDER_RE.findall(value)) - ALLOWED_TEMPLATE_VARIABLES
    if unknown or "{{" in value or "}}" in value:
        raise ValueError("Provider templates contain an unsupported variable")
    return value

def _validate_template_tree(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        raise ValueError("Provider body nesting is too deep")
    if isinstance(value, str):
        if len(value) > 2_000:
            raise ValueError("Provider template values are too long")
        return _validate_template(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Provider body numbers must be finite")
    if isinstance(value, bool) or value is None or isinstance(value, int | float):
        return value
    if isinstance(value, list):
        if len(value) > 40:
            raise ValueError("Provider body lists are too large")
        return [_validate_template_tree(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 40 or not all(
            isinstance(key, str) and 1 <= len(key) <= 120 for key in value
        ):
            raise ValueError("Provider body objects are invalid")
        return {key: _validate_template_tree(item, depth=depth + 1) for key, item in value.items()}
    raise ValueError("Provider body values must be JSON-compatible")
