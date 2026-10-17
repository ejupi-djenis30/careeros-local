"""Provider installations are portable before a candidate profile exists."""

import copy
import json
import uuid
import zipfile
from datetime import timedelta
from io import BytesIO

import pytest

from backend.career.deletion import begin_vault_maintenance
from backend.career.models import CandidateProfile
from backend.core.config import settings
from backend.models import User
from backend.models.auth_session import AuthSession
from backend.models.user import VAULT_STATE_READY, VAULT_STATE_RESTORE_PENDING
from backend.portability.archive import ArchiveError, _validated_members
from backend.portability.manifest import canonical_json, expected_tables, sha256
from backend.portability.provider_records import provider_restore_was_published
from backend.portability.restore import RestoreRolledBackError, _decode_payload, restore_archive
from backend.providers.configuration.models import JobProviderConfiguration
from backend.services.auth import ACCESS_PURPOSE_SESSION, get_password_hash
from tests.backend.providers.configuration.helpers import json_provider_payload


@pytest.fixture
def provider_only_archive(client, auth_headers, db_session, test_user, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    assert db_session.query(CandidateProfile).filter_by(user_id=test_user.id).count() == 0
    created = client.post(
        "/api/v1/job-providers",
        headers=auth_headers,
        json=json_provider_payload().model_dump(mode="json"),
    )
    assert created.status_code == 201, created.text
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    return exported.content


def _login(client):
    response = client.post(
        "/api/v1/auth/login", data={"username": "globaladmin", "password": "Globalpass1"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _reset(client, auth_headers):
    response = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert response.status_code == 204, response.text


def _rewrite(data, change, *, version=9):
    with zipfile.ZipFile(BytesIO(data)) as source:
        members = {name: source.read(name) for name in source.namelist()}
    payload = json.loads(members["payload.json"])
    change(payload)
    if version < 9:
        payload["tables"] = {
            name: rows
            for name, rows in payload["tables"].items()
            if name in expected_tables(version)
        }
    members["payload.json"] = canonical_json(payload)
    manifest = json.loads(members["manifest.json"])
    manifest.update(
        format_version=version,
        record_counts={name: len(rows) for name, rows in payload["tables"].items()},
    )
    for entry in manifest["entries"]:
        entry.update(sha256=sha256(members[entry["path"]]), byte_size=len(members[entry["path"]]))
    members["manifest.json"] = canonical_json(manifest)
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for name, content in members.items():
            target.writestr(name, content)
    return output.getvalue()


def test_real_api_provider_only_export_inspect_reset_restore_creates_no_profile(
    client, auth_headers, db_session, test_user, provider_only_archive
):
    with zipfile.ZipFile(BytesIO(provider_only_archive)) as archive:
        payload = json.loads(archive.read("payload.json"))
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["format_version"] == 9
    assert manifest["record_counts"]["candidate_profiles"] == 0
    assert payload["tables"]["candidate_profiles"] == []
    assert payload["file_bindings"] == []
    row = payload["tables"]["job_provider_configurations"][0]
    assert "user_id" not in row
    assert row["request_config"]["headers"] == {}
    assert row["enabled"] is False
    inspect = client.post(
        "/api/v1/portability/inspect",
        headers=auth_headers,
        files={"file": ("providers.zip", provider_only_archive)},
    )
    assert inspect.status_code == 200, inspect.text
    assert inspect.json()["compatible"] is True
    assert inspect.json()["restorable"] is False
    _reset(client, auth_headers)
    headers = _login(client)
    inspect = client.post(
        "/api/v1/portability/inspect",
        headers=headers,
        files={"file": ("providers.zip", provider_only_archive)},
    )
    assert inspect.status_code == 200, inspect.text
    assert inspect.json()["restorable"] is True
    restored = client.post(
        "/api/v1/portability/restore",
        headers=headers,
        files={"file": ("providers.zip", provider_only_archive)},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored_records"]["candidate_profiles"] == 0
    db_session.expire_all()
    assert db_session.query(CandidateProfile).filter_by(user_id=test_user.id).count() == 0
    installed = db_session.query(JobProviderConfiguration).filter_by(user_id=test_user.id).one()
    assert installed.enabled is False
    assert installed.request_config["headers"] == {}
    assert db_session.get(User, test_user.id).vault_lifecycle_state == VAULT_STATE_READY


def test_real_api_provider_only_restore_rebinds_only_to_authenticated_destination(
    client, auth_headers, db_session, test_user, provider_only_archive
):
    _reset(client, auth_headers)
    destination = User(
        username="provider-backup-destination", hashed_password=get_password_hash("Otherpass1")
    )
    db_session.add(destination)
    db_session.commit()
    login = client.post(
        "/api/v1/auth/login", data={"username": destination.username, "password": "Otherpass1"}
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    restored = client.post(
        "/api/v1/portability/restore",
        headers=headers,
        files={"file": ("providers.zip", provider_only_archive)},
    )
    assert restored.status_code == 200, restored.text
    db_session.expire_all()
    assert db_session.query(CandidateProfile).count() == 0
    assert db_session.query(JobProviderConfiguration).filter_by(user_id=test_user.id).count() == 0
    provider = db_session.query(JobProviderConfiguration).filter_by(user_id=destination.id).one()
    assert provider.enabled is False
    assert provider.request_config["headers"] == {}


def test_export_refuses_provider_inventory_that_restore_cannot_accept(
    client, auth_headers, db_session, provider_only_archive
):
    original = db_session.query(JobProviderConfiguration).one()
    template = {
        column.name: getattr(original, column.name)
        for column in JobProviderConfiguration.__table__.columns
    }
    db_session.add_all(
        [
            JobProviderConfiguration(
                **{
                    **copy.deepcopy(template),
                    "id": str(uuid.uuid4()),
                    "key": f"extra_provider_{index}",
                }
            )
            for index in range(50)
        ]
    )
    db_session.commit()
    assert db_session.query(JobProviderConfiguration).count() == 51
    rejected = client.get("/api/v1/portability/export", headers=auth_headers)
    assert rejected.status_code == 404
    assert "test-provider-secret" not in rejected.text


@pytest.mark.parametrize("version", range(1, 9))
def test_legacy_versions_still_reject_archives_without_a_profile(
    provider_only_archive, db_session, version
):
    archive = _rewrite(provider_only_archive, lambda _payload: None, version=version)
    with pytest.raises(ArchiveError):
        manifest, members = _validated_members(archive)
        _decode_payload(db_session, manifest, members, enforce_destination_ids=False)


@pytest.mark.parametrize(
    "corruption", ["empty", "profile_child", "file_binding", "too_many_providers"]
)
def test_profileless_archive_rejects_missing_providers_or_unbound_domain_data(
    provider_only_archive, db_session, corruption
):
    def corrupt(payload):
        if corruption == "empty":
            payload["tables"]["job_provider_configurations"] = []
        elif corruption == "too_many_providers":
            original = payload["tables"]["job_provider_configurations"][0]
            payload["tables"]["job_provider_configurations"] = [
                {**copy.deepcopy(original), "id": str(uuid.uuid4()), "key": f"provider_{index}"}
                for index in range(51)
            ]
        elif corruption == "profile_child":
            payload["tables"]["career_facts"] = [
                {"id": str(uuid.uuid4()), "profile_id": str(uuid.uuid4())}
            ]
        else:
            payload["file_bindings"] = [
                {
                    "table": "career_assets",
                    "record_id": str(uuid.uuid4()),
                    "storage_path": "unused",
                    "member": "unused",
                }
            ]

    archive = _rewrite(provider_only_archive, corrupt)
    with pytest.raises(ArchiveError):
        manifest, members = _validated_members(archive)
        _decode_payload(db_session, manifest, members, enforce_destination_ids=False)


@pytest.mark.parametrize("failure", ["before_commit", "after_commit"])
def test_provider_only_restore_resolves_commit_outcome_without_profile(
    client, auth_headers, db_session, test_user, provider_only_archive, monkeypatch, failure
):
    _reset(client, auth_headers)
    authority = db_session.query(AuthSession).filter_by(user_id=test_user.id, revoked_at=None).one()
    begin_vault_maintenance(
        db_session,
        test_user.id,
        authority.id,
        VAULT_STATE_RESTORE_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
        maintenance_fingerprint=sha256(provider_only_archive),
    )
    real_commit = db_session.commit
    raised = False

    def injected_commit():
        nonlocal raised
        if failure == "after_commit":
            real_commit()
        if not raised:
            raised = True
            raise RuntimeError("synthetic provider restore commit failure")

    monkeypatch.setattr(db_session, "commit", injected_commit)
    if failure == "before_commit":
        with pytest.raises(RestoreRolledBackError):
            restore_archive(db_session, test_user.id, provider_only_archive)
    else:
        restored = restore_archive(db_session, test_user.id, provider_only_archive)
        assert restored.restored_records["job_provider_configurations"] == 1
    db_session.expire_all()
    assert db_session.query(CandidateProfile).count() == 0
    assert db_session.query(JobProviderConfiguration).filter_by(user_id=test_user.id).count() == (
        failure == "after_commit"
    )
    assert db_session.get(User, test_user.id).vault_lifecycle_state == (
        VAULT_STATE_READY if failure == "after_commit" else VAULT_STATE_RESTORE_PENDING
    )


@pytest.mark.parametrize("modified_timestamp", ["created_at", "updated_at"])
def test_provider_commit_identity_rejects_partial_foreign_or_modified_inventory(
    db_session, test_user, provider_only_archive, modified_timestamp
):
    manifest, members = _validated_members(provider_only_archive)
    decoded, _, _, _ = _decode_payload(db_session, manifest, members, enforce_destination_ids=False)
    expected = decoded["job_provider_configurations"]
    row = db_session.query(JobProviderConfiguration).one()
    # The current original still has a header secret; it is not proof of restored contents.
    with pytest.raises(ValueError, match="contents"):
        provider_restore_was_published(db_session, test_user.id, expected)
    # Restore inserts the complete archived record, including its original timestamps.
    # Updating the original instead would generate a different onupdate timestamp.
    db_session.delete(row)
    db_session.flush()
    row = JobProviderConfiguration(**copy.deepcopy(expected[0]), user_id=test_user.id)
    db_session.add(row)
    db_session.commit()
    assert provider_restore_was_published(db_session, test_user.id, expected) is True
    extra = copy.deepcopy(expected[0])
    extra["id"] = str(uuid.uuid4())
    with pytest.raises(ValueError):
        provider_restore_was_published(db_session, test_user.id, [*expected, extra])
    foreign = User(username="foreign-provider-archive-owner", hashed_password="unused")
    db_session.add(foreign)
    db_session.commit()
    with pytest.raises(ValueError):
        provider_restore_was_published(db_session, foreign.id, expected)
    modified = copy.deepcopy(expected)
    modified[0][modified_timestamp] += timedelta(seconds=1)
    with pytest.raises(ValueError, match="contents"):
        provider_restore_was_published(db_session, test_user.id, modified)
