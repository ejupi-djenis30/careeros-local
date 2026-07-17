import errno
import hashlib
import uuid
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.applications.models import Application, ApplicationEvent
from backend.career.coach_models import CoachConversation, CoachMessage
from backend.career.models import CandidateProfile, CareerAsset
from backend.core.config import settings
from backend.portability import archive as archive_module
from backend.resumes.models import ResumeArtifact, ResumeDraft, ResumeVersion
from backend.storage import atomic
from backend.storage.atomic import atomic_write, resolve_data_path
from backend.workflows.models import WorkflowRun


def _profile_payload():
    return {
        "expected_revision": 0,
        "display_name": "Ada Lovelace",
        "headline": "Computing pioneer",
        "summary": "Builds rigorous analytical systems.",
        "email": "ada@example.test",
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
        snapshot={"display_name": "Ada Lovelace"},
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
        job_snapshot={"title": "Backend Engineer", "company": "Local Co"},
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
    assert (
        client.delete("/api/v1/career-profile", headers=auth_headers).status_code == 409
    )

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
        assert archive.read("payload.json") == payload_before


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
    archive_data = client.get(
        "/api/v1/portability/export", headers=auth_headers
    ).content
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
    created = client.put(
        "/api/v1/career-profile", json=_profile_payload(), headers=auth_headers
    )
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
