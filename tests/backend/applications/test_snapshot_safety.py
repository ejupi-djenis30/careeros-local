from types import SimpleNamespace

from backend.applications.snapshots import sanitize_application_snapshot


def _verified_job() -> SimpleNamespace:
    return SimpleNamespace(
        analysis_verified=True,
        affinity_score=84,
        affinity_analysis="Receipt-verified summary",
        worth_applying=True,
        analysis_execution_id="10000000-0000-4000-8000-000000000001",
        analysis_row_fingerprint="a" * 64,
    )


def test_only_exact_current_verified_match_survives_snapshot_sanitization():
    job = _verified_job()
    safe = sanitize_application_snapshot(
        {
            "title": "Platform Engineer",
            "company": "Local Systems",
            "raw_metadata": {"analysis": "must not cross the boundary"},
            "match": {
                "score": 84,
                "analysis": "Receipt-verified summary",
                "worth_applying": True,
                "untrusted_extra": "must not survive",
            },
        },
        verified_job=job,
        quarantine_reason="unverified",
    )

    assert safe == {
        "schema_version": 2,
        "title": "Platform Engineer",
        "company": "Local Systems",
        "match": {
            "score": 84,
            "analysis": "Receipt-verified summary",
            "worth_applying": True,
            "receipt_verified": True,
            "execution_id": job.analysis_execution_id,
            "row_fingerprint": job.analysis_row_fingerprint,
        },
    }


def test_stale_match_is_replaced_even_when_linked_job_is_verified():
    safe = sanitize_application_snapshot(
        {
            "title": "Platform Engineer",
            "match": {
                "score": 100,
                "analysis": "Stale or forged summary",
                "worth_applying": True,
                "receipt_verified": True,
            },
        },
        verified_job=_verified_job(),
        quarantine_reason="stale_projection",
    )

    assert safe["match"] == {
        "score": None,
        "analysis": None,
        "worth_applying": None,
        "receipt_verified": False,
        "quarantine_reason": "stale_projection",
    }
