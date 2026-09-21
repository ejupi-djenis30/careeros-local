"""Portable-archive and lifecycle contracts for campaign workspaces."""

from __future__ import annotations

import json
import uuid
import zipfile
from datetime import UTC, datetime
from io import BytesIO

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.applications.models import Application
from backend.campaigns.models import Campaign, CampaignApplication, CampaignArtifact
from backend.campaigns.parser import parse_campaign_workspace
from backend.campaigns.service import import_campaign
from backend.career.deletion import begin_vault_maintenance, delete_complete_vault
from backend.career.models import CandidateProfile, CareerAsset
from backend.core.config import settings
from backend.db.base import Base, configure_sqlite_connection, ensure_sqlite_parent
from backend.models import User
from backend.models.user import VAULT_STATE_ERASURE_PENDING, VAULT_STATE_RESET_PENDING
from backend.portability.archive import ArchiveConflictError, ArchiveError, export_archive
from backend.portability.inspection import inspect_archive
from backend.portability.manifest import (
    CURRENT_ARCHIVE_VERSION,
    SUPPORTED_ARCHIVE_VERSIONS,
    canonical_json,
    expected_tables,
    sha256,
)
from backend.portability.restore import restore_archive
from backend.services.auth import ACCESS_PURPOSE_SESSION
from backend.services.auth_sessions import issue_auth_session
from backend.storage.atomic import resolve_data_path
from tests.backend.campaigns.fixture_builder import (
    build_fictional_campaign_zip,
    build_fictional_xlsx_bytes,
)


@pytest.fixture
def campaign_v8_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path / "vault"))
    database_url = f"sqlite:///{(tmp_path / 'campaign-v8.sqlite').as_posix()}"
    ensure_sqlite_parent(database_url)
    engine = create_engine(database_url)
    event.listen(engine, "connect", configure_sqlite_connection)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = User(username="campaign-v8-owner", hashed_password="synthetic")
        foreign = User(username="campaign-v8-foreign", hashed_password="synthetic")
        db.add_all([owner, foreign])
        db.commit()
        yield db, owner, foreign
    engine.dispose()


def _seed_campaign(db: Session, owner: User):
    archive = build_fictional_campaign_zip(credentials_count=2)
    parsed = parse_campaign_workspace(archive)
    result = import_campaign(
        db,
        user_id=owner.id,
        archive_bytes=archive,
        expected_fingerprint=parsed.fingerprint,
        imported_at=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
        campaign_name="Synthetic portable campaign",
        profile_display_name="Synthetic Candidate",
    )
    db.expire_all()
    return result


def _payload(data: bytes) -> dict:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return json.loads(archive.read("payload.json"))


def _manifest(data: bytes) -> dict:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return json.loads(archive.read("manifest.json"))


def _rewrite(data: bytes, change) -> bytes:
    with zipfile.ZipFile(BytesIO(data)) as source:
        members = {name: source.read(name) for name in source.namelist()}
    payload = json.loads(members["payload.json"])
    change(payload)
    members["payload.json"] = canonical_json(payload)
    manifest = json.loads(members["manifest.json"])
    manifest["record_counts"] = {
        name: len(rows) for name, rows in payload["tables"].items()
    }
    for entry in manifest["entries"]:
        entry.update(
            sha256=sha256(members[entry["path"]]),
            byte_size=len(members[entry["path"]]),
        )
    members["manifest.json"] = canonical_json(manifest)
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for name, content in members.items():
            target.writestr(name, content)
    return output.getvalue()


def _duplicate_application_order(payload: dict) -> None:
    rows = payload["tables"]["campaign_applications"]
    rows[1]["source_order"] = rows[0]["source_order"]


def _duplicate_artifact_order(payload: dict) -> None:
    rows = payload["tables"]["campaign_artifacts"]
    rows[1]["source_order"] = rows[0]["source_order"]


def _casefold_artifact_path_collision(payload: dict) -> None:
    rows = payload["tables"]["campaign_artifacts"]
    rows[1]["relative_path"] = rows[0]["relative_path"].swapcase()
    rows[1]["display_name"] = rows[0]["display_name"].swapcase()


def _unicode_artifact_path_collision(payload: dict) -> None:
    rows = payload["tables"]["campaign_artifacts"]
    rows[0]["relative_path"] = "application-packets/APP-001/caf\u00e9.txt"
    rows[0]["display_name"] = "caf\u00e9.txt"
    rows[1]["relative_path"] = "application-packets/APP-001/cafe\u0301.txt"
    rows[1]["display_name"] = "cafe\u0301.txt"


def _noncanonical_provenance_order(payload: dict) -> None:
    rows = payload["tables"]["campaign_applications"]
    matched = next(
        row for row in rows
        if set(row["provenance"]["sources"]) == {"tracker", "dossier"}
    )
    matched["provenance"]["sources"] = ["dossier", "tracker"]


def _invalid_packet_dir_shape(payload: dict) -> None:
    rows = payload["tables"]["campaign_applications"]
    dossier = next(row for row in rows if "dossier" in row["provenance"]["sources"])
    dossier["provenance"]["packet_dir"] = {"private": "value"}


def _missing_dossier_packet_dir(payload: dict) -> None:
    rows = payload["tables"]["campaign_applications"]
    dossier = next(row for row in rows if "dossier" in row["provenance"]["sources"])
    dossier["provenance"].pop("packet_dir")


def _tracker_only_packet_dir(payload: dict) -> None:
    rows = payload["tables"]["campaign_applications"]
    tracker_only = next(
        row for row in rows if row["provenance"]["sources"] == ["tracker"]
    )
    tracker_only["provenance"]["packet_dir"] = "must-not-cross-this-boundary"


def _in_range_task_count_mismatch(payload: dict) -> None:
    summary = payload["tables"]["campaigns"][0]["summary"]
    summary["task_count"] = 0 if summary["task_count"] else 1


def _application_order_gap(payload: dict) -> None:
    rows = payload["tables"]["campaign_applications"]
    last = max(rows, key=lambda row: row["source_order"])
    last["source_order"] += 1


def _artifact_order_gap(payload: dict) -> None:
    rows = payload["tables"]["campaign_artifacts"]
    last = max(rows, key=lambda row: row["source_order"])
    last["source_order"] += 1


def _boolean_status_count(payload: dict) -> None:
    counts = payload["tables"]["campaigns"][0]["summary"]["status_counts"]
    key = next(key for key, value in counts.items() if value == 1)
    counts[key] = True


def _control_character_artifact_path(payload: dict) -> None:
    row = payload["tables"]["campaign_artifacts"][0]
    row["relative_path"] = "assets/unsafe\r\nname.txt"
    row["display_name"] = "unsafe\r\nname.txt"


def _drive_like_artifact_path(payload: dict) -> None:
    row = payload["tables"]["campaign_artifacts"][0]
    row["relative_path"] = "assets/C:unsafe.txt"
    row["display_name"] = "C:unsafe.txt"


def _reset(db: Session, owner: User) -> dict[str, int]:
    authority = issue_auth_session(db, owner)
    begin_vault_maintenance(
        db,
        owner.id,
        authority.session_id,
        VAULT_STATE_RESET_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
    )
    return delete_complete_vault(
        db,
        owner.id,
        maintenance_session_id=authority.session_id,
    )


def _erase(db: Session, owner: User) -> dict[str, int]:
    authority = issue_auth_session(db, owner)
    begin_vault_maintenance(
        db,
        owner.id,
        authority.session_id,
        VAULT_STATE_ERASURE_PENDING,
        token_purpose=ACCESS_PURPOSE_SESSION,
    )
    return delete_complete_vault(
        db,
        owner.id,
        erase_auth_sessions=True,
        erasure_session_id=authority.session_id,
    )


def test_v8_roundtrip_preserves_exact_campaign_graph_and_managed_bytes(campaign_v8_db):
    db, owner, _foreign = campaign_v8_db
    imported = _seed_campaign(db, owner)
    before = export_archive(db, owner.id)
    manifest = _manifest(before)
    payload = _payload(before)

    assert CURRENT_ARCHIVE_VERSION == 8
    assert SUPPORTED_ARCHIVE_VERSIONS == frozenset(range(1, 9))
    assert manifest["format_version"] == 8
    assert set(payload["tables"]) == expected_tables(8)
    assert manifest["record_counts"]["campaigns"] == 1
    assert manifest["record_counts"]["campaign_applications"] == imported.application_count
    assert manifest["record_counts"]["campaign_artifacts"] == imported.artifact_count
    assert payload["tables"]["campaigns"][0]["source_fingerprint"] == imported.fingerprint
    assert all("user_id" not in row for row in payload["tables"]["campaigns"])
    assert any(row["tracker_record"] for row in payload["tables"]["campaign_applications"])
    assert all(isinstance(row["provenance"], dict) for row in payload["tables"]["campaign_applications"])

    campaign_asset_ids = {
        row["asset_id"] for row in payload["tables"]["campaign_artifacts"]
    }
    asset_rows = {
        row["id"]: row for row in payload["tables"]["career_assets"]
    }
    assert campaign_asset_ids <= set(asset_rows)
    assert all(asset_rows[item]["kind"] == "campaign_document" for item in campaign_asset_ids)
    assert all(
        asset_rows[item]["storage_path"]
        == f"assets/campaign/{asset_rows[item]['sha256'][:2]}/{asset_rows[item]['sha256']}"
        for item in campaign_asset_ids
    )

    counts = _reset(db, owner)
    assert counts["campaigns"] == 1
    assert db.query(Campaign).filter(Campaign.user_id == owner.id).count() == 0
    restored = restore_archive(db, owner.id, before)
    assert restored.format_version == 8
    assert restored.restored_records["campaigns"] == 1
    assert restored.restored_records["campaign_applications"] == imported.application_count
    assert restored.restored_records["campaign_artifacts"] == imported.artifact_count
    assert inspect_archive(db, owner.id, export_archive(db, owner.id)).compatible

    after = export_archive(db, owner.id)
    assert _payload(after) == payload
    for asset in db.query(CareerAsset).filter(CareerAsset.kind == "campaign_document"):
        assert resolve_data_path(asset.storage_path).read_bytes()
        assert sha256(resolve_data_path(asset.storage_path).read_bytes()) == asset.sha256


def test_v8_roundtrip_accepts_tracker_rows_with_missing_source_status(campaign_v8_db):
    db, owner, _foreign = campaign_v8_db
    tracker = build_fictional_xlsx_bytes(
        applications_rows=[
            {
                "Application ID": "APP-001",
                "Role Title": "Synthetic statusless role",
                "Company Name": "Synthetic statusless company",
                "Status": None,
            }
        ]
    )
    source = build_fictional_campaign_zip(xlsx_bytes=tracker)
    parsed = parse_campaign_workspace(source)
    imported = import_campaign(
        db,
        user_id=owner.id,
        archive_bytes=source,
        expected_fingerprint=parsed.fingerprint,
        imported_at=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
        campaign_name="Synthetic statusless campaign",
        profile_display_name="Synthetic Candidate",
    )
    assert imported.created

    portable = export_archive(db, owner.id)
    assert inspect_archive(db, owner.id, portable).compatible
    assert _payload(portable)["tables"]["campaigns"][0]["summary"]["status_counts"] == {
        "Saved": 1
    }

    _reset(db, owner)
    restored = restore_archive(db, owner.id, portable)
    assert restored.restored_records["campaigns"] == 1


def test_v8_roundtrip_bounds_long_platform_projection_without_losing_source(campaign_v8_db):
    db, owner, _foreign = campaign_v8_db
    source_platform = "Synthetic source platform " + ("x" * 43)
    tracker = build_fictional_xlsx_bytes(
        applications_rows=[
            {
                "Application ID": "APP-001",
                "Role Title": "Synthetic long-platform role",
                "Company Name": "Synthetic long-platform company",
                "Platform / Source": source_platform,
                "Status": "Applied",
            }
        ]
    )
    source = build_fictional_campaign_zip(xlsx_bytes=tracker)
    parsed = parse_campaign_workspace(source)
    imported = import_campaign(
        db,
        user_id=owner.id,
        archive_bytes=source,
        expected_fingerprint=parsed.fingerprint,
        imported_at=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
        campaign_name="Synthetic long-platform campaign",
        profile_display_name="Synthetic Candidate",
    )
    link = (
        db.query(CampaignApplication)
        .filter(
            CampaignApplication.campaign_id == imported.campaign_id,
            CampaignApplication.source_application_id == "APP-001",
        )
        .one()
    )
    application = db.get(Application, link.application_id)

    assert link.platform == source_platform
    assert application is not None
    assert application.job_snapshot["platform"] == source_platform[:40]

    portable = export_archive(db, owner.id)
    payload = _payload(portable)
    portable_link = next(
        row
        for row in payload["tables"]["campaign_applications"]
        if row["source_application_id"] == "APP-001"
    )
    portable_application = next(
        row
        for row in payload["tables"]["applications"]
        if row["id"] == portable_link["application_id"]
    )
    assert portable_link["platform"] == source_platform
    assert portable_application["job_snapshot"]["platform"] == source_platform[:40]

    _reset(db, owner)
    restored = restore_archive(db, owner.id, portable)
    assert restored.restored_records["campaigns"] == 1
    restored_link = (
        db.query(CampaignApplication)
        .filter(CampaignApplication.source_application_id == "APP-001")
        .one()
    )
    restored_application = db.get(Application, restored_link.application_id)
    assert restored_link.platform == source_platform
    assert restored_application is not None
    assert restored_application.job_snapshot["platform"] == source_platform[:40]


def test_v8_roundtrip_preserves_excel_max_tracker_cell_without_truncation(campaign_v8_db):
    db, owner, _foreign = campaign_v8_db
    long_notes = "x" * 32_767
    tracker = build_fictional_xlsx_bytes(
        applications_rows=[
            {
                "Application ID": "APP-001",
                "Role Title": "Synthetic long-note role",
                "Company Name": "Synthetic long-note company",
                "Status": "Applied",
                "Notes": long_notes,
            }
        ]
    )
    source = build_fictional_campaign_zip(xlsx_bytes=tracker)
    parsed = parse_campaign_workspace(source)
    imported = import_campaign(
        db,
        user_id=owner.id,
        archive_bytes=source,
        expected_fingerprint=parsed.fingerprint,
        imported_at=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
        campaign_name="Synthetic long-note campaign",
        profile_display_name="Synthetic Candidate",
    )
    link = (
        db.query(CampaignApplication)
        .filter(
            CampaignApplication.campaign_id == imported.campaign_id,
            CampaignApplication.source_application_id == "APP-001",
        )
        .one()
    )
    assert link.tracker_record["Notes"] == long_notes

    portable = export_archive(db, owner.id)
    portable_link = next(
        row
        for row in _payload(portable)["tables"]["campaign_applications"]
        if row["source_application_id"] == "APP-001"
    )
    assert portable_link["tracker_record"]["Notes"] == long_notes

    _reset(db, owner)
    restored = restore_archive(db, owner.id, portable)
    assert restored.restored_records["campaigns"] == 1
    restored_link = (
        db.query(CampaignApplication)
        .filter(CampaignApplication.source_application_id == "APP-001")
        .one()
    )
    assert restored_link.tracker_record["Notes"] == long_notes


@pytest.mark.parametrize("operation", ["reset", "erasure"])
def test_campaign_lifecycle_removes_rows_and_exclusive_files(campaign_v8_db, operation):
    db, owner, _foreign = campaign_v8_db
    _seed_campaign(db, owner)
    campaign_paths = {
        path
        for (path,) in db.query(CareerAsset.storage_path)
        .filter(CareerAsset.kind == "campaign_document")
        .all()
    }
    assert campaign_paths and all(resolve_data_path(path).exists() for path in campaign_paths)

    counts = _reset(db, owner) if operation == "reset" else _erase(db, owner)

    assert counts["campaigns"] == 1
    assert counts["campaign_applications"] == 5
    assert counts["campaign_artifacts"] > 0
    assert db.query(Campaign).filter(Campaign.user_id == owner.id).count() == 0
    assert db.query(CampaignApplication).count() == 0
    assert db.query(CampaignArtifact).count() == 0
    assert all(not resolve_data_path(path).exists() for path in campaign_paths)


def test_campaign_reset_preserves_content_addressed_bytes_owned_by_another_profile(
    campaign_v8_db,
):
    db, owner, foreign = campaign_v8_db
    _seed_campaign(db, owner)
    shared = (
        db.query(CareerAsset)
        .filter(CareerAsset.kind == "campaign_document")
        .order_by(CareerAsset.id)
        .first()
    )
    assert shared is not None
    foreign_profile = CandidateProfile(
        user_id=foreign.id,
        display_name="Foreign Synthetic Candidate",
        revision=1,
    )
    db.add(foreign_profile)
    db.flush()
    foreign_asset = CareerAsset(
        profile_id=foreign_profile.id,
        kind="campaign_document",
        original_name="shared.txt",
        media_type=shared.media_type,
        sha256=shared.sha256,
        byte_size=shared.byte_size,
        storage_path=shared.storage_path,
        normalized=False,
    )
    db.add(foreign_asset)
    db.commit()
    shared_path = resolve_data_path(shared.storage_path)
    expected_bytes = shared_path.read_bytes()

    _reset(db, owner)

    assert db.get(CareerAsset, foreign_asset.id) is not None
    assert shared_path.read_bytes() == expected_bytes
    assert db.query(Campaign).filter(Campaign.user_id == owner.id).count() == 0


def test_restore_requires_empty_campaign_scope(campaign_v8_db):
    db, owner, _foreign = campaign_v8_db
    _seed_campaign(db, owner)
    archive = export_archive(db, owner.id)
    _reset(db, owner)
    db.add(
        Campaign(
            user_id=owner.id,
            name="Conflicting campaign",
            source_fingerprint="f" * 64,
            name_integrity=sha256(b"Conflicting campaign"),
            summary={},
        )
    )
    db.commit()

    with pytest.raises(ArchiveConflictError, match="empty campaign"):
        restore_archive(db, owner.id, archive)
    assert db.query(CandidateProfile).filter(CandidateProfile.user_id == owner.id).count() == 0
    assert db.query(Campaign).filter(Campaign.user_id == owner.id).count() == 1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["tables"]["campaign_applications"][0].update(
            campaign_id=str(uuid.uuid4())
        ),
        lambda payload: payload["tables"]["campaign_artifacts"][0].update(
            asset_id=str(uuid.uuid4())
        ),
        lambda payload: payload["tables"]["campaigns"][0]["summary"].update(
            application_count=999_999
        ),
        lambda payload: payload["tables"]["career_assets"][0].update(
            storage_path="../outside-vault"
        ),
        lambda payload: payload["tables"]["campaign_artifacts"][0].update(
            relative_path="../unsafe.txt"
        ),
    ],
    ids=["campaign-fk", "asset-fk", "aggregate", "storage-path", "artifact-path"],
)
def test_v8_tampering_is_rejected_before_restore_writes(campaign_v8_db, mutate):
    db, owner, _foreign = campaign_v8_db
    _seed_campaign(db, owner)
    valid = export_archive(db, owner.id)
    tampered = _rewrite(valid, mutate)
    _reset(db, owner)

    with pytest.raises(ArchiveError):
        restore_archive(db, owner.id, tampered)
    assert db.query(CandidateProfile).filter(CandidateProfile.user_id == owner.id).count() == 0
    assert db.query(Campaign).filter(Campaign.user_id == owner.id).count() == 0
    assert db.query(CareerAsset).count() == 0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["tables"]["campaign_applications"][0].update(
            provenance=[]
        ),
        lambda payload: payload["tables"]["campaign_applications"][0].update(
            provenance=["tracker"]
        ),
        lambda payload: payload["tables"]["campaign_applications"][0][
            "provenance"
        ].update(sources=["tracker", "dossier", "tracker"]),
        _noncanonical_provenance_order,
        lambda payload: payload["tables"]["campaign_applications"][0][
            "provenance"
        ].update(private_note="must-not-cross-the-portability-boundary"),
        lambda payload: payload["tables"]["campaign_applications"][0][
            "provenance"
        ].update(warnings={"private": "value"}),
        _invalid_packet_dir_shape,
        _missing_dossier_packet_dir,
        _tracker_only_packet_dir,
        lambda payload: payload["tables"]["campaign_applications"][0].update(
            tracker_record={"nested": {"private": "value"}}
        ),
        lambda payload: payload["tables"]["campaign_applications"][0][
            "tracker_record"
        ].update(Notes="x" * 32_768),
        lambda payload: payload["tables"]["campaigns"][0]["summary"].pop(
            "warning_count"
        ),
        lambda payload: payload["tables"]["campaigns"][0]["summary"].update(
            private_note="must-not-cross-the-portability-boundary"
        ),
        lambda payload: payload["tables"]["campaigns"][0]["summary"].update(
            omitted_credential_count=-1
        ),
        lambda payload: payload["tables"]["campaigns"][0]["summary"].update(
            source_document_count=-1
        ),
        lambda payload: payload["tables"]["campaigns"][0]["summary"].update(
            task_count=999_999
        ),
        _in_range_task_count_mismatch,
        _boolean_status_count,
        _duplicate_application_order,
        _application_order_gap,
        _duplicate_artifact_order,
        _artifact_order_gap,
        lambda payload: payload["tables"]["campaign_artifacts"][0].update(
            display_name="different-safe-name.txt"
        ),
        _control_character_artifact_path,
        _drive_like_artifact_path,
        _casefold_artifact_path_collision,
        _unicode_artifact_path_collision,
    ],
    ids=[
        "provenance-shape",
        "provenance-non-object",
        "provenance-source-duplication",
        "provenance-source-order",
        "provenance-private-key",
        "provenance-warning-shape",
        "provenance-packet-dir-shape",
        "provenance-packet-dir-missing",
        "provenance-packet-dir-without-dossier",
        "tracker-record-nesting",
        "tracker-record-exceeds-xlsx-cell-limit",
        "summary-missing-key",
        "summary-private-key",
        "summary-negative-count",
        "summary-negative-source-documents",
        "summary-task-count",
        "summary-in-range-task-count",
        "summary-boolean-status-count",
        "application-order-collision",
        "application-order-gap",
        "artifact-order-collision",
        "artifact-order-gap",
        "artifact-display-name",
        "artifact-control-character-path",
        "artifact-drive-like-path",
        "artifact-casefold-path-collision",
        "artifact-unicode-path-collision",
    ],
)
def test_v8_campaign_json_and_ordering_tampering_is_rejected_before_writes(
    campaign_v8_db,
    mutate,
):
    db, owner, _foreign = campaign_v8_db
    _seed_campaign(db, owner)
    tampered = _rewrite(export_archive(db, owner.id), mutate)
    _reset(db, owner)

    with pytest.raises(ArchiveError):
        restore_archive(db, owner.id, tampered)
    assert db.query(CandidateProfile).filter(CandidateProfile.user_id == owner.id).count() == 0
    assert db.query(Campaign).filter(Campaign.user_id == owner.id).count() == 0
    assert db.query(CareerAsset).count() == 0
