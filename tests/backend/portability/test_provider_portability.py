from __future__ import annotations

import json
import zipfile
from io import BytesIO

import pytest

from backend.career.models import CandidateProfile
from backend.core.config import settings
from backend.models import User
from backend.portability.manifest import canonical_json, sha256
from backend.providers.configuration.models import JobProviderConfiguration
from backend.providers.configuration.service import ProviderConfigurationService
from tests.backend.providers.configuration.helpers import json_provider_payload

PROFILE = {
    "expected_revision": 0,
    "display_name": "Provider Owner",
    "headline": "Platform engineer",
    "summary": "Builds reliable systems.",
    "email": "owner@example.test",
    "location": {"city": "Zurich", "country": "CH"},
    "preferences": {},
    "facts": [],
    "goals": [],
}

SWISS_NATIVE_KEYS = {"job_room", "swissdevjobs", "adecco"}
SWISS_DECLARATIVE_KEYS = {
    "canton_bern",
    "canton_solothurn",
    "canton_lucerne",
    "fmh_doctor_jobs",
    "vmi_npo_jobs",
    "swissolar_jobs",
    "kampajobs",
    "jobs_for_change",
}


def _login(client) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "globaladmin", "password": "Globalpass1"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_provider_round_trip_strips_headers_and_requires_fresh_network_consent(
    client,
    auth_headers,
    monkeypatch,
    tmp_path,
    db_session,
    test_user,
) -> None:
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    neighbor = User(username="neighbor-provider-owner", hashed_password="unused")
    db_session.add(neighbor)
    db_session.commit()
    neighboring_provider = ProviderConfigurationService(db_session).create(
        neighbor.id, json_provider_payload()
    )
    profile = client.put("/api/v1/career-profile", json=PROFILE, headers=auth_headers)
    assert profile.status_code == 200, profile.text
    provider = client.post(
        "/api/v1/job-providers",
        json=json_provider_payload().model_dump(mode="json"),
        headers=auth_headers,
    )
    assert provider.status_code == 201, provider.text

    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(BytesIO(exported.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        payload = json.loads(archive.read("payload.json"))
    row = payload["tables"]["job_provider_configurations"][0]
    assert manifest["format_version"] == 9
    assert manifest["record_counts"]["job_provider_configurations"] == 1
    assert row["request_config"]["headers"] == {}
    assert row["enabled"] is False
    assert b"test-provider-secret" not in exported.content

    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text
    assert db_session.query(JobProviderConfiguration).filter_by(user_id=test_user.id).count() == 0
    assert (
        ProviderConfigurationService(db_session).get(neighbor.id, neighboring_provider.id).enabled
        is True
    )
    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("provider-backup.zip", exported.content, "application/zip")},
        headers=_login(client),
    )
    assert restored.status_code == 200, restored.text

    catalog = client.get("/api/v1/job-providers", headers=_login(client))
    assert catalog.status_code == 200
    restored_provider = catalog.json()["installed"][0]
    assert restored_provider["key"] == "example_jobs"
    assert restored_provider["enabled"] is False
    assert restored_provider["request"]["headers"] == {}


def test_imported_mixed_pack_round_trip_preserves_manifest_but_revokes_network_consent(
    client,
    auth_headers,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    profile = client.put("/api/v1/career-profile", json=PROFILE, headers=auth_headers)
    assert profile.status_code == 200, profile.text
    imported = client.post(
        "/api/v1/job-providers/packs/careeros.switzerland.core/import",
        json={"activate": True},
        headers=auth_headers,
    )
    assert imported.status_code == 201, imported.text

    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(BytesIO(exported.content)) as archive:
        payload = json.loads(archive.read("payload.json"))
    rows = payload["tables"]["job_provider_configurations"]
    assert {row["key"] for row in rows} == SWISS_NATIVE_KEYS | SWISS_DECLARATIVE_KEYS
    assert all(
        row["source_pack_id"] == "careeros.switzerland.core"
        and row["source_pack_version"] == "1.1.0"
        for row in rows
    )
    native_rows = [row for row in rows if row["key"] in SWISS_NATIVE_KEYS]
    declarative_rows = [row for row in rows if row["key"] in SWISS_DECLARATIVE_KEYS]
    assert all(
        row["adapter_kind"] == "native"
        and row["request_config"] is None
        and row["extraction_config"] is None
        for row in native_rows
    )
    assert all(
        row["adapter_kind"] == "html"
        and row["request_config"]["headers"] == {}
        and row["extraction_config"]["item_selector"]
        for row in declarative_rows
    )

    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text
    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("native-provider-backup.zip", exported.content, "application/zip")},
        headers=_login(client),
    )
    assert restored.status_code == 200, restored.text

    catalog = client.get("/api/v1/job-providers", headers=_login(client)).json()
    assert len(catalog["installed"]) == len(SWISS_NATIVE_KEYS | SWISS_DECLARATIVE_KEYS)
    assert all(provider["enabled"] is False for provider in catalog["installed"])


def _rewrite_provider_archive(data, change, *, version=9):
    with zipfile.ZipFile(BytesIO(data)) as source:
        members = {name: source.read(name) for name in source.namelist()}
    payload = json.loads(members["payload.json"])
    change(payload)
    members["payload.json"] = canonical_json(payload)
    manifest = json.loads(members["manifest.json"])
    manifest["format_version"] = version
    manifest["record_counts"] = {name: len(rows) for name, rows in payload["tables"].items()}
    for entry in manifest["entries"]:
        entry["sha256"] = sha256(members[entry["path"]])
        entry["byte_size"] = len(members[entry["path"]])
    members["manifest.json"] = canonical_json(manifest)
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for name, content in members.items():
            target.writestr(name, content)
    return output.getvalue()


@pytest.mark.parametrize("corruption", ["private_destination", "secret_header", "native_id"])
def test_self_checksummed_provider_archive_is_validated_before_restore(
    client, auth_headers, monkeypatch, tmp_path, db_session, test_user, corruption
):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    assert (
        client.put("/api/v1/career-profile", json=PROFILE, headers=auth_headers).status_code == 200
    )
    assert (
        client.post(
            "/api/v1/job-providers",
            json=json_provider_payload().model_dump(mode="json"),
            headers=auth_headers,
        ).status_code
        == 201
    )
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200

    def corrupt(payload):
        row = payload["tables"]["job_provider_configurations"][0]
        row["enabled"] = True
        if corruption == "private_destination":
            row["request_config"]["base_url"] = "https://127.0.0.1"
        elif corruption == "secret_header":
            row["request_config"]["headers"] = {"X-Innocuous": "synthetic-secret"}
        else:
            row.update(
                adapter_kind="native",
                native_adapter_id="unreviewed_adapter",
                key="unreviewed_adapter",
                request_config=None,
                extraction_config=None,
            )

    crafted = _rewrite_provider_archive(exported.content, corrupt)
    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204
    headers = _login(client)
    rejected = client.post(
        "/api/v1/portability/restore",
        files={"file": ("crafted.zip", crafted, "application/zip")},
        headers=headers,
    )
    assert rejected.status_code == 422, rejected.text
    assert db_session.query(JobProviderConfiguration).filter_by(user_id=test_user.id).count() == 0
    assert db_session.query(CandidateProfile).filter_by(user_id=test_user.id).count() == 0
    valid = client.post(
        "/api/v1/portability/restore",
        files={"file": ("valid.zip", exported.content, "application/zip")},
        headers=headers,
    )
    assert valid.status_code == 200, valid.text


def test_v8_archive_upgrades_to_empty_provider_inventory_without_network_consent(
    client, auth_headers, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    assert (
        client.put("/api/v1/career-profile", json=PROFILE, headers=auth_headers).status_code == 200
    )
    exported = client.get("/api/v1/portability/export", headers=auth_headers)
    assert exported.status_code == 200
    legacy = _rewrite_provider_archive(
        exported.content,
        lambda payload: payload["tables"].pop("job_provider_configurations"),
        version=8,
    )
    assert (
        client.delete(
            "/api/v1/career-profile",
            headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
        ).status_code
        == 204
    )
    headers = _login(client)
    restored = client.post(
        "/api/v1/portability/restore",
        files={"file": ("v8.zip", legacy, "application/zip")},
        headers=headers,
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["format_version"] == 8
    assert restored.json()["restored_records"]["job_provider_configurations"] == 0
    assert client.get("/api/v1/job-providers", headers=_login(client)).json()["installed"] == []
