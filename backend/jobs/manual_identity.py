"""Server-owned identities for private manual job captures."""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from backend.jobs.urls import normalize_job_url

_TRACKING_QUERY_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "ref",
        "referrer",
        "source",
    }
)


def canonical_manual_identity_url(value: str | None) -> str | None:
    """Canonicalize URL details that do not identify a distinct vacancy."""

    normalized = normalize_job_url(value, required=False)
    if normalized is None:
        return None
    parsed = urlsplit(normalized)
    hostname = parsed.hostname or ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    default_port = (parsed.scheme == "http" and parsed.port == 80) or (
        parsed.scheme == "https" and parsed.port == 443
    )
    netloc = hostname if parsed.port is None or default_port else f"{hostname}:{parsed.port}"
    path = parsed.path.rstrip("/") or "/"
    query_items = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in _TRACKING_QUERY_KEYS
    ]
    query = urlencode(sorted(query_items))
    return urlunsplit((parsed.scheme, netloc, path, query, ""))


def stable_manual_platform_job_id(
    user_id: int,
    *,
    title: str,
    company: str,
    external_url: str | None,
) -> str:
    """Return a private, stable identity for one manually supplied vacancy.

    A canonical URL is the strongest available identity: host and scheme are
    case-insensitive, fragments are presentation-only, while path and query
    remain case-sensitive. Title and company are only a fallback for callers
    that do not have a URL.
    """

    canonical_url = canonical_manual_identity_url(external_url)
    if canonical_url:
        source_identity = f"url:{canonical_url}"
    else:
        source_identity = "fallback:{}|{}".format(
            str(title or "").strip().casefold(),
            str(company or "").strip().casefold(),
        )
    digest = hashlib.sha256(
        f"user:{user_id}|platform:manual|{source_identity}".encode("utf-8")
    ).hexdigest()
    return f"manual-{digest[:24]}"
