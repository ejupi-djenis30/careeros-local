"""Privacy-safe durable receipts for completed job-search runs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Final

SEARCH_RECEIPT_SCHEMA_VERSION: Final = 1
SEARCH_RECEIPT_MAX_COUNTER: Final = 2_147_483_647
SEARCH_RECEIPT_MAX_DURATION_MS: Final = 31 * 24 * 60 * 60 * 1000
SEARCH_RECEIPT_MAX_SERIALIZED_BYTES: Final = 4096

SEARCH_RECEIPT_COUNTER_KEYS: Final = (
    "total_searches",
    "searches_completed",
    "jobs_found",
    "jobs_new",
    "jobs_unique",
    "jobs_duplicates",
    "jobs_duplicates_runtime",
    "jobs_duplicates_history",
    "jobs_duplicates_catalog_conflicts",
    "jobs_skipped",
    "jobs_analyzed",
    "jobs_analyze_total",
    "errors",
    "plan_unique_count",
)


def _coerce_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str):
        text = value.strip()
        if not text or len(text) > 64:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            timestamp = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _bounded_counter(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return min(SEARCH_RECEIPT_MAX_COUNTER, max(0, number))


def _provider_status(successful: int, failed: int) -> str:
    if successful and failed:
        return "partial"
    if successful:
        return "succeeded"
    if failed:
        return "failed"
    return "not_contacted"


def build_search_completion_summary(
    status_payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Build a fixed-shape receipt from a successful terminal runtime status.

    Only explicitly allowlisted counters and timestamps cross this boundary. Query
    text, CV content, listing text, logs and provider response bodies are never read.
    """

    if status_payload.get("state") != "done":
        return None

    started_at = _coerce_timestamp(status_payload.get("started_at"))
    finished_at = _coerce_timestamp(status_payload.get("finished_at"))
    if started_at is None or finished_at is None or finished_at < started_at:
        return None

    duration_ms = min(
        SEARCH_RECEIPT_MAX_DURATION_MS,
        max(0, int((finished_at - started_at).total_seconds() * 1000)),
    )
    counts = {key: _bounded_counter(status_payload.get(key)) for key in SEARCH_RECEIPT_COUNTER_KEYS}
    successful_requests = _bounded_counter(status_payload.get("provider_successes"))
    failed_requests = _bounded_counter(status_payload.get("provider_failures"))
    providers = {
        "status": _provider_status(successful_requests, failed_requests),
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "queries_without_provider": _bounded_counter(
            status_payload.get("queries_without_provider")
        ),
    }
    summary = {
        "schema_version": SEARCH_RECEIPT_SCHEMA_VERSION,
        "started_at": _timestamp_text(started_at),
        "finished_at": _timestamp_text(finished_at),
        "duration_ms": duration_ms,
        "counts": counts,
        "providers": providers,
    }
    if (
        len(
            json.dumps(
                summary,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        > SEARCH_RECEIPT_MAX_SERIALIZED_BYTES
    ):
        return None
    return summary


def normalize_search_completion_summary(value: Any) -> dict[str, Any] | None:
    """Canonicalize an imported receipt while dropping every non-allowlisted key."""

    if not isinstance(value, Mapping):
        return None
    counts = value.get("counts")
    providers = value.get("providers")
    if not isinstance(counts, Mapping) or not isinstance(providers, Mapping):
        return None

    payload: dict[str, Any] = {
        "state": "done",
        "started_at": value.get("started_at"),
        "finished_at": value.get("finished_at"),
        "provider_successes": providers.get("successful_requests"),
        "provider_failures": providers.get("failed_requests"),
        "queries_without_provider": providers.get("queries_without_provider"),
    }
    payload.update({key: counts.get(key) for key in SEARCH_RECEIPT_COUNTER_KEYS})
    return build_search_completion_summary(payload)
