"""HTTP contract tests for the local campaign workspace API."""

from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from pathlib import Path
from urllib.parse import quote

import pytest

from backend.applications.models import Application
from backend.campaigns.models import Campaign, CampaignApplication, CampaignArtifact
from backend.career.models import CandidateProfile, CareerAsset, SourceDocument
from backend.main import app
from backend.models import User
from backend.services.auth import get_password_hash
from backend.storage.atomic import resolve_data_path
from tests.backend.campaigns.fixture_builder import (
    build_fictional_campaign_zip,
    build_fictional_xlsx_bytes,
)


@pytest.fixture(autouse=True)
def campaign_api_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep every API publication inside a disposable local vault."""
    data_dir = tmp_path / "campaign-api-vault"
    monkeypatch.setattr("backend.storage.atomic.settings.DATA_DIR", str(data_dir))
    monkeypatch.setattr("backend.core.config.settings.DATA_DIR", str(data_dir))
    return data_dir


@pytest.fixture
def campaign_archive() -> bytes:
    return build_fictional_campaign_zip(credentials_count=2)


def _archive_upload(data: bytes, name: str = "campaign.zip") -> dict[str, tuple[str, bytes, str]]:
    return {"archive": (name, data, "application/zip")}


def _preview(client, auth_headers, archive: bytes):
    return client.post(
        "/api/v1/campaigns/preview",
        files=_archive_upload(archive),
        headers=auth_headers,
    )


def _import_campaign(
    client,
    auth_headers,
    archive: bytes,
    fingerprint: str,
    *,
    name: str = "Spring 2026 Search",
    profile_display_name: str = "Fictional Candidate",
):
    return client.post(
        "/api/v1/campaigns/import",
        files=_archive_upload(archive),
        data={
            "expected_fingerprint": fingerprint,
            "name": name,
            "profile_display_name": profile_display_name,
        },
        headers=auth_headers,
    )


def _preview_and_import(client, auth_headers, archive: bytes) -> tuple[dict, dict]:
    preview = _preview(client, auth_headers, archive)
    assert preview.status_code == 200, preview.text
    imported = _import_campaign(client, auth_headers, archive, preview.json()["fingerprint"])
    assert imported.status_code == 201, imported.text
    return preview.json(), imported.json()


def _second_user_headers(client, db_session) -> dict[str, str]:
    user = User(username="campaignviewer", hashed_password=get_password_hash("Viewerpass1"))
    db_session.add(user)
    db_session.commit()
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "campaignviewer", "password": "Viewerpass1"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _all_vault_files(data_dir: Path) -> set[Path]:
    return {path for path in data_dir.rglob("*") if path.is_file()} if data_dir.exists() else set()


def test_campaign_preview_requires_auth_and_is_side_effect_free(
    client,
    auth_headers,
    db_session,
    campaign_archive: bytes,
    campaign_api_storage: Path,
) -> None:
    unauthorized = client.post(
        "/api/v1/campaigns/preview",
        files=_archive_upload(campaign_archive),
    )
    assert unauthorized.status_code == 401

    before_files = _all_vault_files(campaign_api_storage)
    response = _preview(client, auth_headers, campaign_archive)
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["fingerprint"]) == 64
    assert set(body["fingerprint"]) <= set("0123456789abcdef")
    assert body["logical_application_count"] == 5
    assert body["tracker_rows"] == 4
    assert body["dossier_count"] == 3
    assert body["matched_count"] == 2
    assert body["tracker_only_count"] == 2
    assert body["dossier_only_count"] == 1
    assert body["credential_rows_omitted"] == 2
    assert body["requires_profile_name"] is True
    assert len(body["sample"]) <= 10
    assert "pass0" not in response.text
    assert "user0" not in response.text
    assert response.headers["cache-control"].startswith("no-store")

    db_session.expire_all()
    assert db_session.query(Campaign).count() == 0
    assert db_session.query(Application).count() == 0
    assert db_session.query(CandidateProfile).count() == 0
    assert db_session.query(CareerAsset).count() == 0
    assert db_session.query(SourceDocument).count() == 0
    assert _all_vault_files(campaign_api_storage) == before_files


def test_campaign_preview_maps_bounded_generic_errors(
    client,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    malformed = client.post(
        "/api/v1/campaigns/preview",
        files=_archive_upload(b"not a zip", "private-candidate-name.zip"),
        headers=auth_headers,
    )
    assert malformed.status_code == 400
    assert "private-candidate-name" not in malformed.text
    assert "not a zip" not in malformed.text

    invalid_xlsx = build_fictional_xlsx_bytes(applications_sheet_name="Wrong sheet")
    semantic = _preview(
        client,
        auth_headers,
        build_fictional_campaign_zip(xlsx_bytes=invalid_xlsx),
    )
    assert semantic.status_code == 422
    assert "Wrong sheet" not in semantic.text

    monkeypatch.setattr("backend.api.routes.campaigns.MAX_COMPRESSED_BYTES", 8)
    oversized = client.post(
        "/api/v1/campaigns/preview",
        files=_archive_upload(b"123456789"),
        headers=auth_headers,
    )
    assert oversized.status_code == 413
    assert "123456789" not in oversized.text


def test_campaign_import_is_created_then_idempotent_and_projects_application_links(
    client,
    auth_headers,
    db_session,
    campaign_archive: bytes,
) -> None:
    preview, imported = _preview_and_import(client, auth_headers, campaign_archive)
    assert imported == {
        "campaign_id": imported["campaign_id"],
        "fingerprint": preview["fingerprint"],
        "created": True,
        "application_count": 5,
        "artifact_count": preview["artifact_count"],
        "source_document_count": 4,
        "task_count": 1,
        "warning_count": len(preview["warnings"]),
    }
    uuid.UUID(imported["campaign_id"])

    replay = _import_campaign(
        client,
        auth_headers,
        campaign_archive,
        preview["fingerprint"],
        name="A harmless later display-name request",
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == {**imported, "created": False}

    listing = client.get("/api/v1/campaigns", headers=auth_headers)
    assert listing.status_code == 200, listing.text
    assert len(listing.json()) == 1
    campaign = listing.json()[0]
    assert campaign["id"] == imported["campaign_id"]
    assert campaign["name"] == "Spring 2026 Search"
    assert campaign["summary"]["application_count"] == 5
    assert campaign["summary_scope"] == "import_snapshot"
    serialized = json.dumps(campaign, sort_keys=True)
    assert "tracker_record" not in serialized
    assert "provenance" not in serialized
    assert "relative_path" not in serialized

    applications = client.get("/api/v1/applications", headers=auth_headers)
    assert applications.status_code == 200, applications.text
    linked = next(item for item in applications.json() if item["source_application_id"] == "APP-001")
    assert linked["campaign_id"] == imported["campaign_id"]
    assert linked["campaign_priority"] == "High"
    assert linked["campaign_platform"] == "LinkedIn"
    assert linked["campaign_category"] == "Engineering"

    manual = client.post(
        "/api/v1/applications",
        json={
            "manual_job": {
                "title": "Independent role",
                "company": "Independent company",
            }
        },
        headers=auth_headers,
    )
    assert manual.status_code == 201, manual.text
    summaries = client.get("/api/v1/applications", headers=auth_headers).json()
    manual_summary = next(item for item in summaries if item["id"] == manual.json()["id"])
    assert manual_summary["campaign_id"] is None
    assert manual_summary["source_application_id"] is None
    assert manual_summary["campaign_priority"] is None
    assert manual_summary["campaign_platform"] is None
    assert manual_summary["campaign_category"] is None

    db_session.expire_all()
    assert db_session.query(Campaign).count() == 1
    assert db_session.query(CampaignApplication).count() == 5


def test_campaign_import_rejects_stale_preview_without_writes(
    client,
    auth_headers,
    db_session,
    campaign_archive: bytes,
    campaign_api_storage: Path,
) -> None:
    preview = _preview(client, auth_headers, campaign_archive)
    assert preview.status_code == 200
    changed = build_fictional_campaign_zip(
        members={"assets/new-evidence.txt": "changed after preview"},
        credentials_count=2,
    )
    response = _import_campaign(
        client,
        auth_headers,
        changed,
        preview.json()["fingerprint"],
    )
    assert response.status_code == 409
    assert "changed after preview" not in response.text
    db_session.expire_all()
    assert db_session.query(Campaign).count() == 0
    assert db_session.query(CandidateProfile).count() == 0
    assert db_session.query(CareerAsset).count() == 0
    assert _all_vault_files(campaign_api_storage) == set()


def test_campaign_detail_filters_searches_and_paginates_bounded_projections(
    client,
    auth_headers,
    campaign_archive: bytes,
) -> None:
    _preview_body, imported = _preview_and_import(client, auth_headers, campaign_archive)
    base = f"/api/v1/campaigns/{imported['campaign_id']}"

    detail = client.get(base, headers=auth_headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["id"] == imported["campaign_id"]
    assert body["total_application_count"] == 5
    assert body["summary_scope"] == "import_snapshot"
    assert sum(body["live_stage_counts"].values()) == 5
    assert body["filtered_application_count"] == 5
    assert len(body["applications"]) == 5
    assert body["offset"] == 0
    assert body["limit"] <= 200
    assert "tracker_record" not in json.dumps(body["applications"])

    filtered = client.get(
        f"{base}?query=acme&stage=applied&priority=High&limit=1&offset=0",
        headers=auth_headers,
    )
    assert filtered.status_code == 200, filtered.text
    filtered_body = filtered.json()
    assert filtered_body["total_application_count"] == 5
    assert filtered_body["filtered_application_count"] == 1
    assert filtered_body["live_stage_counts"] == body["live_stage_counts"]
    assert [item["source_application_id"] for item in filtered_body["applications"]] == [
        "APP-001"
    ]

    for query in ("LinkedIn", "Engineering"):
        searched = client.get(f"{base}?query={query}", headers=auth_headers)
        assert searched.status_code == 200, searched.text
        assert [item["source_application_id"] for item in searched.json()["applications"]] == [
            "APP-001"
        ]

    empty_page = client.get(f"{base}?limit=1&offset=99", headers=auth_headers)
    assert empty_page.status_code == 200
    assert empty_page.json()["applications"] == []
    assert empty_page.json()["filtered_application_count"] == 5

    assert client.get(f"{base}?limit=0", headers=auth_headers).status_code == 422
    assert client.get(f"{base}?limit=201", headers=auth_headers).status_code == 422
    assert client.get(f"{base}?stage=unknown", headers=auth_headers).status_code == 422
    assert client.get(f"{base}?priority=unknown", headers=auth_headers).status_code == 422
    assert client.get(f"{base}?query={'x' * 201}", headers=auth_headers).status_code == 422
    for stage in (
        "saved",
        "preparing",
        "applied",
        "screening",
        "interview",
        "offer",
        "accepted",
        "rejected",
        "withdrawn",
        "archived",
    ):
        assert client.get(f"{base}?stage={stage}", headers=auth_headers).status_code == 200


def test_campaign_detail_separates_import_statuses_from_live_stage_changes(
    client,
    auth_headers,
    db_session,
    campaign_archive: bytes,
) -> None:
    _preview_body, imported = _preview_and_import(client, auth_headers, campaign_archive)
    base = f"/api/v1/campaigns/{imported['campaign_id']}"
    before = client.get(base, headers=auth_headers).json()
    link = (
        db_session.query(CampaignApplication)
        .filter(
            CampaignApplication.campaign_id == imported["campaign_id"],
            CampaignApplication.source_application_id == "APP-001",
        )
        .one()
    )
    assert link.application.current_stage == "applied"
    link.application.current_stage = "screening"
    db_session.commit()

    after = client.get(f"{base}?stage=screening&limit=1", headers=auth_headers).json()
    assert after["summary_scope"] == "import_snapshot"
    assert after["summary"]["status_counts"] == before["summary"]["status_counts"]
    assert after["live_stage_counts"].get("applied", 0) == before["live_stage_counts"]["applied"] - 1
    assert after["live_stage_counts"]["screening"] == before["live_stage_counts"].get("screening", 0) + 1
    assert sum(after["live_stage_counts"].values()) == after["total_application_count"]


def test_application_campaign_context_preserves_tracker_and_groups_artifacts(
    client,
    auth_headers,
    db_session,
    campaign_archive: bytes,
) -> None:
    _preview_body, imported = _preview_and_import(client, auth_headers, campaign_archive)
    db_session.expire_all()
    link = (
        db_session.query(CampaignApplication)
        .filter(
            CampaignApplication.campaign_id == imported["campaign_id"],
            CampaignApplication.source_application_id == "APP-001",
        )
        .one()
    )

    response = client.get(
        f"/api/v1/applications/{link.application_id}/campaign-context",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["campaign_id"] == imported["campaign_id"]
    assert body["campaign_name"] == "Spring 2026 Search"
    assert body["application_id"] == link.application_id
    assert body["source_application_id"] == "APP-001"
    assert body["source_status"] == "Applied"
    assert body["priority"] == "High"
    assert body["platform"] == "LinkedIn"
    assert body["category"] == "Engineering"
    assert body["found_at"] == "2026-01-10"
    assert body["applied_at"] == "2026-01-12"
    assert body["follow_up_at"] == "2026-01-26"
    assert body["last_update_at"] == "2026-01-15"
    assert body["tracker_record"]["Application ID"] == "APP-001"
    assert len(body["tracker_record"]) == 28
    assert set(body["provenance"]["sources"]) == {"tracker", "dossier"}
    assert set(body["artifact_groups"]) >= {
        "cv",
        "letter",
        "vacancy",
        "tracker",
        "profile",
        "goal",
        "story",
        "evidence",
        "image",
        "template",
        "script",
    }
    assert [item["display_name"] for item in body["artifact_groups"]["cv"]] == ["cv.pdf"]
    artifact = body["artifact_groups"]["cv"][0]
    assert set(artifact) == {
        "id",
        "display_name",
        "category",
        "media_type",
        "byte_size",
        "download_url",
    }
    assert artifact["download_url"] == (
        f"/api/v1/campaigns/{imported['campaign_id']}/artifacts/{artifact['id']}/download"
    )
    assert "<script" not in response.text.lower()


def test_campaign_artifact_download_is_owned_verified_and_inert(
    client,
    auth_headers,
    db_session,
    campaign_archive: bytes,
) -> None:
    _preview_body, imported = _preview_and_import(client, auth_headers, campaign_archive)
    db_session.expire_all()
    artifact = (
        db_session.query(CampaignArtifact)
        .filter(
            CampaignArtifact.campaign_id == imported["campaign_id"],
            CampaignArtifact.relative_path == "application-packets/APP-001/cv.pdf",
        )
        .one()
    )
    asset = db_session.get(CareerAsset, artifact.asset_id)
    assert asset is not None
    expected = resolve_data_path(asset.storage_path, create_root=False).read_bytes()
    endpoint = (
        f"/api/v1/campaigns/{imported['campaign_id']}/artifacts/{artifact.id}/download"
    )

    response = client.get(endpoint, headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.content == expected
    assert response.headers["content-length"] == str(len(expected))
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "cv.pdf" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"].startswith("no-store")
    assert response.headers["x-content-sha256"] == hashlib.sha256(expected).hexdigest()

    resolve_data_path(asset.storage_path, create_root=False).write_bytes(b"corrupt")
    corrupted = client.get(endpoint, headers=auth_headers)
    assert corrupted.status_code == 409
    assert corrupted.content != b"corrupt"
    assert asset.storage_path not in corrupted.text


def test_campaign_artifact_download_uses_ascii_safe_unicode_disposition(
    client,
    auth_headers,
    db_session,
) -> None:
    filename = "r\u00e9sum\u00e9-\u96ea.txt"
    archive = build_fictional_campaign_zip(
        members={f"assets/{filename}": b"synthetic unicode filename payload"}
    )
    _preview_body, imported = _preview_and_import(client, auth_headers, archive)
    db_session.expire_all()
    artifact = (
        db_session.query(CampaignArtifact)
        .filter(
            CampaignArtifact.campaign_id == imported["campaign_id"],
            CampaignArtifact.relative_path == f"assets/{filename}",
        )
        .one()
    )

    response = client.get(
        f"/api/v1/campaigns/{imported['campaign_id']}/artifacts/{artifact.id}/download",
        headers=auth_headers,
    )

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert f"filename*=UTF-8''{quote(filename, safe='')}" in disposition
    assert disposition.isascii()


def test_campaign_artifact_download_rejects_control_character_filename(
    client,
    auth_headers,
    db_session,
    campaign_archive: bytes,
) -> None:
    _preview_body, imported = _preview_and_import(client, auth_headers, campaign_archive)
    artifact = (
        db_session.query(CampaignArtifact)
        .filter(CampaignArtifact.campaign_id == imported["campaign_id"])
        .first()
    )
    assert artifact is not None
    artifact.display_name = "unsafe\r\nX-Injected-Header: yes.txt"
    db_session.commit()

    response = client.get(
        f"/api/v1/campaigns/{imported['campaign_id']}/artifacts/{artifact.id}/download",
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert "x-injected-header" not in response.headers


def test_campaign_reads_hide_unowned_and_missing_resources_without_existence_leakage(
    client,
    auth_headers,
    db_session,
    campaign_archive: bytes,
) -> None:
    _preview_body, imported = _preview_and_import(client, auth_headers, campaign_archive)
    db_session.expire_all()
    link = (
        db_session.query(CampaignApplication)
        .filter(CampaignApplication.campaign_id == imported["campaign_id"])
        .first()
    )
    artifact = (
        db_session.query(CampaignArtifact)
        .filter(CampaignArtifact.campaign_id == imported["campaign_id"])
        .first()
    )
    assert link is not None and artifact is not None
    other_headers = _second_user_headers(client, db_session)
    missing = str(uuid.uuid4())

    assert client.get("/api/v1/campaigns", headers=other_headers).json() == []
    cases = [
        (
            f"/api/v1/campaigns/{imported['campaign_id']}",
            f"/api/v1/campaigns/{missing}",
        ),
        (
            f"/api/v1/applications/{link.application_id}/campaign-context",
            f"/api/v1/applications/{missing}/campaign-context",
        ),
        (
            f"/api/v1/campaigns/{imported['campaign_id']}/artifacts/{artifact.id}/download",
            f"/api/v1/campaigns/{missing}/artifacts/{missing}/download",
        ),
    ]
    for owned_url, missing_url in cases:
        unowned = client.get(owned_url, headers=other_headers)
        absent = client.get(missing_url, headers=other_headers)
        assert unowned.status_code == absent.status_code == 404
        assert unowned.json() == absent.json()
        assert imported["campaign_id"] not in unowned.text


def test_all_campaign_routes_require_authentication(
    client,
    campaign_archive: bytes,
) -> None:
    identifier = str(uuid.uuid4())
    requests = [
        client.get("/api/v1/campaigns"),
        client.get(f"/api/v1/campaigns/{identifier}"),
        client.get(f"/api/v1/applications/{identifier}/campaign-context"),
        client.get(f"/api/v1/campaigns/{identifier}/artifacts/{identifier}/download"),
        client.post(
            "/api/v1/campaigns/import",
            files=_archive_upload(campaign_archive),
            data={"expected_fingerprint": "0" * 64},
        ),
    ]
    assert [response.status_code for response in requests] == [401, 401, 401, 401, 401]


def test_campaign_multipart_routes_have_explicit_preparse_body_limits() -> None:
    middleware = next(
        item for item in app.user_middleware if item.cls.__name__ == "RequestBodyLimitMiddleware"
    )
    route_limits = middleware.kwargs["route_max_bytes"]
    preview_limit = route_limits[("POST", "/api/v1/campaigns/preview")]
    import_limit = route_limits[("POST", "/api/v1/campaigns/import")]
    assert preview_limit == import_limit
    assert 128 * 1024 * 1024 < preview_limit <= 129 * 1024 * 1024


def test_semantic_preview_error_fixture_is_a_valid_outer_zip() -> None:
    """Guard the semantic-error test so it cannot accidentally exercise malformed ZIP handling."""
    data = build_fictional_campaign_zip(
        xlsx_bytes=build_fictional_xlsx_bytes(applications_sheet_name="Wrong sheet")
    )
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
