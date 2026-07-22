from datetime import datetime, timezone

import pytest

from backend.applications.exports import (
    MAX_DOSSIER_ARTIFACT_BYTES,
    DossierSizeError,
    build_dossier_bundle,
    canonical_json,
    export_task_calendar,
)
from backend.applications.schemas import ApplicationTaskResponse


def test_calendar_folds_long_utf8_lines_at_rfc5545_octet_boundary():
    timestamp = datetime(2026, 8, 1, 9, tzinfo=timezone.utc)
    task = ApplicationTaskResponse(
        id="44444444-4444-4444-8444-444444444444",
        title="Inviare il dossier verificato " + "affidabilità " * 12,
        status="pending",
        priority="urgent",
        due_at=timestamp,
        reminder_at=None,
        completed_at=None,
        revision=1,
        created_at=timestamp,
        updated_at=timestamp,
    )

    data = export_task_calendar(
        "55555555-5555-4555-8555-555555555555",
        "Senior Platform Engineer",
        "Local Systems",
        [task],
    )

    assert all(len(line.encode("utf-8")) <= 75 for line in data.decode("utf-8").split("\r\n"))
    assert "\r\n " in data.decode("utf-8")


def test_canonical_json_rejects_non_finite_numbers():
    with pytest.raises(ValueError):
        canonical_json({"score": float("nan")})


def test_dossier_bundle_rejects_oversized_artifact_before_zip_creation():
    with pytest.raises(DossierSizeError, match="PDF resume artifact"):
        build_dossier_bundle(
            dossier_id="10000000-0000-4000-8000-000000000001",
            version_number=1,
            application_revision=2,
            application_id="10000000-0000-4000-8000-000000000002",
            created_at="2026-08-01T07:00:00+00:00",
            role={"title": "Role", "company": "Company", "location": None},
            resume_version_id="10000000-0000-4000-8000-000000000003",
            readiness={"status": "ready"},
            cover_letter=None,
            answers=[],
            checklist=[],
            requirement_matrix=[
                {
                    "requirement": "Operate systems",
                    "evidence_fact_ids": [
                        "10000000-0000-4000-8000-000000000004"
                    ],
                }
            ],
            evidence_catalog={},
            resume_artifacts={
                "pdf": (
                    b"x" * (MAX_DOSSIER_ARTIFACT_BYTES + 1),
                    "application/pdf",
                )
            },
        )
