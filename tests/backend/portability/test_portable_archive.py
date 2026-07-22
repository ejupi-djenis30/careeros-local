import errno
import hashlib
import json
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.ai.audit import fingerprint_output
from backend.ai.contracts import CoachResult
from backend.ai.models import AIExecution
from backend.applications.models import Application, ApplicationEvent
from backend.career.coach_models import CoachConversation, CoachMessage
from backend.career.models import CandidateProfile, CareerAsset
from backend.core.config import settings
from backend.models import Job, ScrapedJob, SearchProfile, User
from backend.portability import archive as archive_module
from backend.resumes.models import ResumeArtifact, ResumeDraft, ResumeVersion
from backend.storage import atomic
from backend.storage.atomic import atomic_write, resolve_data_path
from backend.workflows.models import WorkflowRun


def _profile_payload():
    return {
        "expected_revision": 0,
        "display_name": "Mira Vale",
        "headline": "Computing pioneer",
        "summary": "Builds rigorous analytical systems.",
        "email": "mira@example.test",
        "location": {"city": "Zurich", "country": "CH"},
        "preferences": {"workload_min": 80, "workload_max": 100},
        "facts": [
            {
                "fact_type": "skill",
                "position": 0,
                "verification_status": "confirmed",
                "payload": {"name": "Python", "level": "expert", "years": 8},
            }
        ],
        "goals": [
            {
                "name": "Local systems",
                "is_primary": True,
                "payload": {"target_roles": ["Staff Engineer"]},
            }
        ],
    }


@pytest.fixture
def portable_data_dir(monkeypatch):
    with TemporaryDirectory() as directory:
        path = Path(directory)
        monkeypatch.setattr(settings, "DATA_DIR", str(path))
        yield path


def _seed_related_records(db, user_id: int, profile_id: str, fact_id: str) -> str:
    now = datetime.now(timezone.utc)
    draft_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    artifact_id = str(uuid.uuid4())
    artifact_data = b"%PDF-1.4\nportable-fixture"
    digest = hashlib.sha256(artifact_data).hexdigest()
    artifact_path = f"resumes/{profile_id}/{version_id}/{digest}.pdf"
    atomic_write(artifact_path, artifact_data)
    draft = ResumeDraft(
        id=draft_id,
        profile_id=profile_id,
        revision=1,
        profile_revision=1,
        title="Portable ATS CV",
        template_kind="ats",
        section_config={"order": ["skill"]},
        selected_fact_ids=[fact_id],
        content_overrides={},
    )
    version = ResumeVersion(
        id=version_id,
        draft_id=draft_id,
        version_number=1,
        semantic_version="1.0.0",
        snapshot={"display_name": "Mira Vale"},
        snapshot_sha256="0" * 64,
        profile_revision=1,
        selected_fact_ids=[fact_id],
        template_kind="ats",
        renderer_version="1.0",
        published_at=now,
        quality_report={"passed": True, "page_count": 1},
    )
    artifact = ResumeArtifact(
        id=artifact_id,
        version_id=version_id,
        format="pdf",
        media_type="application/pdf",
        sha256=digest,
        byte_size=len(artifact_data),
        storage_path=artifact_path,
        created_at=now,
    )
    application_id = str(uuid.uuid4())
    application = Application(
        id=application_id,
        user_id=user_id,
        job_id=None,
        resume_version_id=version_id,
        revision=1,
        current_stage="applied",
        job_snapshot={
            "title": "Backend Engineer",
            "company": "Local Co",
            "location": "Zurich",
        },
        job_title="Backend Engineer",
        job_company="Local Co",
        job_location="Zurich",
        latest_event_at=now,
    )
    event = ApplicationEvent(
        id=str(uuid.uuid4()),
        application_id=application_id,
        event_type="stage",
        stage="applied",
        occurred_at=now,
        note="Submitted locally",
        payload={},
        created_at=now,
    )
    conversation_id = str(uuid.uuid4())
    conversation = CoachConversation(
        id=conversation_id, profile_id=profile_id, title="Career direction"
    )
    message = CoachMessage(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role="assistant",
        content="Python is a verified strength.",
        cited_fact_ids=[fact_id],
        cited_job_ids=[],
        model_id="qwen3:4b",
        generation_metadata={"local": True},
        created_at=now,
    )
    workflow = WorkflowRun(
        id=str(uuid.uuid4()),
        user_id=user_id,
        workflow_type="resume_publish",
        idempotency_key=str(uuid.uuid4()),
        status="succeeded",
        payload={"resume_id": draft_id},
        checkpoint={"step": "done"},
        result_reference={"version_id": version_id},
        progress=1.0,
        attempt_count=1,
        max_attempts=3,
        finished_at=now,
    )
    db.add(draft)
    db.flush()
    db.add(version)
    db.flush()
    db.add(artifact)
    db.flush()
    db.add(application)
    db.flush()
    db.add(event)
    db.add(conversation)
    db.flush()
    db.add(message)
    db.add(workflow)
    db.commit()
    return artifact_path


def _seed_verified_coach_records(
    db, user_id: int, profile_id: str, fact_id: str
) -> tuple[str, str, CoachResult]:
    now = datetime.now(timezone.utc)
    model_id = "ollama-local/verified-coach"
    result = CoachResult.model_validate(
        {
            "answer": "Python is a verified strength for this direction.",
            "claims": [
                {
                    "text": "Python is a verified strength for this direction.",
                    "fact_ids": [fact_id],
                    "job_ids": [],
                }
            ],
            "fact_citations": [fact_id],
            "job_citations": [],
            "confidence": 0.91,
            "missing_evidence": [],
        }
    )
    output_fingerprint = fingerprint_output(result)
    execution = AIExecution(
        user_id=user_id,
        task="coach",
        contract_version="1.0.0",
        model_id=model_id,
        input_fingerprint="a" * 64,
        output_fingerprint=output_fingerprint,
        row_fingerprints=[],
        row_input_fingerprints=[],
        evidence_count=1,
        accepted=True,
        repair_count=0,
        validation_codes=[],
        duration_ms=2,
    )
    db.add(execution)
    db.flush()
    conversation = CoachConversation(
        id=str(uuid.uuid4()),
        profile_id=profile_id,
        title="Verified coach history",
    )
    db.add(conversation)
    db.flush()
    db.add_all(
        [
            CoachMessage(
                id=str(uuid.uuid4()),
                conversation_id=conversation.id,
                role="user",
                content="Which verified strength should I emphasize?",
                cited_fact_ids=[],
                cited_job_ids=[],
                model_id=None,
                generation_metadata={},
                created_at=now,
            ),
            CoachMessage(
                id=str(uuid.uuid4()),
                conversation_id=conversation.id,
                role="assistant",
                content=result.answer,
                cited_fact_ids=result.fact_citations,
                cited_job_ids=result.job_citations,
                model_id=model_id,
                generation_metadata={
                    "mode": "local",
                    "claims": [claim.model_dump(mode="json") for claim in result.claims],
                    "confidence": result.confidence,
                    "missing_evidence": result.missing_evidence,
                    "provenance": "local_model_validated",
                    "contract_version": "1.0.0",
                    "execution_id": execution.id,
                    "output_fingerprint": output_fingerprint,
                },
                created_at=now + timedelta(microseconds=1),
            ),
        ]
    )
    db.commit()
    return conversation.id, execution.id, result


def _tamper_payload(archive_data: bytes) -> bytes:
    source = zipfile.ZipFile(BytesIO(archive_data), "r")
    output = BytesIO()
    with source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "payload.json":
                data += b" "
            target.writestr(info.filename, data)
    return output.getvalue()


def _rewrite_forged_coach_message(archive_data: bytes) -> bytes:
    with zipfile.ZipFile(BytesIO(archive_data), "r") as source:
        files = {name: source.read(name) for name in source.namelist()}
    payload = json.loads(files["payload.json"])
    payload["tables"]["coach_messages"][0].update(
        {
            "content": "Forged authoritative executive advice.",
            "cited_fact_ids": ["00000000-0000-4000-8000-000000000000"],
            "model_id": "forged/model",
            "generation_metadata": {
                "provenance": "local_model_validated",
                "contract_version": "1.0.0",
                "execution_id": "00000000-0000-4000-8000-000000000001",
                "output_fingerprint": "f" * 64,
            },
        }
    )
    files["payload.json"] = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    manifest = json.loads(files["manifest.json"])
    payload_entry = next(entry for entry in manifest["entries"] if entry["path"] == "payload.json")
    payload_entry["byte_size"] = len(files["payload.json"])
    payload_entry["sha256"] = hashlib.sha256(files["payload.json"]).hexdigest()
    files["manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for name, content in files.items():
            target.writestr(name, content)
    return output.getvalue()


def _rewrite_application_job(archive_data: bytes, job_id: int) -> bytes:
    with zipfile.ZipFile(BytesIO(archive_data), "r") as source:
        files = {name: source.read(name) for name in source.namelist()}
    payload = json.loads(files["payload.json"])
    payload["tables"]["applications"][0]["job_id"] = job_id
    files["payload.json"] = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    manifest = json.loads(files["manifest.json"])
    payload_entry = next(entry for entry in manifest["entries"] if entry["path"] == "payload.json")
    payload_entry["byte_size"] = len(files["payload.json"])
    payload_entry["sha256"] = hashlib.sha256(files["payload.json"]).hexdigest()
    files["manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for name, content in files.items():
            target.writestr(name, content)
    return output.getvalue()


APPLICATION_PROJECTION_FIELDS = {
    "job_title",
    "job_company",
    "job_location",
    "latest_event_at",
    "next_action_task_id",
    "next_action_title",
    "next_action_at",
    "next_action_priority",
}


def _rewrite_application_projection_fixture(
    archive_data: bytes,
    *,
    format_version: int = 4,
    remove_projections: bool = False,
    projection_overrides: dict | None = None,
) -> bytes:
    with zipfile.ZipFile(BytesIO(archive_data), "r") as source:
        files = {name: source.read(name) for name in source.namelist()}
    payload = json.loads(files["payload.json"])
    application = payload["tables"]["applications"][0]
    if remove_projections:
        for field in APPLICATION_PROJECTION_FIELDS:
            application.pop(field, None)
    if projection_overrides:
        application.update(projection_overrides)

    removed_tables: list[str] = []
    if format_version < 3:
        removed_tables.extend(["search_profiles", "scraped_jobs", "jobs", "preference_signals"])
    if format_version < 2:
        removed_tables.append("ai_executions")
    for table_name in removed_tables:
        payload["tables"].pop(table_name)
    if format_version == 3 and "jobs" in payload["tables"]:
        for row in payload["tables"]["jobs"]:
            for field in (
                "source_query",
                "analysis_provenance",
                "analysis_model_id",
                "analysis_contract_version",
                "analysis_validated_at",
                "analysis_legacy_snapshot",
            ):
                row.pop(field, None)

    files["payload.json"] = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    manifest = json.loads(files["manifest.json"])
    manifest["format_version"] = format_version
    for table_name in removed_tables:
        manifest["record_counts"].pop(table_name)
    payload_entry = next(entry for entry in manifest["entries"] if entry["path"] == "payload.json")
    payload_entry["byte_size"] = len(files["payload.json"])
    payload_entry["sha256"] = hashlib.sha256(files["payload.json"]).hexdigest()
    files["manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for name, content in files.items():
            target.writestr(name, content)
    return output.getvalue()


def _rewrite_legacy_v3_private_and_runtime_fields(archive_data: bytes, source_query: str) -> bytes:
    with zipfile.ZipFile(BytesIO(archive_data), "r") as source:
        files = {name: source.read(name) for name in source.namelist()}
    payload = json.loads(files["payload.json"])
    for row in payload["tables"]["jobs"]:
        for field in (
            "source_query",
            "analysis_provenance",
            "analysis_model_id",
            "analysis_contract_version",
            "analysis_validated_at",
            "analysis_legacy_snapshot",
        ):
            row.pop(field, None)
    payload["tables"]["scraped_jobs"][0]["source_query"] = source_query
    payload["tables"]["search_profiles"][0].update(
        {
            "search_lock_token": "legacy-private-token",
            "search_lock_state": "active",
            "search_lock_acquired_at": "2026-07-01T09:30:00+00:00",
            "search_status_state": "matching",
            "search_status_payload": {"query": "legacy private runtime query"},
            "search_status_started_at": "2026-07-01T09:30:00+00:00",
            "search_status_updated_at": "2026-07-01T09:31:00+00:00",
            "search_status_finished_at": None,
        }
    )
    files["payload.json"] = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    manifest = json.loads(files["manifest.json"])
    manifest["format_version"] = 3
    payload_entry = next(entry for entry in manifest["entries"] if entry["path"] == "payload.json")
    payload_entry["byte_size"] = len(files["payload.json"])
    payload_entry["sha256"] = hashlib.sha256(files["payload.json"]).hexdigest()
    files["manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for name, content in files.items():
            target.writestr(name, content)
    return output.getvalue()


def _rewrite_legacy_v3_heuristic_match(archive_data: bytes) -> bytes:
    with zipfile.ZipFile(BytesIO(archive_data), "r") as source:
        files = {name: source.read(name) for name in source.namelist()}
    payload = json.loads(files["payload.json"])
    for field in (
        "analysis_provenance",
        "analysis_model_id",
        "analysis_contract_version",
        "analysis_validated_at",
        "analysis_legacy_snapshot",
    ):
        payload["tables"]["jobs"][0].pop(field, None)
    payload["tables"]["jobs"][0].update(
        {
            "affinity_score": 94,
            "affinity_analysis": "Legacy heuristic fit",
            "worth_applying": True,
            "skill_match_score": 90,
            "analysis_structured": {
                "mode": "deterministic_local",
                "verdict": "strong",
            },
            "red_flags": ["legacy"],
        }
    )
    payload["tables"]["applications"][0]["job_snapshot"].update(
        {
            "affinity_analysis": "Legacy top-level application claim",
            "match": {
                "score": 100,
                "analysis": "Legacy embedded application claim",
                "worth_applying": True,
                "receipt_verified": True,
            },
        }
    )
    files["payload.json"] = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    manifest = json.loads(files["manifest.json"])
    manifest["format_version"] = 3
    payload_entry = next(entry for entry in manifest["entries"] if entry["path"] == "payload.json")
    payload_entry["byte_size"] = len(files["payload.json"])
    payload_entry["sha256"] = hashlib.sha256(files["payload.json"]).hexdigest()
    files["manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for name, content in files.items():
            target.writestr(name, content)
    return output.getvalue()


def _seed_search_portability_records(db, user_id: int):
    updated_at = datetime(2026, 7, 1, 9, 30, tzinfo=timezone.utc)
    signals = {
        "preferred_domains": {"it": 0.9},
        "preferred_skills": ["python"],
        "signal_count": 7,
    }
    owner = db.get(User, user_id)
    owner.preference_signals = signals
    owner.preference_updated_at = updated_at
    profile = SearchProfile(
        user_id=user_id,
        name="Portable backend search",
        role_description="Local Python systems",
        advanced_preferences={"remote_only": True},
        search_lock_token="private-runtime-token",
        search_lock_state="active",
        search_lock_acquired_at=updated_at,
        search_status_state="matching",
        search_status_payload={"query": "private runtime query", "completed": 3},
        search_status_started_at=updated_at,
        search_status_updated_at=updated_at,
        search_status_finished_at=updated_at,
    )
    scraped = ScrapedJob(
        platform="portable-test",
        platform_job_id="listing-42",
        title="Local Backend Engineer",
        company="Portable Co",
        description="Build local-first systems.",
        location="Zurich",
        external_url="https://example.test/jobs/42",
        normalized_domain="it",
    )
    db.add_all([profile, scraped])
    db.flush()
    job = Job(
        user_id=user_id,
        search_profile_id=profile.id,
        scraped_job_id=scraped.id,
        source_query="private Python search terms",
        affinity_score=93.0,
        affinity_analysis=(
            "Local evidence review: strong fit. 2 supported strength(s), 0 supported "
            "gap(s), 0 risk signal(s). Evidence dimensions: experience, skill."
        ),
        worth_applying=True,
        skill_match_score=95,
        experience_match_score=92,
        intent_match_score=90,
        language_match_score=85,
        location_match_score=90,
        transferability_score=88,
        qualification_gap_score=90,
        analysis_structured={
            "recommendation": "strong_fit",
            "evidence_citations": [
                {
                    "type": "skill",
                    "assessment": "strength",
                    "job_evidence_id": "job:0",
                    "candidate_evidence_id": "candidate:profile",
                    "job_evidence": "local-first systems",
                    "candidate_evidence": "production Python services",
                },
                {
                    "type": "experience",
                    "assessment": "strength",
                    "job_evidence_id": "job:0",
                    "candidate_evidence_id": "candidate:profile",
                    "job_evidence": "Backend Engineer",
                    "candidate_evidence": "Backend engineering experience",
                },
            ],
        },
        analysis_provenance="local_model_validated",
        analysis_model_id="llama-cpp-local/test-model",
        analysis_contract_version="1.1.0",
        analysis_validated_at=updated_at,
        applied=True,
        feedback_signal="already_applied",
    )
    db.add(job)
    db.flush()
    application = Application(
        id=str(uuid.uuid4()),
        user_id=user_id,
        job_id=job.id,
        revision=1,
        current_stage="applied",
        job_snapshot={
            "title": scraped.title,
            "company": scraped.company,
            "location": scraped.location,
            "affinity_analysis": "forged top-level snapshot claim",
            "raw_metadata": {"analysis": "raw unverified provider metadata claim"},
            "match": {
                "score": 93.0,
                "analysis": "raw unverified application snapshot claim",
                "worth_applying": True,
                "receipt_verified": True,
            },
        },
        job_title=scraped.title,
        job_company=scraped.company,
        job_location=scraped.location,
        latest_event_at=updated_at,
    )
    db.add(application)
    db.flush()
    db.add(
        ApplicationEvent(
            application_id=application.id,
            event_type="stage",
            stage="applied",
            occurred_at=updated_at,
            note=None,
            payload={"initial": True},
            created_at=updated_at,
        )
    )
    db.commit()
    return profile.id, scraped.id, job.id, application.id, signals


def _clear_search_records(db, user_id: int, scraped_job_id: int) -> None:
    db.query(Job).filter(Job.user_id == user_id).delete(synchronize_session=False)
    db.query(SearchProfile).filter(SearchProfile.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(ScrapedJob).filter(ScrapedJob.id == scraped_job_id).delete(synchronize_session=False)
    owner = db.get(User, user_id)
    owner.preference_signals = None
    owner.preference_updated_at = None
    db.commit()


def _seed_portable_application_via_api(client, auth_headers) -> tuple[dict, dict]:
    profile = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert profile.status_code == 200, profile.text
    created = client.post(
        "/api/v1/applications",
        json={
            "manual_job": {
                "title": "Reliability Engineer",
                "company": "Northstar Systems",
                "location": "Zurich",
            },
            "initial_stage": "preparing",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    application = created.json()
    task_response = client.post(
        f"/api/v1/applications/{application['id']}/tasks",
        json={
            "expected_revision": 1,
            "title": "Review the application pack",
            "due_at": "2026-08-01T09:00:00+02:00",
            "priority": "high",
        },
        headers=auth_headers,
    )
    assert task_response.status_code == 201, task_response.text
    return task_response.json(), task_response.json()["tasks"][0]


@pytest.mark.parametrize("format_version", [1, 2, 3, 4])
def test_historical_archive_rebuilds_application_projections_after_events(
    client,
    auth_headers,
    db_session,
    test_user,
    portable_data_dir,
    format_version,
):
    application, task = _seed_portable_application_via_api(client, auth_headers)
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    legacy = _rewrite_application_projection_fixture(
        exported.content,
        format_version=format_version,
        remove_projections=True,
    )
    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text

    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": (f"historical-v{format_version}.zip", legacy, "application/zip")},
        headers=auth_headers,
    )

    assert restored.status_code == 200, restored.text
    assert restored.json()["format_version"] == format_version
    db_session.expire_all()
    stored = db_session.get(Application, application["id"])
    assert stored is not None
    assert stored.job_title == "Reliability Engineer"
    assert stored.job_company == "Northstar Systems"
    assert stored.job_location == "Zurich"
    assert stored.latest_event_at == max(event.occurred_at for event in stored.events)
    assert stored.next_action_task_id == task["id"]
    assert stored.next_action_title == "Review the application pack"
    assert stored.next_action_at == datetime(2026, 8, 1, 7, 0, tzinfo=timezone.utc)
    assert stored.next_action_priority == "high"


def test_modern_v4_archive_rejects_inconsistent_application_projections(
    client, auth_headers, db_session, test_user, portable_data_dir
):
    application, _task = _seed_portable_application_via_api(client, auth_headers)
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    inconsistent = _rewrite_application_projection_fixture(
        exported.content,
        projection_overrides={
            "job_title": "Tampered role",
            "job_company": "Tampered company",
            "job_location": "Elsewhere",
            "latest_event_at": "2020-01-01T00:00:00Z",
            "next_action_task_id": "00000000-0000-4000-8000-000000000000",
            "next_action_title": "Tampered task",
            "next_action_at": "2020-01-01T00:00:00Z",
            "next_action_priority": "low",
        },
    )
    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text

    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("inconsistent-v3.zip", inconsistent, "application/zip")},
        headers=auth_headers,
    )

    assert restored.status_code == 422, restored.text
    assert "projections are inconsistent" in restored.json()["detail"]
    db_session.expire_all()
    assert db_session.get(Application, application["id"]) is None
    assert (
        db_session.query(CandidateProfile).filter(CandidateProfile.user_id == test_user.id).count()
        == 0
    )


def test_export_delete_restore_round_trip(
    client, auth_headers, db_session, test_user, portable_data_dir
):
    profile_response = client.put(
        "/api/v1/career-profile", json=_profile_payload(), headers=auth_headers
    )
    assert profile_response.status_code == 200, profile_response.text
    profile_body = profile_response.json()
    source_data = b"Local source document"
    source_response = client.post(
        "/api/v1/career-profile/sources",
        files={"file": ("source.txt", source_data, "text/plain")},
        headers=auth_headers,
    )
    assert source_response.status_code == 201, source_response.text
    db_session.expire_all()
    artifact_path = _seed_related_records(
        db_session, test_user.id, profile_body["id"], profile_body["facts"][0]["id"]
    )
    source_path = (
        db_session.query(CareerAsset)
        .filter(CareerAsset.profile_id == profile_body["id"])
        .one()
        .storage_path
    )

    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    archive_data = exported.content
    assert exported.headers["content-type"].startswith("application/zip")
    assert exported.headers["x-content-sha256"] == hashlib.sha256(archive_data).hexdigest()
    with zipfile.ZipFile(BytesIO(archive_data)) as archive:
        manifest = archive.read("manifest.json")
        payload_before = archive.read("payload.json")
        assert b"careeros-portable-archive" in manifest

    conflict = client.post(
        "/api/v1/portability/restore",
        files={"file": ("backup.zip", archive_data, "application/zip")},
        headers=auth_headers,
    )
    assert conflict.status_code == 409
    assert client.delete("/api/v1/career-profile", headers=auth_headers).status_code == 409

    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text
    db_session.expire_all()
    assert db_session.query(CandidateProfile).count() == 0
    assert db_session.query(Application).count() == 0
    assert db_session.query(WorkflowRun).count() == 0
    assert not resolve_data_path(source_path).exists()
    assert not resolve_data_path(artifact_path).exists()

    tampered = client.post(
        "/api/v1/portability/restore",
        files={"file": ("backup.zip", _tamper_payload(archive_data), "application/zip")},
        headers=auth_headers,
    )
    assert tampered.status_code == 422

    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("backup.zip", archive_data, "application/zip")},
        headers=auth_headers,
    )
    assert restored.status_code == 200, restored.text
    restore_body = restored.json()
    assert restore_body["restored_files"] == 2
    assert restore_body["restored_records"]["career_facts"] == 1
    assert restore_body["restored_records"]["applications"] == 1
    assert resolve_data_path(source_path).read_bytes() == source_data
    assert resolve_data_path(artifact_path).read_bytes().startswith(b"%PDF")
    loaded = client.get("/api/v1/career-profile", headers=auth_headers)
    assert loaded.status_code == 200
    assert loaded.json()["facts"][0]["payload"]["name"] == "Python"

    exported_again = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported_again.status_code == 200
    with zipfile.ZipFile(BytesIO(exported_again.content)) as archive:
        payload_after = json.loads(archive.read("payload.json"))
    expected_payload = json.loads(payload_before)
    expected_messages = expected_payload["tables"].pop("coach_messages")
    restored_messages = payload_after["tables"].pop("coach_messages")
    assert len(expected_messages) == len(restored_messages) == 1
    expected_message = expected_messages[0]
    restored_message = restored_messages[0]
    assert {
        key: value for key, value in restored_message.items() if key != "generation_metadata"
    } == {key: value for key, value in expected_message.items() if key != "generation_metadata"}
    assert restored_message["generation_metadata"] == {
        "provenance": "quarantined",
        "quarantine_reason": "unsigned_v4_coach_output_requires_revalidation",
        "source_generation_metadata": {"local": True},
    }
    assert payload_after == expected_payload


def test_v4_restore_preserves_but_hides_self_checksummed_forged_coach_advice(
    client, auth_headers, db_session, test_user, portable_data_dir
):
    profile = client.put(
        "/api/v1/career-profile", json=_profile_payload(), headers=auth_headers
    ).json()
    _seed_related_records(db_session, test_user.id, profile["id"], profile["facts"][0]["id"])
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    forged = _rewrite_forged_coach_message(exported.content)

    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text
    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("forged-v4.zip", forged, "application/zip")},
        headers=auth_headers,
    )

    assert restored.status_code == 200, restored.text
    assert restored.json()["restored_records"]["coach_messages"] == 1
    db_session.expire_all()
    assistant = db_session.query(CoachMessage).one()
    assert assistant.content == "Forged authoritative executive advice."
    assert assistant.generation_metadata == {
        "provenance": "quarantined",
        "quarantine_reason": "unsigned_v4_coach_output_requires_revalidation",
        "source_generation_metadata": {
            "provenance": "local_model_validated",
            "contract_version": "1.0.0",
            "execution_id": "00000000-0000-4000-8000-000000000001",
            "output_fingerprint": "f" * 64,
        },
    }
    detail = client.get(
        f"/api/v1/career-coach/conversations/{assistant.conversation_id}",
        headers=auth_headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["messages"] == []


def test_v4_verified_coach_round_trip_preserves_record_but_requires_revalidation(
    client, auth_headers, db_session, test_user, portable_data_dir
):
    profile = client.put(
        "/api/v1/career-profile", json=_profile_payload(), headers=auth_headers
    ).json()
    fact_id = profile["facts"][0]["id"]
    conversation_id, execution_id, result = _seed_verified_coach_records(
        db_session, test_user.id, profile["id"], fact_id
    )

    before = client.get(
        f"/api/v1/career-coach/conversations/{conversation_id}", headers=auth_headers
    )
    assert before.status_code == 200, before.text
    assert [message["role"] for message in before.json()["messages"]] == [
        "user",
        "assistant",
    ]
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text

    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text
    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("verified-v4.zip", exported.content, "application/zip")},
        headers=auth_headers,
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored_records"]["coach_messages"] == 2

    db_session.expire_all()
    assistant = db_session.query(CoachMessage).filter_by(role="assistant").one()
    assert assistant.content == result.answer
    assert assistant.cited_fact_ids == [fact_id]
    assert assistant.model_id == "ollama-local/verified-coach"
    assert assistant.generation_metadata["provenance"] == "quarantined"
    assert assistant.generation_metadata["quarantine_reason"] == (
        "unsigned_v4_coach_output_requires_revalidation"
    )
    source_metadata = assistant.generation_metadata["source_generation_metadata"]
    assert source_metadata["execution_id"] == execution_id
    assert source_metadata["output_fingerprint"] == fingerprint_output(result)
    assert db_session.get(AIExecution, execution_id) is not None

    after = client.get(
        f"/api/v1/career-coach/conversations/{conversation_id}", headers=auth_headers
    )
    assert after.status_code == 200, after.text
    assert [message["role"] for message in after.json()["messages"]] == ["user"]

    exported_again = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported_again.status_code == 200, exported_again.text
    with zipfile.ZipFile(BytesIO(exported_again.content)) as archive:
        payload = json.loads(archive.read("payload.json"))
    archived_assistant = next(
        row for row in payload["tables"]["coach_messages"] if row["role"] == "assistant"
    )
    assert archived_assistant["content"] == result.answer
    assert archived_assistant["generation_metadata"]["provenance"] == "quarantined"


def test_v4_round_trip_remaps_search_ids_and_preserves_application_job(
    client, auth_headers, db_session, test_user, portable_data_dir
):
    created = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert created.status_code == 200, created.text
    profile_id, scraped_id, job_id, application_id, signals = _seed_search_portability_records(
        db_session, test_user.id
    )

    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(BytesIO(exported.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        payload = json.loads(archive.read("payload.json"))
    assert manifest["format_version"] == 4
    expected_search_counts = {
        "search_profiles": 1,
        "scraped_jobs": 1,
        "jobs": 1,
        "preference_signals": 1,
    }
    assert {
        name: manifest["record_counts"][name] for name in expected_search_counts
    } == expected_search_counts
    assert payload["tables"]["applications"][0]["job_id"] == job_id
    exported_job = payload["tables"]["jobs"][0]
    assert exported_job["affinity_score"] is None
    assert exported_job["affinity_analysis"] is None
    assert exported_job["worth_applying"] is False
    assert exported_job["analysis_legacy_snapshot"] is None
    exported_snapshot = payload["tables"]["applications"][0]["job_snapshot"]
    assert exported_snapshot["match"]["receipt_verified"] is False
    assert exported_snapshot["match"]["score"] is None
    assert "affinity_analysis" not in exported_snapshot
    assert "raw unverified" not in json.dumps(exported_snapshot)
    assert payload["tables"]["preference_signals"][0]["preference_signals"] == signals
    assert "source_query" not in payload["tables"]["scraped_jobs"][0]
    assert payload["tables"]["jobs"][0]["source_query"] == "private Python search terms"
    runtime_fields = {
        "search_lock_token",
        "search_lock_state",
        "search_lock_acquired_at",
        "search_status_state",
        "search_status_payload",
        "search_status_started_at",
        "search_status_updated_at",
        "search_status_finished_at",
    }
    assert runtime_fields.isdisjoint(payload["tables"]["search_profiles"][0])

    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text
    db_session.expire_all()
    _clear_search_records(db_session, test_user.id, scraped_id)

    other_user = User(username="portability-collision", hashed_password="unused-local-hash")
    db_session.add(other_user)
    db_session.flush()
    collision_profile = SearchProfile(
        id=profile_id, user_id=other_user.id, name="Unrelated profile"
    )
    collision_scraped = ScrapedJob(
        id=scraped_id,
        platform="collision-test",
        platform_job_id="unrelated",
        title="Unrelated listing",
        company="Other Co",
        external_url="https://example.test/jobs/unrelated",
    )
    db_session.add_all([collision_profile, collision_scraped])
    db_session.flush()
    db_session.add(
        Job(
            id=job_id,
            user_id=other_user.id,
            search_profile_id=collision_profile.id,
            scraped_job_id=collision_scraped.id,
        )
    )
    db_session.commit()

    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("backup.zip", exported.content, "application/zip")},
        headers=auth_headers,
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored_records"]["jobs"] == 1
    db_session.expire_all()
    restored_profile = db_session.query(SearchProfile).filter_by(user_id=test_user.id).one()
    restored_job = db_session.query(Job).filter_by(user_id=test_user.id).one()
    restored_application = db_session.get(Application, application_id)
    assert restored_profile.id != profile_id
    assert restored_profile.name == "Portable backend search"
    assert restored_job.id != job_id
    assert restored_job.search_profile_id == restored_profile.id
    assert restored_job.scraped_job_id != scraped_id
    assert restored_job.scraped_job.title == "Local Backend Engineer"
    assert restored_job.source_query == "private Python search terms"
    assert restored_job.affinity_score is None
    assert restored_job.analysis_provenance is None
    assert restored_job.analysis_structured is None
    assert restored_job.analysis_legacy_snapshot is None
    assert restored_application.job_id == restored_job.id
    assert restored_application.job_snapshot["match"] == {
        "score": None,
        "analysis": None,
        "worth_applying": None,
        "receipt_verified": False,
        "quarantine_reason": "unsigned_v4_application_match_requires_revalidation",
    }
    assert "affinity_analysis" not in restored_application.job_snapshot
    assert all(getattr(restored_profile, field) is None for field in runtime_fields)
    owner = db_session.get(User, test_user.id)
    assert owner.preference_signals == signals
    assert owner.preference_updated_at is not None


def test_damaged_v4_relationship_leaves_search_vault_and_preferences_unchanged(
    client, auth_headers, db_session, test_user, portable_data_dir
):
    created = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert created.status_code == 200, created.text
    _profile_id, scraped_id, _job_id, _application_id, _signals = _seed_search_portability_records(
        db_session, test_user.id
    )
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    damaged = _rewrite_application_job(exported.content, 999_999)

    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text
    db_session.expire_all()
    _clear_search_records(db_session, test_user.id, scraped_id)
    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("damaged.zip", damaged, "application/zip")},
        headers=auth_headers,
    )
    assert restored.status_code == 422, restored.text
    assert "missing job" in restored.json()["detail"]
    db_session.expire_all()
    assert db_session.query(CandidateProfile).filter_by(user_id=test_user.id).count() == 0
    assert db_session.query(SearchProfile).filter_by(user_id=test_user.id).count() == 0
    assert db_session.query(Job).filter_by(user_id=test_user.id).count() == 0
    assert db_session.query(Application).filter_by(user_id=test_user.id).count() == 0
    assert (
        db_session.query(ScrapedJob)
        .filter_by(platform="portable-test", platform_job_id="listing-42")
        .count()
        == 0
    )
    assert db_session.get(User, test_user.id).preference_signals is None


def test_legacy_v3_restore_quarantines_unverified_match_analysis(
    client, auth_headers, db_session, test_user, portable_data_dir
):
    created = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert created.status_code == 200, created.text
    _profile_id, scraped_id, _job_id, _application_id, _signals = _seed_search_portability_records(
        db_session, test_user.id
    )
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    legacy = _rewrite_legacy_v3_heuristic_match(exported.content)

    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text
    db_session.expire_all()
    _clear_search_records(db_session, test_user.id, scraped_id)

    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("legacy-v3.zip", legacy, "application/zip")},
        headers=auth_headers,
    )

    assert restored.status_code == 200, restored.text
    db_session.expire_all()
    job = db_session.query(Job).filter_by(user_id=test_user.id).one()
    assert job.affinity_score is None
    assert job.affinity_analysis is None
    assert job.worth_applying is False
    assert job.skill_match_score is None
    assert job.analysis_structured is None
    assert job.red_flags is None
    assert job.analysis_legacy_snapshot["reason"] == ("unsigned_v3_analysis_requires_revalidation")
    assert job.analysis_legacy_snapshot["analysis"]["affinity_analysis"] == ("Legacy heuristic fit")
    assert job.analysis_legacy_snapshot["analysis"]["worth_applying"] is True
    application = db_session.query(Application).filter_by(user_id=test_user.id).one()
    assert application.job_snapshot["match"] == {
        "score": None,
        "analysis": None,
        "worth_applying": None,
        "receipt_verified": False,
        "quarantine_reason": "unsigned_v3_application_match_requires_revalidation",
    }
    assert "affinity_analysis" not in application.job_snapshot
    assert "Legacy" not in json.dumps(application.job_snapshot)


def test_v4_restore_rejects_preexisting_preference_signals_without_mutation(
    client, auth_headers, db_session, test_user, portable_data_dir
):
    created = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert created.status_code == 200, created.text
    _profile_id, scraped_id, _job_id, _application_id, _signals = _seed_search_portability_records(
        db_session, test_user.id
    )
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text

    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text
    db_session.expire_all()
    _clear_search_records(db_session, test_user.id, scraped_id)
    owner = db_session.get(User, test_user.id)
    sentinel = {"signal_count": 1, "preferred_domains": {"finance": 1.0}}
    owner.preference_signals = sentinel
    owner.preference_updated_at = datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc)
    db_session.commit()

    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("backup.zip", exported.content, "application/zip")},
        headers=auth_headers,
    )

    assert restored.status_code == 409, restored.text
    assert "empty preference signals" in restored.json()["detail"]
    db_session.expire_all()
    assert db_session.query(CandidateProfile).filter_by(user_id=test_user.id).count() == 0
    assert db_session.query(SearchProfile).filter_by(user_id=test_user.id).count() == 0
    assert db_session.get(User, test_user.id).preference_signals == sentinel


def test_v4_restore_rejects_unsafe_existing_shared_listing(
    client,
    auth_headers,
    db_session,
    test_user,
    portable_data_dir,
):
    created = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert created.status_code == 200, created.text
    _profile_id, scraped_id, _job_id, _application_id, _signals = _seed_search_portability_records(
        db_session, test_user.id
    )
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text
    db_session.expire_all()
    _clear_search_records(db_session, test_user.id, scraped_id)

    other_user = User(username="shared-owner", hashed_password="unused-local-hash")
    existing = ScrapedJob(
        platform="portable-test",
        platform_job_id="listing-42",
        title="Stale Backend Engineer",
        company="Portable Co",
        description="Build local-first systems.",
        location="Zurich",
        external_url="https://example.test/jobs/42",
        normalized_domain="it",
    )
    db_session.add_all([other_user, existing])
    db_session.flush()
    db_session.add(
        Job(
            user_id=other_user.id,
            scraped_job_id=existing.id,
            source_query="another user's private query",
        )
    )
    db_session.commit()

    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("backup.zip", exported.content, "application/zip")},
        headers=auth_headers,
    )

    assert restored.status_code == 409, restored.text
    assert "shared scraped listing" in restored.json()["detail"]
    db_session.expire_all()
    assert db_session.query(CandidateProfile).filter_by(user_id=test_user.id).count() == 0
    assert db_session.query(Job).filter_by(user_id=test_user.id).count() == 0
    assert db_session.query(Job).filter_by(user_id=other_user.id).count() == 1
    assert (
        db_session.query(Job).filter_by(user_id=other_user.id).one().source_query
        == "another user's private query"
    )


def test_v4_restore_reuses_only_identical_public_shared_listing(
    client, auth_headers, db_session, test_user, portable_data_dir
):
    created = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert created.status_code == 200, created.text
    _profile_id, scraped_id, _job_id, _application_id, _signals = _seed_search_portability_records(
        db_session, test_user.id
    )
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text
    db_session.expire_all()
    _clear_search_records(db_session, test_user.id, scraped_id)

    other_user = User(username="safe-shared-owner", hashed_password="unused-local-hash")
    existing = ScrapedJob(
        platform="portable-test",
        platform_job_id="listing-42",
        title="Local Backend Engineer",
        company="Portable Co",
        description="Build local-first systems.",
        location="Zurich",
        external_url="https://example.test/jobs/42",
        normalized_domain="it",
    )
    db_session.add_all([other_user, existing])
    db_session.flush()
    existing_id = existing.id
    db_session.add(
        Job(
            user_id=other_user.id,
            scraped_job_id=existing_id,
            source_query="other owner's private query",
        )
    )
    db_session.commit()

    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("backup.zip", exported.content, "application/zip")},
        headers=auth_headers,
    )

    assert restored.status_code == 200, restored.text
    db_session.expire_all()
    restored_job = db_session.query(Job).filter_by(user_id=test_user.id).one()
    assert restored_job.scraped_job_id == existing_id
    assert restored_job.source_query == "private Python search terms"
    assert (
        db_session.query(Job).filter_by(user_id=other_user.id).one().source_query
        == "other owner's private query"
    )


def test_v3_restore_accepts_legacy_private_field_but_does_not_propagate_it(
    client, auth_headers, db_session, test_user, portable_data_dir
):
    created = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert created.status_code == 200, created.text
    _profile_id, scraped_id, _job_id, _application_id, _signals = _seed_search_portability_records(
        db_session, test_user.id
    )
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    legacy_v3 = _rewrite_legacy_v3_private_and_runtime_fields(
        exported.content, "legacy user's private discovery query"
    )
    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text
    db_session.expire_all()
    _clear_search_records(db_session, test_user.id, scraped_id)

    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("legacy-v3.zip", legacy_v3, "application/zip")},
        headers=auth_headers,
    )

    assert restored.status_code == 200, restored.text
    db_session.expire_all()
    restored_job = db_session.query(Job).filter_by(user_id=test_user.id).one()
    restored_profile = db_session.query(SearchProfile).filter_by(user_id=test_user.id).one()
    assert restored_job.source_query is None
    assert restored_profile.search_lock_token is None
    assert restored_profile.search_lock_state is None
    assert restored_profile.search_lock_acquired_at is None
    assert restored_profile.search_status_state is None
    assert restored_profile.search_status_payload is None
    assert restored_profile.search_status_started_at is None
    assert restored_profile.search_status_updated_at is None
    assert restored_profile.search_status_finished_at is None


def test_backup_restore_disk_full_rolls_back_records_and_first_file(
    client, auth_headers, db_session, test_user, portable_data_dir, monkeypatch
):
    profile_response = client.put(
        "/api/v1/career-profile", json=_profile_payload(), headers=auth_headers
    )
    assert profile_response.status_code == 200, profile_response.text
    profile = profile_response.json()
    source_response = client.post(
        "/api/v1/career-profile/sources",
        files={"file": ("source.txt", b"private source", "text/plain")},
        headers=auth_headers,
    )
    assert source_response.status_code == 201, source_response.text
    db_session.expire_all()
    artifact_path = _seed_related_records(
        db_session, test_user.id, profile["id"], profile["facts"][0]["id"]
    )
    source_path = (
        db_session.query(CareerAsset)
        .filter(CareerAsset.profile_id == profile["id"])
        .one()
        .storage_path
    )
    archive_data = client.get("/api/v1/portability/export", headers=auth_headers).content
    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text

    original_fsync = atomic.os.fsync
    calls = 0

    def fail_second_write(descriptor):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError(errno.ENOSPC, "No space left on device")
        return original_fsync(descriptor)

    monkeypatch.setattr(atomic.os, "fsync", fail_second_write)
    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("backup.zip", archive_data, "application/zip")},
        headers=auth_headers,
    )

    assert restored.status_code == 507, restored.text
    db_session.expire_all()
    assert db_session.query(CandidateProfile).count() == 0
    assert not resolve_data_path(source_path).exists()
    assert not resolve_data_path(artifact_path).exists()
    assert list(portable_data_dir.rglob(".write-*")) == []


def test_backup_export_interruption_returns_507_without_mutating_vault(
    client, auth_headers, db_session, monkeypatch
):
    created = client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    assert created.status_code == 200, created.text
    original_write = archive_module.zipfile.ZipFile.writestr
    calls = 0

    def interrupted_write(self, member, data, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError(errno.ENOSPC, "No space left on device")
        return original_write(self, member, data, *args, **kwargs)

    monkeypatch.setattr(archive_module.zipfile.ZipFile, "writestr", interrupted_write)
    response = client.get("/api/v1/portability/export", headers=auth_headers)

    assert response.status_code == 507, response.text
    db_session.expire_all()
    persisted = db_session.query(CandidateProfile).one()
    assert persisted.id == created.json()["id"]
    assert persisted.revision == created.json()["revision"]
