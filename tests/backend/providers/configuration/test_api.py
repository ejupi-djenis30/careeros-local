from __future__ import annotations

from backend.providers.configuration.schemas import PRESERVE_SECRET, REDACTED_SECRET
from tests.backend.providers.configuration.helpers import json_provider_payload

SWISS_PACK_KEYS = [
    "job_room",
    "swissdevjobs",
    "adecco",
    "canton_bern",
    "canton_solothurn",
    "canton_lucerne",
    "fmh_doctor_jobs",
    "vmi_npo_jobs",
    "swissolar_jobs",
    "kampajobs",
    "jobs_for_change",
]


def test_authenticated_provider_api_crud_and_no_store(client, auth_headers) -> None:
    payload = json_provider_payload().model_dump(mode="json")
    created = client.post("/api/v1/job-providers", json=payload, headers=auth_headers)

    assert created.status_code == 201, created.text
    assert created.headers["cache-control"] == "no-store, max-age=0"
    body = created.json()
    assert body["request"]["headers"]["X-API-Key"] == REDACTED_SECRET
    assert "test-provider-secret" not in created.text

    catalog = client.get("/api/v1/job-providers", headers=auth_headers)
    assert catalog.status_code == 200
    assert [item["key"] for item in catalog.json()["installed"]] == ["example_jobs"]
    assert [item["id"] for item in catalog.json()["available_packs"]] == [
        "careeros.switzerland.core"
    ]

    update = {
        key: value
        for key, value in body.items()
        if key
        not in {
            "id",
            "revision",
            "native_adapter_id",
            "source_pack_id",
            "source_pack_version",
            "has_secrets",
            "created_at",
            "updated_at",
        }
    }
    update["expected_revision"] = body["revision"]
    update["request"]["headers"]["X-API-Key"] = PRESERVE_SECRET
    updated = client.put(
        f"/api/v1/job-providers/{body['id']}",
        json=update,
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2
    assert updated.json()["request"]["headers"]["X-API-Key"] == REDACTED_SECRET

    stale = client.put(
        f"/api/v1/job-providers/{body['id']}",
        json=update,
        headers=auth_headers,
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"

    deleted = client.delete(
        f"/api/v1/job-providers/{body['id']}?expected_revision=2",
        headers=auth_headers,
    )
    assert deleted.status_code == 204


def test_provider_registry_starts_empty_and_swiss_pack_requires_explicit_activation(
    client, auth_headers
) -> None:
    catalog = client.get("/api/v1/job-providers", headers=auth_headers)

    assert catalog.status_code == 200
    assert catalog.json()["installed"] == []
    assert [pack["id"] for pack in catalog.json()["available_packs"]] == [
        "careeros.switzerland.core"
    ]

    imported = client.post(
        "/api/v1/job-providers/packs/careeros.switzerland.core/import",
        json={"activate": False},
        headers=auth_headers,
    )

    assert imported.status_code == 201, imported.text
    body = imported.json()
    assert body["source_id"] == "careeros.switzerland.core"
    assert body["activated"] is False
    assert [provider["key"] for provider in body["imported"]] == SWISS_PACK_KEYS
    assert [provider["adapter_kind"] for provider in body["imported"]] == [
        "native",
        "native",
        "native",
        *("html" for _ in range(8)),
    ]
    assert all(provider["enabled"] is False for provider in body["imported"])

    job_room = body["imported"][0]
    enabled = client.patch(
        f"/api/v1/job-providers/{job_room['id']}/state",
        json={"expected_revision": 1, "enabled": True},
        headers=auth_headers,
    )

    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["enabled"] is True
    assert enabled.json()["revision"] == 2

    duplicate = client.post(
        "/api/v1/job-providers/packs/careeros.switzerland.core/import",
        json={"activate": False},
        headers=auth_headers,
    )
    assert duplicate.status_code == 409
    after = client.get("/api/v1/job-providers", headers=auth_headers).json()
    assert len(after["installed"]) == len(SWISS_PACK_KEYS)


def test_provider_api_rejects_private_destination(client, auth_headers) -> None:
    payload = json_provider_payload().model_dump(mode="json")
    payload["request"]["base_url"] = "https://127.0.0.1"

    response = client.post(
        "/api/v1/job-providers/validate",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_provider_configuration"
    assert "127.0.0.1" not in response.text
