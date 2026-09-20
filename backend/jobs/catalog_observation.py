"""Shared mutation rules for an existing scraped-job catalog observation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, cast

from backend.models.job import ScrapedJob

_CONTENT_FIELDS = frozenset({"title", "company", "description", "location", "workload"})


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def catalog_content_changed(
    record: ScrapedJob,
    *,
    refresh_fields: dict[str, Any],
    content_fingerprint: str,
) -> bool:
    stored = getattr(record, "content_fingerprint", None)
    if isinstance(stored, str) and stored.strip():
        return stored != content_fingerprint
    return any(
        getattr(record, field, None) != value
        for field, value in refresh_fields.items()
        if field in _CONTENT_FIELDS
    )


def clear_catalog_normalization(record: ScrapedJob) -> None:
    for column in ScrapedJob.__table__.columns:
        if column.name.startswith(("normalization_", "normalized_")) or column.name == (
            "posting_quality"
        ):
            setattr(record, column.name, None)


def apply_catalog_observation(
    record: ScrapedJob,
    *,
    seen_at: datetime,
    refresh_fields: dict[str, Any],
    content_fingerprint: str,
    normalized_bootstrap: dict[str, Any] | None = None,
    clear_normalization: Callable[[ScrapedJob], None] | None = None,
) -> bool:
    """Refresh a catalog row without committing and return whether content changed."""

    seen_at = aware_utc(seen_at)
    target = cast(Any, record)
    bootstrap = normalized_bootstrap or {}
    changed = catalog_content_changed(
        record,
        refresh_fields=refresh_fields,
        content_fingerprint=content_fingerprint,
    )

    created_at = getattr(record, "created_at", None)
    first_seen = getattr(record, "first_seen_at", None)
    if not isinstance(first_seen, datetime):
        first_seen = created_at if isinstance(created_at, datetime) else seen_at
    target.first_seen_at = min(aware_utc(first_seen), seen_at)

    previous_seen = getattr(record, "last_seen_at", None)
    target.last_seen_at = (
        max(aware_utc(previous_seen), seen_at) if isinstance(previous_seen, datetime) else seen_at
    )

    stored_revision = getattr(record, "content_revision", 1)
    if (
        isinstance(stored_revision, bool)
        or not isinstance(stored_revision, int)
        or stored_revision < 1
    ):
        stored_revision = 1
        target.content_revision = stored_revision

    previous_change = getattr(record, "last_changed_at", None)
    if not isinstance(previous_change, datetime):
        target.last_changed_at = target.first_seen_at

    for field, value in refresh_fields.items():
        setattr(target, field, value)
    target.content_fingerprint = content_fingerprint

    if changed:
        target.content_revision = stored_revision + 1
        target.last_changed_at = target.last_seen_at
        if clear_normalization is not None:
            clear_normalization(record)
        for field, value in bootstrap.items():
            setattr(record, field, value)
        metadata = dict(getattr(record, "normalized_metadata", None) or {})
        metadata["content_changed_at"] = target.last_changed_at.isoformat()
        target.normalized_metadata = metadata
    else:
        for field, value in bootstrap.items():
            if getattr(record, field, None) is None and value is not None:
                setattr(record, field, value)
    if not target.normalization_status:
        target.normalization_status = "provider_bootstrap"
    return changed
