"""Aggregate-only validation report builder for campaign archives (FR-002, US1)."""

from __future__ import annotations

import hashlib
from typing import Any

from backend.campaigns.parser import parse_campaign_workspace
from backend.campaigns.reconciliation import reconcile_dossier_directory_name

PROJECTION_FIELD_MAP: tuple[tuple[str, str], ...] = (
    ("application_date", "applied_at"),
    ("date_found", "found_at"),
    ("follow_up_date", "follow_up_at"),
    ("job_posting_url", "job_posting_url"),
    ("last_update", "last_update_at"),
    ("platform_source", "platform"),
    ("platform_url", "platform_url"),
)


def build_campaign_validation_report(archive_bytes: bytes) -> dict[str, Any]:
    """Inspect and parse campaign archive, returning strict aggregate-only report.

    Contains no paths, titles, company names, credentials, or private content.
    """
    parsed = parse_campaign_workspace(archive_bytes)
    tracker_ids = {row.source_application_id for row in parsed.tracker_rows}

    dossier_dirs: set[str] = set()
    for path in parsed.inspection.members:
        if path.startswith("application-packets/"):
            parts = path.split("/")
            if len(parts) >= 3:
                dossier_dirs.add(parts[1])

    descriptive_suffix_matches = sum(
        1 for d in dossier_dirs
        if d not in tracker_ids and reconcile_dossier_directory_name(d, tracker_ids) in tracker_ids
    )

    typed_projections: dict[str, int] = {
        name: sum(1 for r in parsed.tracker_rows if getattr(r, attr) is not None)
        for name, attr in PROJECTION_FIELD_MAP
    }

    member_digests = sorted(m.sha256 for m in parsed.inspection.members.values())
    commitment_bytes = b"".join(bytes.fromhex(item) for item in member_digests)
    digest_commitment = hashlib.sha256(commitment_bytes).hexdigest()

    return {
        "artifact_count": len(parsed.artifacts),
        "credential_rows_omitted": parsed.credentials_count,
        "descriptive_suffix_match_count": descriptive_suffix_matches,
        "dossier_count": parsed.dossier_count,
        "dossier_only_count": parsed.dossier_only_count,
        "expanded_bytes": parsed.inspection.total_byte_size,
        "logical_application_count": parsed.logical_application_count,
        "matched_count": parsed.matched_count,
        "member_count": parsed.inspection.member_count,
        "member_digest_commitment": digest_commitment,
        "member_sha256": member_digests,
        "source_fingerprint": parsed.fingerprint,
        "status_counts": dict(sorted(parsed.status_counts.items())),
        "tracker_only_count": parsed.tracker_only_count,
        "tracker_rows": len(parsed.tracker_rows),
        "typed_projection_counts": typed_projections,
    }
