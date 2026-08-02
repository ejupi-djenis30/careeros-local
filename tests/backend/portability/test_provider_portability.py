from __future__ import annotations

import json
import zipfile
from io import BytesIO

from backend.core.config import settings
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
) -> None:
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
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
    assert manifest["format_version"] == 7
    assert manifest["record_counts"]["job_provider_configurations"] == 1
    assert row["request_config"]["headers"] == {}
    assert row["enabled"] is False
    assert b"test-provider-secret" not in exported.content

    deleted = client.delete(
        "/api/v1/career-profile",
        headers={**auth_headers, "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT"},
    )
    assert deleted.status_code == 204, deleted.text
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
