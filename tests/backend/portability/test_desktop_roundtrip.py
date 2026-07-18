import hashlib
import json
import threading
import zipfile
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.ai.models import AIExecution
from backend.career.models import CandidateProfile, CareerAsset
from backend.core.config import settings
from backend.desktop.lifecycle import VaultLockTimeout, desktop_vault_lock
from backend.portability.restore import restore_archive
from backend.storage.atomic import resolve_data_path

PROFILE = {
    "expected_revision": 0,
    "display_name": "Grace Hopper",
    "headline": "Compiler pioneer",
    "summary": "Turns evidence into reliable systems.",
    "email": "grace@example.test",
    "location": {"city": "New York", "country": "US"},
    "preferences": {},
    "facts": [],
    "goals": [],
}


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


def _convert_to_version(data: bytes, version: int) -> bytes:
    with zipfile.ZipFile(BytesIO(data), "r") as source:
        files = {name: source.read(name) for name in source.namelist()}
    payload = json.loads(files["payload.json"])
    removed_tables = ["search_profiles", "scraped_jobs", "jobs", "preference_signals"]
    if version == 1:
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


def test_v3_archive_restores_ai_audit_and_v2_v1_remain_compatible(
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
    assert manifest["format_version"] == 3
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

    original_atomic_write = restore_module.atomic_write
    calls = 0

    def interrupted_write(relative_path, content):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated interrupted upgrade")
        return original_atomic_write(relative_path, content)

    monkeypatch.setattr(restore_module, "atomic_write", interrupted_write)
    with pytest.raises(OSError, match="interrupted upgrade"):
        restore_archive(db_session, test_user.id, exported.content)

    db_session.expire_all()
    assert db_session.query(CandidateProfile).filter_by(user_id=test_user.id).count() == 0
    assert all(not resolve_data_path(path).exists() for path in paths)


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
