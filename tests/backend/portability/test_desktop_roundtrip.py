import hashlib
import json
import threading
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from backend.ai.models import AIExecution
from backend.career.deletion import (
    VaultMaintenanceConflictError,
    begin_vault_maintenance,
    delete_complete_vault,
)
from backend.career.models import CandidateProfile, CareerAsset, CareerGoal
from backend.core.config import settings
from backend.db.base import Base, configure_sqlite_connection, ensure_sqlite_parent
from backend.desktop.lifecycle import VaultLockTimeout, desktop_vault_lock
from backend.models import User
from backend.models.auth_session import AuthSession
from backend.models.user import (
    VAULT_STATE_ERASURE_PENDING,
    VAULT_STATE_READY,
    VAULT_STATE_RESTORE_PENDING,
)
from backend.portability.archive import ArchiveError, export_archive
from backend.portability.journal import atomic_restore_write, prepare_restore_journal
from backend.portability.manifest import PAYLOAD_MEMBER
from backend.portability.restore import (
    RestoreRolledBackError,
    _prepare_file_writes,
    _rollback_failed_restore,
    restore_archive,
)
from backend.resumes.artifact_policy import MAX_RESUME_ARTIFACT_BYTES
from backend.services.auth import ACCESS_PURPOSE_SESSION, ACCESS_PURPOSE_VAULT_MAINTENANCE
from backend.storage.atomic import resolve_data_path

PROFILE = {
    "expected_revision": 0,
    "display_name": "Noa Rowan",
    "headline": "Compiler pioneer",
    "summary": "Turns evidence into reliable systems.",
    "email": "grace@example.test",
    "location": {"city": "New York", "country": "US"},
    "preferences": {},
    "facts": [],
    "goals": [],
}


class _UnreadableManagedMemberDict(dict[str, bytes]):
    def __getitem__(self, key: str) -> bytes:
        if key != PAYLOAD_MEMBER:
            raise AssertionError("managed member bytes were read before metadata validation")
        return super().__getitem__(key)


@pytest.mark.parametrize(
    ("table_name", "invalid_size"),
    [
        ("career_assets", 0),
        ("career_assets", settings.MAX_UPLOAD_FILE_SIZE + 1),
        ("resume_artifacts", 0),
        ("resume_artifacts", MAX_RESUME_ARTIFACT_BYTES + 1),
    ],
)
def test_restore_rejects_invalid_per_table_file_size_before_member_read(
    table_name: str,
    invalid_size: int,
) -> None:
    digest = "a" * 64
    member = f"files/{table_name}/private"
    if table_name == "career_assets":
        record = {
            "id": "asset-id",
            "kind": "source_document",
            "normalized": False,
            "sha256": digest,
            "byte_size": invalid_size,
            "storage_path": f"assets/{digest[:2]}/{digest}",
        }
    else:
        record = {
            "id": "artifact-id",
            "version_id": "version-id",
            "format": "pdf",
            "media_type": "application/pdf",
            "sha256": digest,
            "byte_size": invalid_size,
            "storage_path": f"resumes/profile-id/version-id/{digest}.pdf",
        }
    decoded = {
        "career_assets": [record] if table_name == "career_assets" else [],
        "resume_artifacts": [record] if table_name == "resume_artifacts" else [],
        "resume_versions": [],
        "resume_drafts": [],
    }
    bindings = [
        {
            "table": table_name,
            "record_id": record["id"],
            "member": member,
            "storage_path": record["storage_path"],
        }
    ]
    members = _UnreadableManagedMemberDict({PAYLOAD_MEMBER: b"{}", member: b"private"})

    with pytest.raises(ArchiveError, match="file size metadata"):
        _prepare_file_writes(decoded, bindings, members, create_data_root=False)


@pytest.fixture
def desktop_data_dir(monkeypatch):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        monkeypatch.setattr(settings, "DATA_DIR", str(root))
        monkeypatch.setenv("CAREEROS_DESKTOP_DATA_DIR", str(root))
        yield root


def _create_profile(client, auth_headers):
    response = client.put("/api/v1/career-profile", json=PROFILE, headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


def _delete_profile(client, auth_headers):
    response = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert response.status_code == 204, response.text


def _source_archive_ready_for_direct_restore(
    client,
    auth_headers,
    db_session,
    test_user,
    *,
    content: bytes,
) -> tuple[bytes, str, str]:
    _create_profile(client, auth_headers)
    source = client.post(
        "/api/v1/career-profile/sources",
        files={"file": ("receipt.txt", content, "text/plain")},
        headers=auth_headers,
    )
    assert source.status_code == 201, source.text
    db_session.expire_all()
    storage_path = db_session.query(CareerAsset).one().storage_path
    archive = client.get("/api/v1/portability/export", headers=auth_headers).content
    _delete_profile(client, auth_headers)
    authority = db_session.query(AuthSession).filter_by(user_id=test_user.id).one()
    begin_vault_maintenance(
        db_session,
        test_user.id,
        authority.id,
        VAULT_STATE_RESTORE_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
        maintenance_fingerprint=hashlib.sha256(archive).hexdigest(),
    )
    return archive, storage_path, authority.id


def _reauthenticated_headers(client, username: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": "Globalpass1"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _convert_to_version(data: bytes, version: int) -> bytes:
    with zipfile.ZipFile(BytesIO(data), "r") as source:
        files = {name: source.read(name) for name in source.namelist()}
    payload = json.loads(files["payload.json"])
    if version < 5:
        for row in payload["tables"].get("applications", []):
            row.pop("scraped_job_id", None)
        for row in payload["tables"].get("scraped_jobs", []):
            for field in (
                "first_seen_at",
                "last_seen_at",
                "last_changed_at",
                "content_revision",
            ):
                row.pop(field, None)
        for row in payload["tables"].get("search_profiles", []):
            for field in (
                "last_search_started_at",
                "last_search_completed_at",
                "last_search_state",
                "search_run_count",
                "last_search_summary",
            ):
                row.pop(field, None)
    removed_tables = []
    if version < 7:
        removed_tables.append("job_provider_configurations")
    if version < 6:
        removed_tables.append("application_dossier_drafts")
    if version < 3:
        removed_tables.extend(["search_profiles", "scraped_jobs", "jobs", "preference_signals"])
    elif version == 3:
        for row in payload["tables"]["jobs"]:
            for field in (
                "analysis_provenance",
                "analysis_model_id",
                "analysis_contract_version",
                "analysis_validated_at",
                "analysis_legacy_snapshot",
            ):
                row.pop(field, None)
    if version < 2:
        removed_tables.append("ai_executions")
    for table_name in removed_tables:
        payload["tables"].pop(table_name)
    files["payload.json"] = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    manifest = json.loads(files["manifest.json"])
    manifest["format_version"] = version
    for table_name in removed_tables:
        manifest["record_counts"].pop(table_name)
    for entry in manifest["entries"]:
        if entry["path"] == "payload.json":
            entry["byte_size"] = len(files["payload.json"])
            entry["sha256"] = hashlib.sha256(files["payload.json"]).hexdigest()
    files["manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for name, content in files.items():
            target.writestr(name, content)
    return output.getvalue()


def _with_profile_created_at(data: bytes, timestamp: str) -> bytes:
    with zipfile.ZipFile(BytesIO(data), "r") as source:
        files = {name: source.read(name) for name in source.namelist()}
    payload = json.loads(files["payload.json"])
    payload["tables"]["candidate_profiles"][0]["created_at"] = timestamp
    files["payload.json"] = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    manifest = json.loads(files["manifest.json"])
    for entry in manifest["entries"]:
        if entry["path"] == "payload.json":
            entry["byte_size"] = len(files["payload.json"])
            entry["sha256"] = hashlib.sha256(files["payload.json"]).hexdigest()
    files["manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for name, content in files.items():
            target.writestr(name, content)
    return output.getvalue()


def test_v6_archive_restores_ai_audit_and_v5_v4_v3_v2_v1_remain_compatible(
    client, auth_headers, db_session, test_user, desktop_data_dir
):
    _create_profile(client, auth_headers)
    execution = AIExecution(
        user_id=test_user.id,
        task="coach",
        contract_version="1.0.0",
        model_id="qwen3-local",
        input_fingerprint="1" * 64,
        output_fingerprint="2" * 64,
        evidence_count=2,
        accepted=True,
        repair_count=0,
        validation_codes=[],
        duration_ms=42,
    )
    db_session.add(execution)
    db_session.commit()

    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(BytesIO(exported.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["format_version"] == 7
    assert manifest["record_counts"]["ai_executions"] == 1
    assert manifest["record_counts"]["preference_signals"] == 1

    _delete_profile(client, auth_headers)
    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("backup.zip", exported.content, "application/zip")},
        headers=auth_headers,
    )
    assert restored.status_code == 200, restored.text
    db_session.expire_all()
    assert db_session.query(AIExecution).filter(AIExecution.user_id == test_user.id).count() == 1

    auth_headers = _reauthenticated_headers(client, test_user.username)
    _delete_profile(client, auth_headers)
    v5_data = _convert_to_version(exported.content, 5)
    restored_v5 = client.post(
        "/api/v1/portability/restore",
        files={"file": ("v5.zip", v5_data, "application/zip")},
        headers=auth_headers,
    )
    assert restored_v5.status_code == 200, restored_v5.text
    assert restored_v5.json()["format_version"] == 5

    auth_headers = _reauthenticated_headers(client, test_user.username)
    _delete_profile(client, auth_headers)
    v4_data = _convert_to_version(exported.content, 4)
    restored_v4 = client.post(
        "/api/v1/portability/restore",
        files={"file": ("v4.zip", v4_data, "application/zip")},
        headers=auth_headers,
    )
    assert restored_v4.status_code == 200, restored_v4.text
    assert restored_v4.json()["format_version"] == 4

    auth_headers = _reauthenticated_headers(client, test_user.username)
    _delete_profile(client, auth_headers)
    v3_data = _convert_to_version(exported.content, 3)
    restored_v3 = client.post(
        "/api/v1/portability/restore",
        files={"file": ("v3.zip", v3_data, "application/zip")},
        headers=auth_headers,
    )
    assert restored_v3.status_code == 200, restored_v3.text
    assert restored_v3.json()["format_version"] == 3

    auth_headers = _reauthenticated_headers(client, test_user.username)
    _delete_profile(client, auth_headers)
    v2_data = _convert_to_version(exported.content, 2)
    restored_v2 = client.post(
        "/api/v1/portability/restore",
        files={"file": ("v2.zip", v2_data, "application/zip")},
        headers=auth_headers,
    )
    assert restored_v2.status_code == 200, restored_v2.text
    assert restored_v2.json()["format_version"] == 2
    assert restored_v2.json()["restored_records"]["preference_signals"] == 0

    auth_headers = _reauthenticated_headers(client, test_user.username)
    _delete_profile(client, auth_headers)
    v1_data = _convert_to_version(exported.content, 1)
    restored_v1 = client.post(
        "/api/v1/portability/restore",
        files={"file": ("legacy.zip", v1_data, "application/zip")},
        headers=auth_headers,
    )
    assert restored_v1.status_code == 200, restored_v1.text
    assert restored_v1.json()["format_version"] == 1
    assert restored_v1.json()["restored_records"]["ai_executions"] == 0


@pytest.mark.parametrize("format_version", [1, 2, 3, 4, 5, 6, 7])
@pytest.mark.parametrize(
    "archived_timestamp",
    ["2026-07-22T12:15:00+02:00", "2026-07-22T10:15:00"],
    ids=["non-utc-offset", "legacy-naive-utc"],
)
def test_archive_versions_normalize_legacy_timestamps_to_aware_utc(
    client,
    auth_headers,
    db_session,
    test_user,
    desktop_data_dir,
    format_version,
    archived_timestamp,
):
    _create_profile(client, auth_headers)
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    _delete_profile(client, auth_headers)

    archive = (
        exported.content
        if format_version == 7
        else _convert_to_version(exported.content, format_version)
    )
    archive = _with_profile_created_at(archive, archived_timestamp)
    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("legacy.zip", archive, "application/zip")},
        headers=auth_headers,
    )

    assert restored.status_code == 200, restored.text
    assert restored.json()["format_version"] == format_version
    db_session.expire_all()
    profile = (
        db_session.query(CandidateProfile).filter(CandidateProfile.user_id == test_user.id).one()
    )
    assert profile.created_at == datetime(2026, 7, 22, 10, 15, tzinfo=timezone.utc)


def test_interrupted_restore_rolls_back_database_and_created_files(
    client, auth_headers, db_session, test_user, desktop_data_dir, monkeypatch
):
    profile = _create_profile(client, auth_headers)
    for index in range(2):
        response = client.post(
            "/api/v1/career-profile/sources",
            files={"file": (f"source-{index}.txt", f"evidence {index}".encode(), "text/plain")},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
    db_session.expire_all()
    paths = [
        asset.storage_path
        for asset in db_session.query(CareerAsset)
        .filter(CareerAsset.profile_id == profile["id"])
        .all()
    ]
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    _delete_profile(client, auth_headers)

    import backend.portability.restore as restore_module

    original_atomic_write = restore_module.atomic_restore_write
    calls = 0

    def interrupted_write(user_id, relative_path, content):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated interrupted upgrade")
        return original_atomic_write(user_id, relative_path, content)

    monkeypatch.setattr(restore_module, "atomic_restore_write", interrupted_write)
    with pytest.raises(restore_module.RestoreRolledBackError) as failure:
        restore_archive(db_session, test_user.id, exported.content)
    assert isinstance(failure.value.original, OSError)
    assert "interrupted upgrade" in str(failure.value.original)

    db_session.expire_all()
    assert db_session.query(CandidateProfile).filter_by(user_id=test_user.id).count() == 0
    assert all(not resolve_data_path(path).exists() for path in paths)


def test_restore_commit_acknowledgement_error_keeps_committed_rows_files_and_lifecycle(
    client,
    auth_headers,
    db_session,
    test_user,
    desktop_data_dir,
    monkeypatch,
) -> None:
    content = b"restore commit acknowledgement evidence"
    archive, storage_path, authority_id = _source_archive_ready_for_direct_restore(
        client,
        auth_headers,
        db_session,
        test_user,
        content=content,
    )
    real_commit = db_session.commit
    acknowledgement_lost = False

    def commit_then_raise_once() -> None:
        nonlocal acknowledgement_lost
        real_commit()
        if not acknowledgement_lost:
            acknowledgement_lost = True
            raise RuntimeError("synthetic lost restore commit acknowledgement")

    monkeypatch.setattr(db_session, "commit", commit_then_raise_once)
    restored = restore_archive(db_session, test_user.id, archive)

    assert acknowledgement_lost is True
    assert restored.restored_files == 1
    db_session.expire_all()
    owner = db_session.get(User, test_user.id)
    assert owner is not None
    assert owner.vault_lifecycle_state == VAULT_STATE_READY
    assert owner.vault_maintenance_fingerprint is None
    assert db_session.query(CandidateProfile).filter_by(user_id=test_user.id).count() == 1
    asset = db_session.query(CareerAsset).one()
    assert asset.storage_path == storage_path
    assert resolve_data_path(storage_path).read_bytes() == content
    assert db_session.get(AuthSession, authority_id).revoked_at is not None
    assert not (desktop_data_dir / ".restore" / f"user-{test_user.id}").exists()


def test_restore_failure_before_commit_removes_rows_files_and_keeps_retry_lifecycle(
    client,
    auth_headers,
    db_session,
    test_user,
    desktop_data_dir,
    monkeypatch,
) -> None:
    archive, storage_path, authority_id = _source_archive_ready_for_direct_restore(
        client,
        auth_headers,
        db_session,
        test_user,
        content=b"restore precommit rollback evidence",
    )

    def fail_before_commit() -> None:
        raise RuntimeError("synthetic restore precommit failure")

    monkeypatch.setattr(db_session, "commit", fail_before_commit)
    with pytest.raises(RestoreRolledBackError) as failure:
        restore_archive(db_session, test_user.id, archive)

    assert isinstance(failure.value.original, RuntimeError)
    assert "precommit" in str(failure.value.original)
    db_session.expire_all()
    owner = db_session.get(User, test_user.id)
    assert owner is not None
    assert owner.vault_lifecycle_state == VAULT_STATE_RESTORE_PENDING
    assert owner.vault_maintenance_fingerprint == hashlib.sha256(archive).hexdigest()
    assert db_session.query(CandidateProfile).filter_by(user_id=test_user.id).count() == 0
    assert db_session.query(CareerAsset).count() == 0
    assert db_session.get(AuthSession, authority_id).revoked_at is None
    assert not resolve_data_path(storage_path).exists()
    assert not (desktop_data_dir / ".restore" / f"user-{test_user.id}").exists()


def test_hard_crash_after_first_restore_file_retries_same_archive_durably(
    client,
    auth_headers,
    db_session,
    test_user,
    desktop_data_dir,
    monkeypatch,
):
    _create_profile(client, auth_headers)
    source = client.post(
        "/api/v1/career-profile/sources",
        files={"file": ("source.txt", b"restart durable evidence", "text/plain")},
        headers=auth_headers,
    )
    assert source.status_code == 201, source.text
    db_session.expire_all()
    storage_path = db_session.query(CareerAsset).one().storage_path
    archive = client.get("/api/v1/portability/export", headers=auth_headers).content
    _delete_profile(client, auth_headers)
    authority = db_session.query(AuthSession).filter_by(user_id=test_user.id).one()
    fingerprint = hashlib.sha256(archive).hexdigest()
    begin_vault_maintenance(
        db_session,
        test_user.id,
        authority.id,
        VAULT_STATE_RESTORE_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
        maintenance_fingerprint=fingerprint,
    )

    import backend.portability.restore as restore_module

    original_write = restore_module.atomic_restore_write

    def hard_crash(user_id, relative_path, content):
        original_write(user_id, relative_path, content)
        raise KeyboardInterrupt("simulated process loss after publication")

    monkeypatch.setattr(restore_module, "atomic_restore_write", hard_crash)
    with pytest.raises(KeyboardInterrupt, match="process loss"):
        restore_archive(db_session, test_user.id, archive)
    db_session.rollback()

    assert resolve_data_path(storage_path).read_bytes() == b"restart durable evidence"
    assert (desktop_data_dir / ".restore" / f"user-{test_user.id}").exists()
    with pytest.raises(VaultMaintenanceConflictError, match="same verified archive"):
        begin_vault_maintenance(
            db_session,
            test_user.id,
            authority.id,
            VAULT_STATE_RESTORE_PENDING,
            token_purpose=ACCESS_PURPOSE_VAULT_MAINTENANCE,
            maintenance_fingerprint="0" * 64,
        )

    monkeypatch.setattr(restore_module, "atomic_restore_write", original_write)
    restored = restore_archive(db_session, test_user.id, archive)

    assert restored.restored_files == 1
    assert not (desktop_data_dir / ".restore" / f"user-{test_user.id}").exists()
    assert db_session.query(CandidateProfile).filter_by(user_id=test_user.id).count() == 1


def test_retry_from_pending_clean_rollback_returns_account_to_ready(
    client,
    auth_headers,
    db_session,
    test_user,
    desktop_data_dir,
    monkeypatch,
):
    _create_profile(client, auth_headers)
    source = client.post(
        "/api/v1/career-profile/sources",
        files={"file": ("source.txt", b"pending retry evidence", "text/plain")},
        headers=auth_headers,
    )
    assert source.status_code == 201, source.text
    db_session.expire_all()
    storage_path = db_session.query(CareerAsset).one().storage_path
    archive = client.get("/api/v1/portability/export", headers=auth_headers).content
    _delete_profile(client, auth_headers)
    authority = db_session.query(AuthSession).filter_by(user_id=test_user.id).one()
    begin_vault_maintenance(
        db_session,
        test_user.id,
        authority.id,
        VAULT_STATE_RESTORE_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
        maintenance_fingerprint=hashlib.sha256(archive).hexdigest(),
    )

    import backend.portability.restore as restore_module

    original_write = restore_module.atomic_restore_write

    def hard_crash(user_id, relative_path, content):
        original_write(user_id, relative_path, content)
        raise KeyboardInterrupt("process loss before retry")

    monkeypatch.setattr(restore_module, "atomic_restore_write", hard_crash)
    with pytest.raises(KeyboardInterrupt, match="process loss"):
        restore_archive(db_session, test_user.id, archive)
    db_session.rollback()

    recovery_login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
    )
    assert recovery_login.status_code == 200, recovery_login.text
    assert recovery_login.json()["session_state"] == VAULT_STATE_RESTORE_PENDING

    monkeypatch.setattr(restore_module, "atomic_restore_write", original_write)

    def fail_after_records(*_args, **_kwargs):
        raise ArchiveError("retry validation failed")

    monkeypatch.setattr(restore_module, "_rebuild_application_projections", fail_after_records)
    retry = client.post(
        "/api/v1/portability/restore",
        files={"file": ("backup.zip", archive, "application/zip")},
        headers={"Authorization": f"Bearer {recovery_login.json()['access_token']}"},
    )

    assert retry.status_code == 422, retry.text
    assert retry.json() == {"detail": "retry validation failed"}
    db_session.expire_all()
    restored_user = db_session.get(User, test_user.id)
    assert restored_user is not None
    assert restored_user.vault_lifecycle_state == VAULT_STATE_READY
    assert restored_user.vault_maintenance_fingerprint is None
    assert not resolve_data_path(storage_path).exists()
    assert not (desktop_data_dir / ".restore" / f"user-{test_user.id}").exists()

    normal_login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.username, "password": "Globalpass1"},
    )
    assert normal_login.status_code == 200, normal_login.text
    assert "session_state" not in normal_login.json()


def test_erasure_recovers_restore_file_and_staging_when_original_zip_is_lost(
    client,
    auth_headers,
    db_session,
    test_user,
    desktop_data_dir,
    monkeypatch,
):
    _create_profile(client, auth_headers)
    source = client.post(
        "/api/v1/career-profile/sources",
        files={"file": ("source.txt", b"lost backup evidence", "text/plain")},
        headers=auth_headers,
    )
    assert source.status_code == 201, source.text
    db_session.expire_all()
    storage_path = db_session.query(CareerAsset).one().storage_path
    archive = client.get("/api/v1/portability/export", headers=auth_headers).content
    _delete_profile(client, auth_headers)
    authority = db_session.query(AuthSession).filter_by(user_id=test_user.id).one()
    begin_vault_maintenance(
        db_session,
        test_user.id,
        authority.id,
        VAULT_STATE_RESTORE_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
        maintenance_fingerprint=hashlib.sha256(archive).hexdigest(),
    )

    import backend.portability.restore as restore_module

    original_write = restore_module.atomic_restore_write

    def hard_crash(user_id, relative_path, content):
        original_write(user_id, relative_path, content)
        staging = desktop_data_dir / ".restore" / f"user-{user_id}" / "staging"
        staging.mkdir(exist_ok=True)
        (staging / ".write-private").write_bytes(b"staged private bytes")
        raise KeyboardInterrupt("lost archive")

    monkeypatch.setattr(restore_module, "atomic_restore_write", hard_crash)
    with pytest.raises(KeyboardInterrupt, match="lost archive"):
        restore_archive(db_session, test_user.id, archive)
    db_session.rollback()

    begin_vault_maintenance(
        db_session,
        test_user.id,
        authority.id,
        VAULT_STATE_ERASURE_PENDING,
        token_purpose=ACCESS_PURPOSE_VAULT_MAINTENANCE,
    )
    delete_complete_vault(
        db_session,
        test_user.id,
        erase_auth_sessions=True,
        erasure_session_id=authority.id,
    )

    assert not resolve_data_path(storage_path).exists()
    assert not (desktop_data_dir / ".restore" / f"user-{test_user.id}").exists()
    assert db_session.query(AuthSession).filter_by(user_id=test_user.id).count() == 0


def test_failed_restore_sanitizes_rolled_back_private_database_bytes(
    desktop_data_dir,
) -> None:
    database_path = desktop_data_dir / "restore-rollback.db"
    ensure_sqlite_parent(f"sqlite:///{database_path.as_posix()}")
    local_engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    event.listen(local_engine, "connect", configure_sqlite_connection)
    LocalSession = sessionmaker(bind=local_engine, expire_on_commit=False)
    marker = "PRIVATE-RESTORE-ROLLBACK-MARKER-7b8f92d4"
    with local_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE restore_probe (payload TEXT NOT NULL)")
    session = LocalSession()
    try:
        session.execute(
            text("INSERT INTO restore_probe(payload) VALUES (:marker)"), {"marker": marker}
        )
        with pytest.raises(RestoreRolledBackError):
            _rollback_failed_restore(session, 1, ValueError("late restore failure"))
    finally:
        session.close()
        local_engine.dispose()

    marker_bytes = marker.encode("utf-8")
    for path in (
        database_path,
        Path(f"{database_path}-wal"),
        Path(f"{database_path}-shm"),
    ):
        if path.exists():
            assert marker_bytes not in path.read_bytes()


def test_failed_restore_preserves_file_that_another_account_bound_after_publish(
    client,
    auth_headers,
    db_session,
    test_user,
    desktop_data_dir,
) -> None:
    profile = _create_profile(client, auth_headers)
    content = b"content-addressed evidence shared after a crashed restore"
    digest = hashlib.sha256(content).hexdigest()
    storage_path = f"assets/{digest[:2]}/{digest}"
    crashed_restore_user_id = test_user.id + 10_000

    prepare_restore_journal(
        crashed_restore_user_id,
        "a" * 64,
        [storage_path],
    )
    published_path, created = atomic_restore_write(
        crashed_restore_user_id,
        storage_path,
        content,
    )
    assert created is True

    db_session.add(
        CareerAsset(
            profile_id=profile["id"],
            kind="source_document",
            original_name="shared.txt",
            media_type="text/plain",
            sha256=digest,
            byte_size=len(content),
            storage_path=storage_path,
            normalized=False,
        )
    )
    db_session.commit()

    with pytest.raises(RestoreRolledBackError):
        _rollback_failed_restore(
            db_session,
            crashed_restore_user_id,
            ValueError("crashed restore resumed after another account bound the file"),
        )

    assert published_path.read_bytes() == content
    assert not (desktop_data_dir / ".restore" / f"user-{crashed_restore_user_id}").exists()


def test_desktop_vault_lock_times_out_for_competing_operation(desktop_data_dir):
    entered = threading.Event()
    release = threading.Event()

    def owner():
        with desktop_vault_lock(root=desktop_data_dir):
            entered.set()
            release.wait(timeout=2)

    thread = threading.Thread(target=owner)
    thread.start()
    assert entered.wait(timeout=1)
    try:
        with pytest.raises(VaultLockTimeout):
            with desktop_vault_lock(root=desktop_data_dir, timeout_seconds=0.1):
                pass
    finally:
        release.set()
        thread.join(timeout=1)
    assert not thread.is_alive()


def test_export_reads_one_sqlite_snapshot_while_a_writer_commits(desktop_data_dir):
    database_path = desktop_data_dir / "snapshot.db"
    ensure_sqlite_parent(f"sqlite:///{database_path.as_posix()}")
    local_engine = create_engine(
        f"sqlite:///{database_path}", connect_args={"check_same_thread": False}
    )
    event.listen(local_engine, "connect", configure_sqlite_connection)
    Base.metadata.create_all(local_engine)
    local_session = sessionmaker(bind=local_engine, autoflush=False, expire_on_commit=False)
    seed = local_session()
    owner = User(username="snapshot-owner", hashed_password="unused-local-hash")
    seed.add(owner)
    seed.flush()
    profile = CandidateProfile(
        user_id=owner.id,
        revision=1,
        display_name="Snapshot Before",
        headline="Stable export",
        summary="The archive must represent one point in time.",
        location={},
        work_authorization=[],
        preferences={},
    )
    seed.add(profile)
    seed.commit()
    user_id = owner.id
    profile_id = profile.id
    seed.close()

    profile_selected = threading.Event()
    writer_committed = threading.Event()
    writer_errors: list[BaseException] = []
    export_thread_id = threading.get_ident()

    def pause_after_profile_select(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ):
        if (
            threading.get_ident() == export_thread_id
            and "FROM candidate_profiles" in statement
            and not profile_selected.is_set()
        ):
            profile_selected.set()
            if not writer_committed.wait(timeout=5):
                raise AssertionError("concurrent writer did not commit during export")

    event.listen(local_engine, "after_cursor_execute", pause_after_profile_select)

    def write_goal() -> None:
        writer = local_session()
        try:
            if not profile_selected.wait(timeout=5):
                raise AssertionError("export did not reach the profile query")
            writer.add(
                CareerGoal(
                    profile_id=profile_id,
                    name="Committed during export",
                    is_primary=True,
                    payload={"target_roles": ["Staff Engineer"]},
                )
            )
            writer.commit()
        except BaseException as exc:
            writer_errors.append(exc)
        finally:
            writer.close()
            writer_committed.set()

    writer_thread = threading.Thread(target=write_goal)
    writer_thread.start()
    reader = local_session()
    try:
        archive_data = export_archive(reader, user_id)
    finally:
        reader.close()
    writer_thread.join(timeout=5)
    assert not writer_thread.is_alive()
    assert writer_errors == []

    with zipfile.ZipFile(BytesIO(archive_data)) as archive:
        payload = json.loads(archive.read("payload.json"))
    assert payload["tables"]["candidate_profiles"][0]["display_name"] == "Snapshot Before"
    assert payload["tables"]["career_goals"] == []

    verification = local_session()
    try:
        assert verification.query(CareerGoal).filter_by(profile_id=profile_id).count() == 1
    finally:
        verification.close()
        event.remove(local_engine, "after_cursor_execute", pause_after_profile_select)
        local_engine.dispose()
