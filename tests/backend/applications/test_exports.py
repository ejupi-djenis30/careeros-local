import io
import zipfile
from datetime import datetime, timezone

import pytest

from backend.applications.exports import (
    MAX_CALENDAR_TASKS,
    MAX_DOSSIER_ARTIFACT_BYTES,
    CalendarExportError,
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


def test_calendar_neutralizes_content_line_injection_and_duplicate_uids():
    timestamp = datetime(2026, 8, 1, 9, tzinfo=timezone.utc)
    task = ApplicationTaskResponse.model_construct(
        id="task\r\nX-INJECTED:true",
        title="Review\r\nBEGIN:VEVENT",
        status="pending",
        priority="normal",
        due_at=timestamp,
        reminder_at=None,
        completed_at=None,
        revision=1,
        created_at=timestamp,
        updated_at=timestamp,
    )

    data = export_task_calendar("application", "Role", "Company", [task])

    assert b"\r\nX-INJECTED:" not in data
    assert b"\r\nBEGIN:VEVENT\r\n" not in data.split(b"SUMMARY:", 1)[1]
    with pytest.raises(CalendarExportError, match="duplicate"):
        export_task_calendar("application", "Role", "Company", [task, task])


def test_calendar_rejects_aggregate_task_and_byte_amplification(monkeypatch):
    timestamp = datetime(2026, 8, 1, 9, tzinfo=timezone.utc)
    task = ApplicationTaskResponse(
        id="77777777-7777-4777-8777-777777777777",
        title="Review",
        status="pending",
        priority="normal",
        due_at=timestamp,
        reminder_at=None,
        completed_at=None,
        revision=1,
        created_at=timestamp,
        updated_at=timestamp,
    )

    with pytest.raises(CalendarExportError, match="more than"):
        export_task_calendar("application", "Role", "Company", [task] * (MAX_CALENDAR_TASKS + 1))

    monkeypatch.setattr("backend.applications.exports.MAX_CALENDAR_BYTES", 64)
    with pytest.raises(CalendarExportError, match="byte limit"):
        export_task_calendar("application", "Role", "Company", [task])


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
                    "evidence_fact_ids": ["10000000-0000-4000-8000-000000000004"],
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


def _small_dossier(**overrides):
    values = {
        "dossier_id": "10000000-0000-4000-8000-000000000001",
        "version_number": 1,
        "application_revision": 2,
        "application_id": "10000000-0000-4000-8000-000000000002",
        "created_at": "2026-08-01T07:00:00+00:00",
        "role": {"title": "Role", "company": "Company", "location": None},
        "resume_version_id": "10000000-0000-4000-8000-000000000003",
        "readiness": {"status": "ready"},
        "cover_letter": None,
        "answers": [],
        "checklist": [],
        "requirement_matrix": [],
        "evidence_catalog": {},
        "resume_artifacts": {"pdf": (b"%PDF-safe", "application/pdf")},
    }
    values.update(overrides)
    return build_dossier_bundle(**values)


def test_dossier_archive_is_byte_stable_and_has_no_host_metadata():
    first = _small_dossier()
    second = _small_dossier()

    assert first.data == second.data
    assert first.sha256 == second.sha256
    with zipfile.ZipFile(io.BytesIO(first.data)) as archive:
        entries = archive.infolist()
        assert {entry.date_time for entry in entries} == {(1980, 1, 1, 0, 0, 0)}
        assert {entry.extra for entry in entries} == {b""}
        assert {entry.comment for entry in entries} == {b""}
        assert archive.comment == b""


def test_dossier_rejects_unexpected_resume_format_and_media_type():
    with pytest.raises(ValueError, match="unsupported"):
        _small_dossier(resume_artifacts={"html": (b"unsafe", "text/html")})
    with pytest.raises(ValueError, match="media type"):
        _small_dossier(resume_artifacts={"pdf": (b"%PDF-safe", "text/html")})
    with pytest.raises(ValueError, match="requires at least one"):
        _small_dossier(resume_artifacts={})
