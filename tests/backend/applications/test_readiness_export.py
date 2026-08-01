from __future__ import annotations

import hashlib

import pytest

from backend.applications.readiness_export import (
    canonical_fingerprint,
    export_readiness,
)
from backend.applications.schemas import (
    ApplicationReadinessCheck,
    ApplicationReadinessReport,
    ReadinessEvidence,
)


def _report() -> ApplicationReadinessReport:
    report = ApplicationReadinessReport(
        application_id="10000000-0000-4000-8000-000000000001",
        application_revision=3,
        role_title="Platform Engineer",
        company="Local Systems",
        status="ready",
        completeness_score=100,
        blocker_count=0,
        warning_count=0,
        checks=[
            ApplicationReadinessCheck(
                id="role_identity",
                status="pass",
                points_awarded=10,
                points_available=10,
                evidence=[ReadinessEvidence(key="title_present", value="yes")],
            )
        ],
        fingerprint="0" * 64,
    )
    return report.model_copy(update={"fingerprint": canonical_fingerprint(report)})


def test_readiness_exports_are_deterministic_and_self_verifying():
    report = _report()

    first = export_readiness(report, "json")
    second = export_readiness(report, "json")

    assert first == second
    assert first.sha256 == hashlib.sha256(first.data).hexdigest()
    assert first.data.endswith(b"\n")


def test_readiness_export_rejects_stale_fingerprint_and_unknown_format():
    report = _report()
    stale = report.model_copy(update={"role_title": "Changed after fingerprinting"})

    with pytest.raises(ValueError, match="fingerprint"):
        export_readiness(stale, "json")
    with pytest.raises(ValueError, match="Unsupported"):
        export_readiness(report, "html")  # type: ignore[arg-type]
