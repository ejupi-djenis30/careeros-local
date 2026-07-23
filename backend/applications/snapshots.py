from __future__ import annotations

from typing import Any, Mapping

APPLICATION_SNAPSHOT_SCHEMA_VERSION = 2
APPLICATION_MATCH_FIELDS = ("score", "analysis", "worth_applying")

# Application workflows use a deliberately small projection of a listing. Keeping an allowlist
# prevents historical or imported free-form JSON from hiding raw analysis under a new key or
# inside provider metadata that the application workflow never consumes.
APPLICATION_SNAPSHOT_SAFE_FIELDS = frozenset(
    {
        "title",
        "company",
        "description",
        "location",
        "external_url",
        "application_url",
        "application_email",
        "workload",
        "publication_date",
        "platform",
        "platform_job_id",
    }
)


def _neutral_match(reason: str) -> dict[str, Any]:
    return {
        "score": None,
        "analysis": None,
        "worth_applying": None,
        "receipt_verified": False,
        "quarantine_reason": reason,
    }


def _verified_match(job: Any) -> dict[str, Any]:
    return {
        "score": getattr(job, "affinity_score", None),
        "analysis": getattr(job, "affinity_analysis", None),
        "worth_applying": getattr(job, "worth_applying", None),
        "receipt_verified": True,
        "execution_id": getattr(job, "analysis_execution_id", None),
        "row_fingerprint": getattr(job, "analysis_row_fingerprint", None),
    }


def snapshot_match_is_current(snapshot: Mapping[str, Any], job: Any) -> bool:
    """Return whether a snapshot is the exact projection of a verified current match."""

    if getattr(job, "analysis_verified", False) is not True:
        return False
    match = snapshot.get("match")
    if not isinstance(match, Mapping):
        return False
    expected = _verified_match(job)
    return all(match.get(field) == expected[field] for field in APPLICATION_MATCH_FIELDS)


def sanitize_application_snapshot(
    snapshot: object,
    *,
    verified_job: Any | None = None,
    quarantine_reason: str,
) -> dict[str, Any]:
    """Return a non-mutating snapshot safe for display or a portable boundary.

    A snapshot does not carry an independently verifiable receipt. Its match projection may
    survive only while it exactly matches the current Job row and that row has just passed the
    complete receipt, input-evidence and citation attestation. Every other match is replaced;
    raw prose and scores are deliberately not copied into quarantine metadata.
    """

    source = snapshot if isinstance(snapshot, Mapping) else {}
    sanitized = {
        field: source[field] for field in APPLICATION_SNAPSHOT_SAFE_FIELDS if field in source
    }
    sanitized["schema_version"] = APPLICATION_SNAPSHOT_SCHEMA_VERSION
    if verified_job is not None and snapshot_match_is_current(source, verified_job):
        sanitized["match"] = _verified_match(verified_job)
    else:
        sanitized["match"] = _neutral_match(quarantine_reason)
    return sanitized


def snapshot_from_job(job: Any) -> dict[str, Any]:
    scraped = job.scraped_job
    snapshot = {
        "schema_version": APPLICATION_SNAPSHOT_SCHEMA_VERSION,
        "title": scraped.title,
        "company": scraped.company,
        "description": scraped.description,
        "location": scraped.location,
        "external_url": scraped.external_url,
        "application_url": scraped.application_url,
        "application_email": scraped.application_email,
        "workload": scraped.workload,
        "publication_date": (
            scraped.publication_date.isoformat() if scraped.publication_date else None
        ),
        "platform": scraped.platform,
        "platform_job_id": scraped.platform_job_id,
        "match": {
            "score": job.affinity_score,
            "analysis": job.affinity_analysis,
            "worth_applying": job.worth_applying,
        },
    }
    return sanitize_application_snapshot(
        snapshot,
        verified_job=job,
        quarantine_reason="analysis_not_receipt_verified",
    )
