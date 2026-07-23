import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import update

from backend.applications.models import Application, ApplicationEvent
from backend.career.models import CandidateProfile, CareerFact
from backend.models import Job, ScrapedJob, User
from backend.resumes.models import ResumeArtifact, ResumeDraft, ResumeVersion
from backend.resumes.renderers.ats import render_ats_docx, render_ats_pdf
from backend.resumes.storage import store_resume_artifact
from backend.services.auth import get_password_hash
from backend.storage.atomic import read_verified, resolve_data_path


@pytest.fixture
def readiness_storage(monkeypatch):
    with TemporaryDirectory(prefix="careeros-readiness-", ignore_cleanup_errors=True) as directory:
        monkeypatch.setattr("backend.storage.atomic.settings.DATA_DIR", directory)
        yield Path(directory)


def _job(db_session, test_user):
    scraped = ScrapedJob(
        platform="fixture",
        platform_job_id="application-job",
        title="Local Platform Engineer",
        company="Local Systems AG",
        description="Build reliable local infrastructure.",
        location="Zurich",
        external_url="https://example.test/jobs/local-platform",
        normalization_status="provider_bootstrap",
        normalized_domain="it",
        normalized_required_skills=["python", "sqlite"],
    )
    db_session.add(scraped)
    db_session.flush()
    job = Job(
        user_id=test_user.id,
        scraped_job_id=scraped.id,
        affinity_score=82,
        affinity_analysis="Deterministic local match",
        worth_applying=True,
        applied=False,
        dismissed=False,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _assert_application_projections(
    db_session,
    application_id: str,
    *,
    title: str,
    company: str,
    location: str | None,
) -> Application:
    """Verify board projections against the committed append-only timeline."""
    db_session.expire_all()
    stored = db_session.query(Application).filter(Application.id == application_id).one()
    event_times = [
        event.occurred_at
        for event in db_session.query(ApplicationEvent)
        .filter(ApplicationEvent.application_id == application_id)
        .all()
    ]
    assert event_times
    assert stored.job_title == title
    assert stored.job_company == company
    assert stored.job_location == location
    assert stored.latest_event_at == max(event_times)
    return stored


def test_application_timeline_is_append_only_and_revisioned(
    client, auth_headers, db_session, test_user
):
    job = _job(db_session, test_user)
    created = client.post(
        "/api/v1/applications",
        json={"job_id": job.id, "initial_stage": "saved", "note": "Promising role"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    application = created.json()
    assert application["revision"] == 1
    assert application["current_stage"] == "saved"
    assert application["job_snapshot"]["title"] == "Local Platform Engineer"
    assert application["job_snapshot"]["description"] == "Build reliable local infrastructure."
    assert len(application["events"]) == 1

    preparing = client.post(
        f"/api/v1/applications/{application['id']}/events",
        json={
            "expected_revision": 1,
            "event_type": "stage",
            "stage": "preparing",
            "note": "Tailoring the resume",
        },
        headers=auth_headers,
    )
    assert preparing.status_code == 201, preparing.text
    assert preparing.json()["revision"] == 2
    assert preparing.json()["current_stage"] == "preparing"

    note = client.post(
        f"/api/v1/applications/{application['id']}/events",
        json={
            "expected_revision": 2,
            "event_type": "note",
            "note": "Research hiring manager",
        },
        headers=auth_headers,
    )
    assert note.status_code == 201, note.text
    assert note.json()["revision"] == 3
    assert note.json()["current_stage"] == "preparing"
    assert [event["event_type"] for event in note.json()["events"]] == [
        "stage",
        "stage",
        "note",
    ]

    stale = client.post(
        f"/api/v1/applications/{application['id']}/events",
        json={"expected_revision": 1, "event_type": "stage", "stage": "applied"},
        headers=auth_headers,
    )
    assert stale.status_code == 409
    invalid = client.post(
        f"/api/v1/applications/{application['id']}/events",
        json={"expected_revision": 3, "event_type": "stage", "stage": "accepted"},
        headers=auth_headers,
    )
    assert invalid.status_code == 409

    historical = client.post(
        f"/api/v1/applications/{application['id']}/events",
        json={
            "expected_revision": 3,
            "event_type": "note",
            "note": "Imported historical context",
            "occurred_at": "2024-01-01T10:00:00+02:00",
        },
        headers=auth_headers,
    )
    assert historical.status_code == 201, historical.text
    assert historical.json()["revision"] == 4

    listing = client.get("/api/v1/applications", headers=auth_headers)
    assert listing.status_code == 200
    assert listing.json()[0]["title"] == "Local Platform Engineer"
    assert listing.json()[0]["company"] == "Local Systems AG"
    assert listing.json()[0]["location"] == "Zurich"
    assert "job_snapshot" not in listing.json()[0]
    stored = _assert_application_projections(
        db_session,
        application["id"],
        title="Local Platform Engineer",
        company="Local Systems AG",
        location="Zurich",
    )
    assert listing.json()[0]["latest_event_at"] == stored.latest_event_at.isoformat().replace(
        "+00:00", "Z"
    )

    assert client.get("/api/v1/applications?offset=1&limit=1", headers=auth_headers).json() == []
    assert client.get("/api/v1/applications?limit=0", headers=auth_headers).status_code == 422

    event = (
        db_session.query(ApplicationEvent)
        .filter(
            ApplicationEvent.event_type == "note",
            ApplicationEvent.note == "Research hiring manager",
        )
        .one()
    )
    event.note = "Attempted edit"
    with pytest.raises(ValueError, match="append-only"):
        db_session.commit()
    db_session.rollback()


def test_application_create_and_read_never_expose_unverified_match_snapshot(
    client, auth_headers, db_session, test_user
):
    job = _job(db_session, test_user)

    created = client.post(
        "/api/v1/applications",
        json={"job_id": job.id},
        headers=auth_headers,
    )

    assert created.status_code == 201, created.text
    application = created.json()
    assert application["job_snapshot"]["match"] == {
        "score": None,
        "analysis": None,
        "worth_applying": None,
        "receipt_verified": False,
        "quarantine_reason": "analysis_not_receipt_verified",
    }
    assert "Deterministic local match" not in json.dumps(application["job_snapshot"])

    stored = db_session.get(Application, application["id"])
    stored.job_snapshot = {
        **stored.job_snapshot,
        "affinity_analysis": "forged top-level claim",
        "raw_metadata": {"analysis": "forged nested metadata claim"},
        "match": {
            "score": 100,
            "analysis": "forged embedded claim",
            "worth_applying": True,
            "receipt_verified": True,
        },
    }
    db_session.commit()

    loaded = client.get(f"/api/v1/applications/{application['id']}", headers=auth_headers)
    assert loaded.status_code == 200, loaded.text
    safe_snapshot = loaded.json()["job_snapshot"]
    assert safe_snapshot["match"]["receipt_verified"] is False
    assert safe_snapshot["match"]["score"] is None
    assert "affinity_analysis" not in safe_snapshot
    assert "raw_metadata" not in safe_snapshot
    assert "forged" not in json.dumps(safe_snapshot)


def test_application_rejects_unowned_or_duplicate_job(client, auth_headers, db_session, test_user):
    job = _job(db_session, test_user)
    first = client.post("/api/v1/applications", json={"job_id": job.id}, headers=auth_headers)
    assert first.status_code == 201
    duplicate = client.post("/api/v1/applications", json={"job_id": job.id}, headers=auth_headers)
    assert duplicate.status_code == 409
    missing = client.post("/api/v1/applications", json={"job_id": 999999}, headers=auth_headers)
    assert missing.status_code == 422


def test_application_accepts_a_safe_manual_job_snapshot(client, auth_headers, db_session):
    created = client.post(
        "/api/v1/applications",
        json={
            "manual_job": {
                "title": "Platform Engineer",
                "company": "Private Local Company",
                "description": "A posting captured manually after the source disappeared.",
                "location": "Bern",
                "external_url": "HTTPS://EXAMPLE.TEST/jobs/../jobs/platform#apply",
            },
            "initial_stage": "applied",
            "note": "Applied outside the discovery workflow",
        },
        headers=auth_headers,
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["job_id"] is None
    assert body["job_snapshot"]["platform"] == "manual"
    assert body["job_snapshot"]["title"] == "Platform Engineer"
    assert body["job_snapshot"]["external_url"] == "https://example.test/jobs/platform"
    assert body["events"][0]["stage"] == "applied"
    listing = client.get("/api/v1/applications", headers=auth_headers).json()[0]
    assert listing["title"] == "Platform Engineer"
    assert listing["company"] == "Private Local Company"
    assert listing["location"] == "Bern"
    stored = _assert_application_projections(
        db_session,
        body["id"],
        title="Platform Engineer",
        company="Private Local Company",
        location="Bern",
    )
    assert listing["latest_event_at"] == stored.latest_event_at.isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///private/cv.txt"])
def test_application_rejects_unsafe_manual_job_urls(client, auth_headers, url):
    response = client.post(
        "/api/v1/applications",
        json={
            "manual_job": {
                "title": "Unsafe role",
                "company": "Unknown",
                "external_url": url,
            }
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_application_rejects_malformed_manual_application_email(client, auth_headers):
    response = client.post(
        "/api/v1/applications",
        json={
            "manual_job": {
                "title": "Unsafe contact",
                "company": "Unknown",
                "application_email": "name@invalid_domain",
            }
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_application_requires_authentication(client):
    assert client.get("/api/v1/applications").status_code == 401


def test_readiness_reports_zero_data_and_missing_application_inputs(client, auth_headers):
    missing = client.get(
        "/api/v1/applications/00000000-0000-0000-0000-000000000000/readiness",
        headers=auth_headers,
    )
    assert missing.status_code == 404

    created = client.post(
        "/api/v1/applications",
        json={
            "manual_job": {
                "title": "Platform Engineer",
                "company": "Local Systems",
            }
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    report = client.get(
        f"/api/v1/applications/{created.json()['id']}/readiness",
        headers=auth_headers,
    )

    assert report.status_code == 200, report.text
    body = report.json()
    assert body["score_kind"] == "preflight_completeness"
    assert body["status"] == "blocked"
    assert body["completeness_score"] == 10
    assert body["blocker_count"] == 8
    assert len(body["checks"]) == 9
    assert [check["id"] for check in body["checks"]] == [
        "role_identity",
        "role_description",
        "application_route",
        "career_profile",
        "resume_linked",
        "resume_artifacts",
        "resume_quality",
        "resume_freshness",
        "fact_verification",
    ]
    for check in body["checks"]:
        assert check["evidence"]
        if check["status"] != "pass":
            assert check["action"]


def _renderable_snapshot(facts: list[CareerFact]) -> dict:
    fact_snapshots = [
        {
            "id": fact.id,
            "fact_type": fact.fact_type,
            "verification_status": fact.verification_status,
        }
        for fact in facts
    ]
    return {
        "profile": {
            "display_name": "Mira Vale",
            "headline": "Principal Software Engineer",
            "email": "mira@example.test",
        },
        "resume": {
            "title": "Platform application",
            "template_kind": "ats",
            "section_config": {"order": ["experience"]},
            "content_overrides": {},
            "canvas_document": {
                "schema_version": 2,
                "style": {
                    "font_family": "Helvetica",
                    "base_font_size": 10,
                    "line_height": 1.3,
                    "section_spacing": 10,
                    "margin_mm": 18,
                    "accent_color": "#243B53",
                    "columns": 1,
                },
                "sections": [
                    {
                        "id": "identity",
                        "kind": "identity",
                        "title": "IDENTITY",
                        "visible": True,
                        "page_break_before": False,
                        "blocks": [
                            {
                                "id": "identity-main",
                                "kind": "identity",
                                "fact_ids": [],
                                "visible": True,
                                "content": {
                                    "title": "Mira Vale",
                                    "subtitle": "Principal Software Engineer",
                                    "date_range": "",
                                    "description": "mira@example.test",
                                    "bullets": [],
                                },
                                "manual_fields": [],
                                "layout": {
                                    "spacing_before_pt": 0,
                                    "keep_together": True,
                                },
                            }
                        ],
                    },
                    {
                        "id": "experience",
                        "kind": "experience",
                        "title": "EXPERIENCE",
                        "visible": True,
                        "page_break_before": False,
                        "blocks": [
                            {
                                "id": "experience-main",
                                "kind": "fact",
                                "fact_ids": [facts[0].id],
                                "visible": True,
                                "content": {
                                    "title": "Principal Engineer",
                                    "subtitle": "Local Systems",
                                    "date_range": "2021 – Present",
                                    "description": "Led privacy-preserving platform delivery.",
                                    "bullets": ["Reduced deployment lead time by 40%."],
                                },
                                "manual_fields": [],
                                "layout": {
                                    "spacing_before_pt": 0,
                                    "keep_together": True,
                                },
                            }
                        ],
                    },
                ],
            },
        },
        "facts": fact_snapshots,
    }


def _complete_application_pack(
    db_session, test_user, *, artifact_formats: tuple[str, ...] = ("pdf", "docx")
) -> str:
    profile = CandidateProfile(
        user_id=test_user.id,
        revision=3,
        display_name="Mira Vale",
        headline="Principal Software Engineer",
        summary="Builds dependable local systems and develops engineering teams.",
        email="mira@example.test",
        location={"city": "Zurich", "country": "CH"},
        preferences={
            "target_roles": ["Staff Engineer"],
            "target_industries": ["Software"],
            "preferred_work_modes": ["hybrid"],
            "salary_min_chf": 150000,
        },
    )
    profile.facts = [
        CareerFact(
            fact_type="experience",
            position=0,
            verification_status="confirmed",
            payload={
                "role": "Principal Engineer",
                "organization": "Local Systems",
                "description": "Led privacy-preserving platform delivery.",
                "achievements": ["Reduced deployment lead time by 40%."],
                "metrics": ["40%"],
            },
        ),
        CareerFact(
            fact_type="skill",
            position=1,
            verification_status="confirmed",
            payload={"name": "Python", "evidence_fact_ids": []},
        ),
        CareerFact(
            fact_type="education",
            position=2,
            verification_status="confirmed",
            payload={"qualification": "BSc Mathematics", "institution": "University"},
        ),
        CareerFact(
            fact_type="achievement",
            position=3,
            verification_status="confirmed",
            payload={"title": "Delivery improvement", "metric_value": "40%"},
        ),
        CareerFact(
            fact_type="project",
            position=4,
            verification_status="confirmed",
            payload={"name": "Local Platform", "description": "Offline-first tooling"},
        ),
        CareerFact(
            fact_type="certification",
            position=5,
            verification_status="confirmed",
            payload={"name": "Systems Architecture"},
        ),
    ]
    db_session.add(profile)
    db_session.flush()
    selected_ids = [fact.id for fact in profile.facts]
    draft = ResumeDraft(
        profile_id=profile.id,
        revision=1,
        profile_revision=profile.revision,
        title="Platform application",
        template_kind="ats",
        section_config={},
        selected_fact_ids=selected_ids,
        content_overrides={},
        canvas_document={},
        generation_context={"mode": "deterministic"},
    )
    db_session.add(draft)
    db_session.flush()
    snapshot = _renderable_snapshot(profile.facts)
    version = ResumeVersion(
        draft_id=draft.id,
        version_number=1,
        semantic_version="1.0.0",
        name="Platform application · v1.0.0",
        snapshot=snapshot,
        snapshot_sha256="a" * 64,
        profile_revision=profile.revision,
        selected_fact_ids=selected_ids,
        template_kind="ats",
        renderer_version="careeros-canvas-3.0",
        published_at=datetime.now(timezone.utc),
        quality_report={"passed": True, "text_order_verified": True},
    )
    db_session.add(version)
    db_session.flush()
    rendered = {
        "pdf": (render_ats_pdf(snapshot), "application/pdf"),
        "docx": (
            render_ats_docx(snapshot),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    }
    for artifact_format in artifact_formats:
        payload, media_type = rendered[artifact_format]
        stored = store_resume_artifact(
            profile_id=profile.id,
            version_id=version.id,
            format=artifact_format,
            data=payload,
        )
        db_session.add(
            ResumeArtifact(
                version_id=version.id,
                format=artifact_format,
                media_type=media_type,
                sha256=stored.sha256,
                byte_size=stored.byte_size,
                storage_path=stored.relative_path,
                created_at=datetime.now(timezone.utc),
            )
        )
    db_session.commit()
    return version.id


def _ready_application(client, auth_headers, version_id: str) -> str:
    created = client.post(
        "/api/v1/applications",
        json={
            "manual_job": {
                "title": "Senior Platform Engineer",
                "company": "Local Systems AG",
                "description": (
                    "Build and operate a private local platform, document architecture decisions, "
                    "improve release reliability, support incident reviews and work with product "
                    "teams on secure measurable delivery."
                ),
                "application_url": "https://example.test/apply/platform",
            },
            "resume_version_id": version_id,
            "initial_stage": "preparing",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def test_readiness_complete_pack_and_exports_are_deterministic(
    client, auth_headers, db_session, test_user, readiness_storage
):
    version_id = _complete_application_pack(db_session, test_user)
    private_description = (
        "PRIVATE SNAPSHOT DESCRIPTION: own the local platform, improve delivery reliability, "
        "document decisions, support incident reviews, and work with product teams on secure "
        "releases. This body must never appear in a readiness export."
    )
    hostile_title = (
        "`[Senior](javascript:alert(1)) <script>alert(1)</script> *Platform* # Engineer\nNext"
    )
    created = client.post(
        "/api/v1/applications",
        json={
            "manual_job": {
                "title": hostile_title,
                "company": "Local Systems",
                "description": private_description,
                "external_url": "https://example.test/jobs/platform",
            },
            "resume_version_id": version_id,
            "initial_stage": "preparing",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    application_id = created.json()["id"]

    report = client.get(f"/api/v1/applications/{application_id}/readiness", headers=auth_headers)
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["status"] == "ready"
    assert body["completeness_score"] == 100
    assert body["blocker_count"] == 0
    assert body["warning_count"] == 0
    assert all(check["status"] == "pass" for check in body["checks"])

    for export_format, extension in (("json", "json"), ("markdown", "md")):
        url = f"/api/v1/applications/{application_id}/readiness/export?format={export_format}"
        first = client.get(url, headers=auth_headers)
        second = client.get(url, headers=auth_headers)
        assert first.status_code == 200, first.text
        assert first.content == second.content
        assert first.headers["x-content-sha256"] == hashlib.sha256(first.content).hexdigest()
        assert first.headers["content-disposition"] == (
            f'attachment; filename="careeros-application-{application_id}-readiness.{extension}"'
        )
        assert first.headers["cache-control"] == "private, no-store"
        decoded = first.content.decode("utf-8")
        assert "private/user/path" not in decoded
        assert "storage_path" not in decoded
        assert "Authorization" not in decoded
        assert "access_token" not in decoded
        assert auth_headers["Authorization"].split()[1] not in decoded
        assert private_description not in decoded
    markdown = client.get(
        f"/api/v1/applications/{application_id}/readiness/export?format=markdown",
        headers=auth_headers,
    ).content
    assert b"preflight completeness index" in markdown
    rendered = markdown.decode("utf-8")
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert r"\[Senior\]\(javascript:alert\(1\)\)" in rendered
    assert r"\*Platform\* \# Engineer Next" in rendered


def test_readiness_warns_when_one_required_artifact_was_never_published(
    client, auth_headers, db_session, test_user, readiness_storage
):
    version_id = _complete_application_pack(db_session, test_user, artifact_formats=("docx",))
    application_id = _ready_application(client, auth_headers, version_id)

    report = client.get(f"/api/v1/applications/{application_id}/readiness", headers=auth_headers)

    assert report.status_code == 200, report.text
    body = report.json()
    assert body["status"] == "action_needed"
    assert body["completeness_score"] == 95
    assert body["blocker_count"] == 0
    assert body["warning_count"] == 1
    artifact_check = next(check for check in body["checks"] if check["id"] == "resume_artifacts")
    assert artifact_check["status"] == "warning"
    assert artifact_check["action"] == "export_resume_files"
    assert {item["key"]: item["value"] for item in artifact_check["evidence"]} == {
        "recorded_formats": "docx",
        "verified_formats": "docx",
        "unavailable_formats": "pdf",
    }


@pytest.mark.parametrize(
    "failure_mode",
    ["deleted", "corrupt", "path_escape", "unreadable", "size_mismatch"],
)
def test_readiness_blocks_recorded_artifacts_without_verified_local_bytes(
    client,
    auth_headers,
    db_session,
    test_user,
    readiness_storage,
    monkeypatch,
    failure_mode,
):
    version_id = _complete_application_pack(db_session, test_user)
    pdf = (
        db_session.query(ResumeArtifact)
        .filter(
            ResumeArtifact.version_id == version_id,
            ResumeArtifact.format == "pdf",
        )
        .one()
    )
    pdf_path = resolve_data_path(pdf.storage_path)
    if failure_mode == "deleted":
        pdf_path.unlink()
    elif failure_mode == "corrupt":
        pdf_path.write_bytes(b"corrupt-pdf")
    elif failure_mode == "path_escape":
        db_session.execute(
            update(ResumeArtifact)
            .where(ResumeArtifact.id == pdf.id)
            .values(storage_path="../outside-vault.pdf")
        )
        db_session.commit()
        db_session.expire_all()
    elif failure_mode == "unreadable":

        def deny_pdf(path, expected_sha256):
            if str(path).endswith(".pdf"):
                raise PermissionError("simulated unreadable artifact")
            return read_verified(path, expected_sha256)

        monkeypatch.setattr("backend.applications.readiness.read_verified", deny_pdf)
    else:
        db_session.execute(
            update(ResumeArtifact)
            .where(ResumeArtifact.id == pdf.id)
            .values(byte_size=pdf.byte_size + 1)
        )
        db_session.commit()
        db_session.expire_all()

    application_id = _ready_application(client, auth_headers, version_id)
    report = client.get(f"/api/v1/applications/{application_id}/readiness", headers=auth_headers)

    assert report.status_code == 200, report.text
    body = report.json()
    assert body["status"] == "blocked"
    assert body["completeness_score"] == 90
    assert body["blocker_count"] == 1
    assert body["warning_count"] == 0
    artifact_check = next(check for check in body["checks"] if check["id"] == "resume_artifacts")
    assert artifact_check["status"] == "blocker"
    assert artifact_check["action"] == "republish_resume_artifacts"
    assert {item["key"]: item["value"] for item in artifact_check["evidence"]} == {
        "recorded_formats": "docx, pdf",
        "verified_formats": "docx",
        "unavailable_formats": "pdf",
    }
    assert "outside-vault" not in report.text
    assert pdf.sha256 not in report.text


def test_preparation_update_resolves_blockers_with_revisioned_audit(
    client, auth_headers, db_session, test_user, readiness_storage
):
    version_id = _complete_application_pack(db_session, test_user)
    created = client.post(
        "/api/v1/applications",
        json={
            "manual_job": {
                "title": "Platform Engineer",
                "company": "Local Systems",
            }
        },
        headers=auth_headers,
    )
    application_id = created.json()["id"]
    description = (
        "Build and operate a local platform, document architecture decisions, improve release "
        "reliability, support incident reviews, and work with product teams on secure delivery."
    )

    updated = client.patch(
        f"/api/v1/applications/{application_id}/preparation",
        json={
            "expected_revision": 1,
            "title": "Senior Platform Engineer",
            "company": "Local Systems AG",
            "description": description,
            "application_url": "HTTPS://EXAMPLE.TEST/apply/../apply/platform#form",
            "application_email": "jobs@example.test",
            "resume_version_id": version_id,
        },
        headers=auth_headers,
    )

    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["revision"] == 2
    assert body["resume_version_id"] == version_id
    assert body["job_snapshot"]["title"] == "Senior Platform Engineer"
    assert body["job_snapshot"]["company"] == "Local Systems AG"
    assert body["job_snapshot"]["description"] == description
    assert body["job_snapshot"]["application_url"] == "https://example.test/apply/platform"
    assert body["job_snapshot"]["application_email"] == "jobs@example.test"
    audit = body["events"][-1]
    assert audit["event_type"] == "preparation"
    assert audit["note"] is None
    assert audit["payload"] == {
        "changed_fields": [
            "application_email",
            "application_url",
            "company",
            "description",
            "resume_version_id",
            "title",
        ]
    }
    assert description not in str(audit["payload"])
    readiness = client.get(f"/api/v1/applications/{application_id}/readiness", headers=auth_headers)
    assert readiness.json()["status"] == "ready"
    assert readiness.json()["completeness_score"] == 100
    listing = client.get("/api/v1/applications", headers=auth_headers).json()[0]
    assert listing["title"] == "Senior Platform Engineer"
    assert listing["company"] == "Local Systems AG"
    stored = _assert_application_projections(
        db_session,
        application_id,
        title="Senior Platform Engineer",
        company="Local Systems AG",
        location=None,
    )
    assert listing["latest_event_at"] == stored.latest_event_at.isoformat().replace("+00:00", "Z")

    stale = client.patch(
        f"/api/v1/applications/{application_id}/preparation",
        json={"expected_revision": 1, "description": "A stale overwrite attempt."},
        headers=auth_headers,
    )
    assert stale.status_code == 409
    loaded = client.get(f"/api/v1/applications/{application_id}", headers=auth_headers).json()
    assert loaded["revision"] == 2
    assert loaded["job_snapshot"]["description"] == description
    assert [event["event_type"] for event in loaded["events"]].count("preparation") == 1


def test_preparation_update_validates_changes_and_owned_resume(client, auth_headers):
    created = client.post(
        "/api/v1/applications",
        json={"manual_job": {"title": "Role", "company": "Company"}},
        headers=auth_headers,
    )
    application_id = created.json()["id"]
    assert (
        client.patch(
            f"/api/v1/applications/{application_id}/preparation",
            json={"expected_revision": 1},
            headers=auth_headers,
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/applications/{application_id}/preparation",
            json={"expected_revision": 1, "application_url": "file:///private/resume.pdf"},
            headers=auth_headers,
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/applications/{application_id}/preparation",
            json={"expected_revision": 1, "application_email": "not-an-email"},
            headers=auth_headers,
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/applications/{application_id}/preparation",
            json={
                "expected_revision": 1,
                "resume_version_id": "00000000-0000-0000-0000-000000000000",
            },
            headers=auth_headers,
        ).status_code
        == 422
    )


def test_readiness_hides_another_users_application(client, auth_headers, db_session, test_user):
    created = client.post(
        "/api/v1/applications",
        json={"manual_job": {"title": "Private role", "company": "Private company"}},
        headers=auth_headers,
    )
    application_id = created.json()["id"]
    other = User(username="other-user", hashed_password=get_password_hash("Otherpass1"))
    db_session.add(other)
    db_session.commit()
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "other-user", "password": "Otherpass1"},
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert (
        client.get(
            f"/api/v1/applications/{application_id}/readiness", headers=other_headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/applications/{application_id}/readiness/export",
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/applications/{application_id}/preparation",
            json={"expected_revision": 1, "description": "Foreign update"},
            headers=other_headers,
        ).status_code
        == 404
    )


def test_application_tasks_are_append_only_and_export_as_local_calendar(
    client, auth_headers, db_session
):
    created = client.post(
        "/api/v1/applications",
        json={"manual_job": {"title": "Platform Engineer", "company": "Local Systems"}},
        headers=auth_headers,
    ).json()
    application_id = created["id"]
    due_at = "2026-08-01T09:00:00+02:00"
    reminder_at = "2026-08-01T08:30:00+02:00"

    task_response = client.post(
        f"/api/v1/applications/{application_id}/tasks",
        json={
            "expected_revision": 1,
            "title": "Send tailored application",
            "due_at": due_at,
            "reminder_at": reminder_at,
            "priority": "high",
        },
        headers=auth_headers,
    )

    assert task_response.status_code == 201, task_response.text
    body = task_response.json()
    assert body["revision"] == 2
    assert len(body["tasks"]) == 1
    task = body["tasks"][0]
    assert task["status"] == "pending"
    assert task["priority"] == "high"
    assert task["due_at"] == "2026-08-01T07:00:00Z"
    assert task["reminder_at"] == "2026-08-01T06:30:00Z"
    assert body["events"][-1]["event_type"] == "task_created"
    listing = client.get("/api/v1/applications", headers=auth_headers).json()[0]
    assert listing["next_action"]["id"] == task["id"]
    assert listing["next_action"]["title"] == "Send tailored application"
    assert listing["next_action"]["due_at"] == "2026-08-01T07:00:00Z"
    assert listing["title"] == "Platform Engineer"
    assert listing["company"] == "Local Systems"
    stored = _assert_application_projections(
        db_session,
        application_id,
        title="Platform Engineer",
        company="Local Systems",
        location=None,
    )
    assert listing["latest_event_at"] == stored.latest_event_at.isoformat().replace("+00:00", "Z")
    detail = client.get(f"/api/v1/applications/{application_id}", headers=auth_headers).json()
    assert detail["tasks"][0]["due_at"] == "2026-08-01T07:00:00Z"
    assert detail["events"][-1]["occurred_at"].endswith("Z")

    calendar = client.get(
        f"/api/v1/applications/{application_id}/tasks/calendar.ics",
        headers=auth_headers,
    )
    assert calendar.status_code == 200, calendar.text
    assert calendar.headers["cache-control"] == "private, no-store"
    assert calendar.headers["x-content-sha256"] == hashlib.sha256(calendar.content).hexdigest()
    text = calendar.content.decode("utf-8")
    assert "BEGIN:VCALENDAR\r\n" in text
    assert "SUMMARY:Send tailored application" in text
    assert "DTSTART:20260801T070000Z" in text
    assert "TRIGGER:-PT1800S" in text

    completed = client.patch(
        f"/api/v1/applications/{application_id}/tasks/{task['id']}",
        json={"expected_revision": 2, "status": "completed"},
        headers=auth_headers,
    )
    assert completed.status_code == 200, completed.text
    completed_body = completed.json()
    assert completed_body["revision"] == 3
    assert completed_body["tasks"][0]["status"] == "completed"
    assert completed_body["tasks"][0]["completed_at"] is not None
    assert completed_body["events"][-1]["event_type"] == "task_completed"
    assert client.get("/api/v1/applications", headers=auth_headers).json()[0]["next_action"] is None
    completed_listing = client.get("/api/v1/applications", headers=auth_headers).json()[0]
    stored = _assert_application_projections(
        db_session,
        application_id,
        title="Platform Engineer",
        company="Local Systems",
        location=None,
    )
    assert completed_listing["latest_event_at"] == stored.latest_event_at.isoformat().replace(
        "+00:00", "Z"
    )

    task_events = (
        db_session.query(ApplicationEvent)
        .filter(ApplicationEvent.application_id == application_id)
        .filter(ApplicationEvent.event_type.like("task_%"))
        .all()
    )
    assert [event.event_type for event in task_events] == ["task_created", "task_completed"]


def test_application_task_schedule_validation_and_revision_conflicts(client, auth_headers):
    application = client.post(
        "/api/v1/applications",
        json={"manual_job": {"title": "Role", "company": "Company"}},
        headers=auth_headers,
    ).json()
    endpoint = f"/api/v1/applications/{application['id']}/tasks"
    assert (
        client.post(
            endpoint,
            json={
                "expected_revision": 1,
                "title": "Invalid reminder",
                "reminder_at": "2026-08-01T08:30:00Z",
            },
            headers=auth_headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            endpoint,
            json={"expected_revision": 1, "title": "   "},
            headers=auth_headers,
        ).status_code
        == 422
    )
    valid = client.post(
        endpoint,
        json={"expected_revision": 1, "title": "Research team"},
        headers=auth_headers,
    )
    assert valid.status_code == 201
    assert (
        client.post(
            endpoint,
            json={"expected_revision": 1, "title": "Stale task"},
            headers=auth_headers,
        ).status_code
        == 409
    )
    task = valid.json()["tasks"][0]
    assert (
        client.patch(
            f"{endpoint}/{task['id']}",
            json={"expected_revision": 2, "status": None},
            headers=auth_headers,
        ).status_code
        == 422
    )


def test_application_dossier_is_versioned_and_zip_manifest_is_verifiable(
    client, auth_headers, db_session, test_user, readiness_storage
):
    version_id = _complete_application_pack(db_session, test_user)
    application_id = _ready_application(client, auth_headers, version_id)
    version = db_session.query(ResumeVersion).filter(ResumeVersion.id == version_id).one()
    evidence_id = version.selected_fact_ids[0]

    published = client.post(
        f"/api/v1/applications/{application_id}/dossiers",
        json={
            "expected_revision": 1,
            "cover_letter": "I build dependable local systems and can explain the trade-offs.",
            "answers": [
                {"question": "Why this role?", "answer": "The engineering scope matches my work."}
            ],
            "checklist": [
                {"label": "Resume reviewed", "completed": True},
                {"label": "References available", "completed": False},
            ],
            "requirement_matrix": [
                {
                    "requirement": "Operate dependable platforms",
                    "evidence_fact_ids": [evidence_id],
                }
            ],
        },
        headers=auth_headers,
    )

    assert published.status_code == 201, published.text
    body = published.json()
    assert body["revision"] == 2
    assert body["events"][-1]["event_type"] == "dossier_published"
    assert len(body["dossiers"]) == 1
    dossier = body["dossiers"][0]
    assert dossier["version_number"] == 1
    assert dossier["application_revision"] == 2
    assert dossier["completed_checklist"] == 1
    assert dossier["checklist_total"] == 2

    url = f"/api/v1/applications/{application_id}/dossiers/{dossier['id']}/download"
    first = client.get(url, headers=auth_headers)
    second = client.get(url, headers=auth_headers)
    assert first.status_code == 200, first.text
    assert first.content == second.content
    assert first.headers["x-content-sha256"] == hashlib.sha256(first.content).hexdigest()
    with zipfile.ZipFile(io.BytesIO(first.content)) as archive:
        names = archive.namelist()
        assert names == sorted(names[:-1]) + ["manifest.json"]
        assert {"resume.pdf", "resume.docx", "manifest.json"} <= set(names)
        manifest_bytes = archive.read("manifest.json")
        manifest = json.loads(manifest_bytes)
        assert hashlib.sha256(manifest_bytes).hexdigest() == dossier["manifest_sha256"]
        assert first.headers["x-dossier-manifest-sha256"] == dossier["manifest_sha256"]
        for entry in manifest["entries"]:
            payload = archive.read(entry["path"])
            assert len(payload) == entry["byte_size"]
            assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
        application_record = json.loads(archive.read("application.json"))
        assert application_record["readiness"]["score_kind"] == "preflight_completeness"
        assert "prediction" not in json.dumps(application_record).casefold()
        evidence_record = json.loads(archive.read("requirement-evidence.json"))
        assert evidence_record["schema_version"] == "2.0"
        assert len(evidence_record["evidence_catalog"]) == 1
        assert evidence_record["requirements"] == [
            {
                "requirement": "Operate dependable platforms",
                "evidence_fact_ids": [evidence_id],
            }
        ]
        assert "snapshot" not in evidence_record["requirements"][0]

    dossier_event = (
        db_session.query(ApplicationEvent).filter(ApplicationEvent.id == dossier["id"]).one()
    )
    persisted_dossier = dossier_event.payload["dossier"]
    assert persisted_dossier["schema_version"] == "2.0"
    assert len(persisted_dossier["evidence_catalog"]) == 1
    listing = client.get("/api/v1/applications", headers=auth_headers).json()[0]
    stored = _assert_application_projections(
        db_session,
        application_id,
        title="Senior Platform Engineer",
        company="Local Systems AG",
        location=None,
    )
    assert listing["latest_event_at"] == stored.latest_event_at.isoformat().replace("+00:00", "Z")

    stale = client.post(
        f"/api/v1/applications/{application_id}/dossiers",
        json={
            "expected_revision": 1,
            "requirement_matrix": [
                {"requirement": "A requirement", "evidence_fact_ids": [evidence_id]}
            ],
        },
        headers=auth_headers,
    )
    assert stale.status_code == 409


def test_application_dossier_rejects_oversized_deduplicated_event_before_commit(
    client, auth_headers, db_session, test_user, readiness_storage
):
    version_id = _complete_application_pack(db_session, test_user)
    application_id = _ready_application(client, auth_headers, version_id)
    version = db_session.query(ResumeVersion).filter(ResumeVersion.id == version_id).one()
    snapshot = json.loads(json.dumps(version.snapshot))
    evidence_id = version.selected_fact_ids[0]
    snapshot["facts"][0]["oversized_local_evidence"] = "x" * 600_000
    db_session.execute(
        update(ResumeVersion).where(ResumeVersion.id == version_id).values(snapshot=snapshot)
    )
    db_session.commit()

    response = client.post(
        f"/api/v1/applications/{application_id}/dossiers",
        json={
            "expected_revision": 1,
            "requirement_matrix": [
                {
                    "requirement": "Operate dependable platforms",
                    "evidence_fact_ids": [evidence_id],
                }
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert "Dossier event exceeds" in response.text
    detail = client.get(f"/api/v1/applications/{application_id}", headers=auth_headers).json()
    assert detail["revision"] == 1
    assert detail["dossiers"] == []


@pytest.mark.parametrize(
    "body",
    [
        {
            "expected_revision": 1,
            "requirement_matrix": [
                {"requirement": "A requirement", "evidence_fact_ids": ["not-a-uuid"]}
            ],
        },
        {
            "expected_revision": 1,
            "requirement_matrix": [
                {
                    "requirement": "A requirement",
                    "evidence_fact_ids": ["10000000-0000-4000-8000-000000000001"],
                    "unexpected": "rejected",
                }
            ],
        },
        {
            "expected_revision": 1,
            "requirement_matrix": [
                {
                    "requirement": "A requirement",
                    "evidence_fact_ids": [
                        "10000000-0000-4000-8000-000000000001",
                        "10000000-0000-4000-8000-000000000001",
                    ],
                }
            ],
        },
    ],
)
def test_dossier_schema_rejects_unbounded_or_ambiguous_evidence_ids(client, auth_headers, body):
    created = client.post(
        "/api/v1/applications",
        json={"manual_job": {"title": "Role", "company": "Company"}},
        headers=auth_headers,
    ).json()
    response = client.post(
        f"/api/v1/applications/{created['id']}/dossiers",
        json=body,
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_manual_application_snapshot_forbids_extra_fields(client, auth_headers):
    response = client.post(
        "/api/v1/applications",
        json={
            "manual_job": {
                "title": "Role",
                "company": "Company",
                "private_unbounded_blob": "not accepted",
            }
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_application_api_rejects_unbounded_event_json_and_unknown_fields(client, auth_headers):
    created = client.post(
        "/api/v1/applications",
        json={"manual_job": {"title": "Role", "company": "Company"}},
        headers=auth_headers,
    ).json()
    endpoint = f"/api/v1/applications/{created['id']}/events"

    oversized = client.post(
        endpoint,
        json={
            "expected_revision": 1,
            "event_type": "task",
            "payload": {"blob": "x" * 2_000_000},
        },
        headers=auth_headers,
    )
    assert oversized.status_code == 422

    extra = client.post(
        endpoint,
        json={
            "expected_revision": 1,
            "event_type": "task",
            "payload": {},
            "unexpected": "rejected",
        },
        headers=auth_headers,
    )
    assert extra.status_code == 422

    nested: dict = {}
    cursor = nested
    for _index in range(10):
        cursor["child"] = {}
        cursor = cursor["child"]
    too_deep = client.post(
        endpoint,
        json={
            "expected_revision": 1,
            "event_type": "task",
            "payload": nested,
        },
        headers=auth_headers,
    )
    assert too_deep.status_code == 422

    too_many_nodes = client.post(
        endpoint,
        json={
            "expected_revision": 1,
            "event_type": "task",
            "payload": {"items": list(range(1_001))},
        },
        headers=auth_headers,
    )
    assert too_many_nodes.status_code == 422


def test_application_api_validates_uuid_inputs(client, auth_headers):
    assert client.get("/api/v1/applications/not-a-uuid", headers=auth_headers).status_code == 422
    assert (
        client.post(
            "/api/v1/applications",
            json={
                "manual_job": {"title": "Role", "company": "Company"},
                "resume_version_id": "not-a-uuid",
            },
            headers=auth_headers,
        ).status_code
        == 422
    )
    missing = "10000000-0000-4000-8000-000000000001"
    assert client.get(f"/api/v1/applications/{missing}", headers=auth_headers).status_code == 404


def test_dossier_schema_caps_aggregate_evidence_links(client, auth_headers):
    created = client.post(
        "/api/v1/applications",
        json={"manual_job": {"title": "Role", "company": "Company"}},
        headers=auth_headers,
    ).json()
    evidence = [f"10000000-0000-4000-8000-{index:012d}" for index in range(5)]
    response = client.post(
        f"/api/v1/applications/{created['id']}/dossiers",
        json={
            "expected_revision": 1,
            "requirement_matrix": [
                {
                    "requirement": f"Requirement {index}",
                    "evidence_fact_ids": evidence,
                }
                for index in range(21)
            ],
        },
        headers=auth_headers,
    )
    assert response.status_code == 422
