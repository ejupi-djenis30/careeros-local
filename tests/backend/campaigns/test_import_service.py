"""Comprehensive tests for Campaign Import Service (Feature 003 Phase 2 / C023-C025)."""

from __future__ import annotations

import hashlib
import uuid
import zipfile
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from backend.applications.models import Application, ApplicationEvent
from backend.campaigns.import_planner import plan_campaign_import
from backend.campaigns.models import (
    Campaign,
    CampaignApplication,
    CampaignArtifact,
)
from backend.campaigns.parser import parse_campaign_workspace
from backend.campaigns.service import import_campaign
from backend.campaigns.service_helpers import CampaignImportError, prepare_root_source_documents
from backend.campaigns.xlsx_reader import read_campaign_workbook
from backend.career.models import (
    CandidateProfile,
    CareerAsset,
    CareerFact,
    CareerGoal,
    SourceDocument,
)
from backend.db.base import Base, configure_sqlite_connection, ensure_sqlite_parent
from backend.models import Job, User
from backend.storage.atomic import read_verified, resolve_data_path
from tests.backend.campaigns.fixture_builder import build_fictional_campaign_zip


@pytest.fixture
def service_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "vault-data"
    monkeypatch.setattr("backend.storage.atomic.settings.DATA_DIR", str(data_dir))
    monkeypatch.setattr("backend.core.config.settings.DATA_DIR", str(data_dir))
    db_path = (tmp_path / "test_campaign.db").as_posix()
    db_url = f"sqlite:///{db_path}"
    ensure_sqlite_parent(db_url)
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", configure_sqlite_connection)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        user1 = User(username="user1", hashed_password="pw1")
        user2 = User(username="user2", hashed_password="pw2")
        session.add_all([user1, user2])
        session.commit()
        user1_id = user1.id
        user2_id = user2.id

    try:
        yield factory, data_dir, user1_id, user2_id
    finally:
        engine.dispose()


def _expected_uuid(
    user_id: int,
    fingerprint: str,
    entity_tag: str,
    item_id: str = "",
) -> str:
    urn = f"urn:careeros:campaign:user:{user_id}:{fingerprint}:{entity_tag}"
    if item_id:
        urn = f"{urn}:{item_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, urn))


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return value


def _journal_files(data_dir: Path) -> list[Path]:
    journal_dir = data_dir / "assets" / ".publication-journal"
    return sorted(journal_dir.glob("*.json")) if journal_dir.exists() else []


def test_import_campaign_success_full_flow(service_vault) -> None:
    factory, data_dir, user1_id, _ = service_vault
    zip_bytes = build_fictional_campaign_zip()
    preview = parse_campaign_workspace(zip_bytes)
    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    with factory() as db:
        resp = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=zip_bytes,
            expected_fingerprint=preview.fingerprint,
            imported_at=now,
            campaign_name="Spring 2026 Search",
            profile_display_name="Jane Doe",
        )

    assert resp.created is True
    assert resp.fingerprint == preview.fingerprint
    assert resp.application_count == 5
    assert resp.artifact_count == len(preview.artifacts)
    assert resp.source_document_count == 4
    assert resp.task_count == 1
    assert resp.warning_count == 0

    with factory() as db:
        # Campaign row verification
        camp = db.query(Campaign).filter(Campaign.id == resp.campaign_id).first()
        assert camp is not None
        assert camp.user_id == user1_id
        assert camp.name == "Spring 2026 Search"
        assert camp.source_fingerprint == preview.fingerprint
        assert camp.tracker_sha256 == preview.tracker_sha256

        # Aggregate-only summary verification
        summary = camp.summary
        assert summary["application_count"] == 5
        assert summary["artifact_count"] == len(preview.artifacts)
        assert summary["source_document_count"] == 4
        assert summary["task_count"] == 1
        assert summary["omitted_credential_count"] == preview.credentials_count
        assert summary["warning_count"] == 0
        assert summary["status_counts"] == dict(preview.status_counts)

        # Assert no filenames, records, warning text, or document bodies in summary
        summary_str = str(summary).lower()
        assert ".xlsx" not in summary_str
        assert ".pdf" not in summary_str
        assert ".md" not in summary_str
        assert "password" not in summary_str
        assert "credential" not in summary_str or "omitted_credential_count" in summary

        # Applications verification: manual applications with job_id=None
        apps = db.query(Application).filter(Application.user_id == user1_id).all()
        assert len(apps) == 5
        for app in apps:
            assert app.job_id is None
            assert app.scraped_job_id is None
            assert app.resume_version_id is None
            assert app.revision >= 1

        # No Job rows created
        assert db.query(Job).count() == 0

        # ApplicationEvent verification
        events = (
            db.query(ApplicationEvent)
            .join(Application, ApplicationEvent.application_id == Application.id)
            .filter(Application.user_id == user1_id)
            .all()
        )
        assert len(events) > 0
        for ev in events:
            assert ev.occurred_at <= now

        # Only active application with next action has task projection
        app1 = (
            db.query(Application)
            .join(CampaignApplication, CampaignApplication.application_id == Application.id)
            .filter(CampaignApplication.source_application_id == "APP-001")
            .first()
        )
        assert app1 is not None
        assert app1.next_action_task_id is not None
        assert app1.next_action_title == "Follow up with recruiter"
        assert app1.next_action_priority == "high"
        assert app1.next_action_at == datetime(2026, 1, 26, 12, 0, 0, tzinfo=timezone.utc)

        # Closed application has NO task projection
        app3 = (
            db.query(Application)
            .join(CampaignApplication, CampaignApplication.application_id == Application.id)
            .filter(CampaignApplication.source_application_id == "APP-003")
            .first()
        )
        assert app3 is not None
        assert app3.next_action_task_id is None

        # CampaignApplication verification: JSON-safe values
        camp_apps = db.query(CampaignApplication).filter(CampaignApplication.campaign_id == camp.id).all()
        assert len(camp_apps) == 5
        for ca in camp_apps:
            assert isinstance(ca.tracker_record, dict)
            assert isinstance(ca.provenance, dict)
            # Prove dates serialized as ISO strings
            for v in ca.tracker_record.values():
                assert not isinstance(v, (date, datetime))
            for v in ca.provenance.values():
                assert not isinstance(v, (date, datetime, tuple))

        # Root source documents verification
        sdocs = db.query(SourceDocument).all()
        assert len(sdocs) == 4
        roles = {sd.source_role for sd in sdocs}
        assert roles == {"profile", "goals", "narrative", "template_reference"}
        for sd in sdocs:
            assert len(sd.extracted_text) > 0
            assert len(sd.extracted_text_sha256) == 64
            # Source document is linked to CareerAsset(kind="campaign_document")
            assert sd.asset.kind == "campaign_document"

        # Discard candidates: NO CareerFact, NO CareerGoal rows
        assert db.query(CareerFact).count() == 0
        assert db.query(CareerGoal).count() == 0


def test_import_campaign_persists_exact_owner_scoped_plan(service_vault) -> None:
    factory, data_dir, user1_id, _ = service_vault
    archive = build_fictional_campaign_zip(credentials_count=2)
    parsed = parse_campaign_workspace(archive)
    imported_at = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    campaign_name = "Exact fictional campaign"
    planned = plan_campaign_import(
        parsed,
        imported_at,
        identity_scope=f"user:{user1_id}",
        campaign_name=campaign_name,
    )
    prepared_sources = prepare_root_source_documents(parsed)

    with factory() as db:
        response = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=archive,
            expected_fingerprint=parsed.fingerprint,
            imported_at=imported_at,
            campaign_name=campaign_name,
            profile_display_name="Exact Test User",
        )

    expected_summary = {
        "application_count": len(planned.applications),
        "artifact_count": len(planned.artifacts),
        "source_document_count": len(prepared_sources),
        "task_count": sum(item.task is not None for item in planned.applications),
        "tracker_rows": sum(
            "tracker" in item.source.provenance.get("sources", ())
            for item in planned.applications
        ),
        "dossier_count": sum(
            "dossier" in item.source.provenance.get("sources", ())
            for item in planned.applications
        ),
        "matched_count": sum(
            set(item.source.provenance.get("sources", ())) >= {"tracker", "dossier"}
            for item in planned.applications
        ),
        "tracker_only_count": sum(
            set(item.source.provenance.get("sources", ())) == {"tracker"}
            for item in planned.applications
        ),
        "dossier_only_count": sum(
            set(item.source.provenance.get("sources", ())) == {"dossier"}
            for item in planned.applications
        ),
        "status_counts": dict(planned.status_counts),
        "omitted_credential_count": planned.credentials_count,
        "warning_count": len(planned.warnings),
    }

    assert response.campaign_id == _expected_uuid(user1_id, planned.fingerprint, "campaign")
    assert response.application_count == len(planned.applications)
    assert response.artifact_count == len(planned.artifacts)
    assert response.source_document_count == len(prepared_sources)

    with factory() as db:
        campaign = db.query(Campaign).filter(Campaign.id == response.campaign_id).one()
        assert campaign.user_id == user1_id
        assert campaign.name == campaign_name
        assert campaign.source_fingerprint == planned.fingerprint
        assert campaign.tracker_sha256 == planned.tracker_sha256
        assert campaign.summary == expected_summary

        profile = (
            db.query(CandidateProfile)
            .filter(CandidateProfile.user_id == user1_id)
            .one()
        )
        assert profile.display_name == "Exact Test User"
        assert profile.revision == 1
        assert profile.preferences == {}

        links = {
            item.source_application_id: item
            for item in db.query(CampaignApplication)
            .filter(CampaignApplication.campaign_id == campaign.id)
            .all()
        }
        assert set(links) == {
            item.source_application_id for item in planned.applications
        }

        for expected in planned.applications:
            expected_app_id = _expected_uuid(
                user1_id,
                planned.fingerprint,
                "application",
                expected.source_application_id,
            )
            application = db.query(Application).filter(Application.id == expected_app_id).one()
            assert application.user_id == user1_id
            assert application.job_id is None
            assert application.scraped_job_id is None
            assert application.resume_version_id is None
            assert application.revision == expected.revision
            assert application.current_stage == expected.current_stage
            assert application.job_snapshot == _json_safe(expected.job_snapshot)
            assert application.job_title == expected.job_title
            assert application.job_company == expected.job_company
            assert application.job_location == expected.job_location
            assert application.latest_event_at == expected.latest_event_at
            assert application.next_action_task_id == expected.next_action_task_id
            assert application.next_action_title == expected.next_action_title
            assert application.next_action_at == expected.next_action_at
            assert application.next_action_priority == expected.next_action_priority

            link = links[expected.source_application_id]
            assert link.id == _expected_uuid(
                user1_id,
                planned.fingerprint,
                "campaign_app",
                expected.source_application_id,
            )
            assert link.application_id == expected_app_id
            assert link.source_order == expected.source_order
            assert link.source_status == expected.source.source_status
            assert link.priority == expected.source.priority
            assert link.platform == expected.source.platform
            assert link.category == expected.source.category
            assert link.outcome == expected.source.outcome
            assert link.found_at == expected.source.found_at
            assert link.applied_at == expected.source.applied_at
            assert link.follow_up_at == expected.source.follow_up_at
            assert link.last_update_at == expected.source.last_update_at
            assert link.tracker_record == _json_safe(expected.source.tracker_record)
            assert link.provenance == _json_safe(expected.source.provenance)

            stored_events = {
                item.id: item
                for item in db.query(ApplicationEvent)
                .filter(ApplicationEvent.application_id == expected_app_id)
                .all()
            }
            assert set(stored_events) == {item.id for item in expected.events}
            for expected_event in expected.events:
                stored_event = stored_events[expected_event.id]
                assert stored_event.event_type == expected_event.event_type
                assert stored_event.stage == expected_event.stage
                assert stored_event.occurred_at == expected_event.occurred_at
                assert stored_event.note == expected_event.note
                assert stored_event.payload == _json_safe(expected_event.payload)
                assert stored_event.created_at == expected_event.created_at

        artifacts = {
            item.relative_path: item
            for item in db.query(CampaignArtifact)
            .filter(CampaignArtifact.campaign_id == campaign.id)
            .all()
        }
        assert set(artifacts) == {item.relative_path for item in planned.artifacts}
        for expected in planned.artifacts:
            stored = artifacts[expected.relative_path]
            assert stored.id == _expected_uuid(
                user1_id,
                planned.fingerprint,
                "artifact",
                expected.relative_path,
            )
            expected_application_id = (
                _expected_uuid(
                    user1_id,
                    planned.fingerprint,
                    "application",
                    expected.source_application_id,
                )
                if expected.source_application_id
                else None
            )
            assert stored.application_id == expected_application_id
            assert stored.display_name == expected.display_name
            assert stored.category == expected.category
            assert stored.source_order == expected.source_order
            assert stored.created_at == planned.imported_at
            assert stored.asset.profile_id == profile.id
            assert stored.asset.kind == "campaign_document"
            assert stored.asset.sha256 == expected.sha256
            assert stored.asset.byte_size == expected.byte_size
            assert stored.asset.storage_path == (
                f"assets/campaign/{expected.sha256[:2]}/{expected.sha256}"
            )
            assert read_verified(
                stored.asset.storage_path,
                stored.asset.sha256,
                expected_size=stored.asset.byte_size,
                maximum_size=50 * 1024 * 1024,
            ) == expected.raw_bytes

        source_documents = {item.id: item for item in db.query(SourceDocument).all()}
        assert set(source_documents) == {
            _expected_uuid(
                user1_id,
                planned.fingerprint,
                "source_document",
                item.original_name,
            )
            for item in prepared_sources
        }
        for expected in prepared_sources:
            stored = source_documents[
                _expected_uuid(
                    user1_id,
                    planned.fingerprint,
                    "source_document",
                    expected.original_name,
                )
            ]
            assert stored.profile_id == profile.id
            assert stored.document_type == expected.document_type
            assert stored.source_role == expected.source_role
            assert stored.extracted_text == expected.extracted_text
            assert stored.extracted_text_sha256 == hashlib.sha256(
                expected.extracted_text.encode("utf-8")
            ).hexdigest()
            assert stored.asset.sha256 == expected.sha256

        assert db.query(CareerFact).count() == 0
        assert db.query(CareerGoal).count() == 0
        assert _journal_files(data_dir) == []


def test_import_campaign_sanitized_tracker_bytes_verified(service_vault) -> None:
    factory, data_dir, user1_id, _ = service_vault
    zip_bytes = build_fictional_campaign_zip(credentials_count=2)
    preview = parse_campaign_workspace(zip_bytes)
    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    with zipfile.ZipFile(BytesIO(zip_bytes)) as source_archive:
        original_tracker_bytes = source_archive.read("ApplicationTracker.xlsx")

    with factory() as db:
        resp = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=zip_bytes,
            expected_fingerprint=preview.fingerprint,
            imported_at=now,
            profile_display_name="Jane Doe",
        )
        assert db.in_transaction() is False

    with factory() as db:
        camp = db.query(Campaign).filter(Campaign.id == resp.campaign_id).first()
        assert camp is not None

        # CampaignArtifact for ApplicationTracker.xlsx
        tracker_art = (
            db.query(CampaignArtifact)
            .filter(
                CampaignArtifact.campaign_id == camp.id,
                CampaignArtifact.relative_path == "ApplicationTracker.xlsx",
            )
            .first()
        )
        assert tracker_art is not None
        assert tracker_art.category == "tracker"

        # Read stored tracker bytes from disk
        tracker_asset = tracker_art.asset
        assert tracker_asset is not None
        assert tracker_asset.kind == "campaign_document"

        stored_bytes = read_verified(
            tracker_asset.storage_path,
            tracker_asset.sha256,
            expected_size=tracker_asset.byte_size,
            maximum_size=50 * 1024 * 1024,
        )

        # Original tracker digest differs from sanitized tracker digest
        assert camp.tracker_sha256 == hashlib.sha256(original_tracker_bytes).hexdigest()
        assert camp.tracker_sha256 != tracker_asset.sha256
        assert tracker_asset.sha256 == preview.sanitized_tracker_sha256
        assert stored_bytes == preview.sanitized_tracker_bytes
        assert stored_bytes != original_tracker_bytes
        assert (
            db.query(CareerAsset)
            .filter(CareerAsset.sha256 == camp.tracker_sha256)
            .count()
            == 0
        )

        # Sanitized tracker has NO credentials sheet or sentinels
        assert b"Credentials" not in stored_bytes
        assert b"TopSecretToken" not in stored_bytes
        assert b"sharedStrings" not in stored_bytes

        # Sanitized tracker is parseable with credentials_count == 0
        read_res = read_campaign_workbook(stored_bytes)
        assert read_res.credentials_count == 0
        assert len(read_res.rows) == 4
        assert preview.credentials_count == 2


def test_import_campaign_idempotence(service_vault) -> None:
    factory, data_dir, user1_id, _ = service_vault
    zip_bytes = build_fictional_campaign_zip()
    preview = parse_campaign_workspace(zip_bytes)
    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    with factory() as db:
        resp1 = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=zip_bytes,
            expected_fingerprint=preview.fingerprint,
            imported_at=now,
            profile_display_name="Jane Doe",
        )
    assert resp1.created is True

    with factory() as db:
        c_count1 = db.query(Campaign).count()
        app_count1 = db.query(Application).count()
        ev_count1 = db.query(ApplicationEvent).count()
        art_count1 = db.query(CampaignArtifact).count()
        sdoc_count1 = db.query(SourceDocument).count()
        asset_count1 = db.query(CareerAsset).count()

    files_before = {p: p.stat().st_mtime_ns for p in data_dir.rglob("*") if p.is_file()}

    # Second import with identical user and fingerprint
    with factory() as db:
        resp2 = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=zip_bytes,
            expected_fingerprint=preview.fingerprint,
            imported_at=now,
            profile_display_name="Jane Doe",
        )
    assert resp2.created is False
    assert resp2.campaign_id == resp1.campaign_id
    assert resp2.fingerprint == resp1.fingerprint
    assert resp2.application_count == resp1.application_count
    assert resp2.artifact_count == resp1.artifact_count

    # Zero database row mutations
    with factory() as db:
        assert db.query(Campaign).count() == c_count1
        assert db.query(Application).count() == app_count1
        assert db.query(ApplicationEvent).count() == ev_count1
        assert db.query(CampaignArtifact).count() == art_count1
        assert db.query(SourceDocument).count() == sdoc_count1
        assert db.query(CareerAsset).count() == asset_count1

    # Zero filesystem mutations
    files_after = {p: p.stat().st_mtime_ns for p in data_dir.rglob("*") if p.is_file()}
    assert files_after == files_before


def test_second_campaign_reuses_root_documents_and_remains_idempotent(service_vault) -> None:
    factory, _data_dir, user1_id, _ = service_vault
    first_archive = build_fictional_campaign_zip(credentials_count=0)
    second_archive = build_fictional_campaign_zip(credentials_count=1)
    first_preview = parse_campaign_workspace(first_archive)
    second_preview = parse_campaign_workspace(second_archive)
    assert first_preview.fingerprint != second_preview.fingerprint

    imported_at = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    with factory() as db:
        first = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=first_archive,
            expected_fingerprint=first_preview.fingerprint,
            imported_at=imported_at,
            profile_display_name="Root Document Reuse",
        )
    with factory() as db:
        second = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=second_archive,
            expected_fingerprint=second_preview.fingerprint,
            imported_at=imported_at + timedelta(days=1),
        )
    with factory() as db:
        retry = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=second_archive,
            expected_fingerprint=second_preview.fingerprint,
            imported_at=imported_at + timedelta(days=2),
        )
        assert db.query(SourceDocument).count() == 4

    assert first.created is True
    assert second.created is True
    assert second.campaign_id != first.campaign_id
    assert retry.created is False
    assert retry.campaign_id == second.campaign_id


def test_packet_root_files_remain_campaign_level_and_idempotent(service_vault) -> None:
    factory, _data_dir, user1_id, _ = service_vault
    packet_root_paths = {
        "application-packets/README.md",
        "application-packets/catalog.json",
    }
    archive = build_fictional_campaign_zip(
        members={path: b"fictional campaign-level evidence" for path in packet_root_paths}
    )
    parsed = parse_campaign_workspace(archive)
    packet_root_artifacts = [
        artifact for artifact in parsed.artifacts
        if artifact.relative_path in packet_root_paths
    ]

    assert len(packet_root_artifacts) == 2
    assert all(artifact.source_application_id is None for artifact in packet_root_artifacts)
    assert parsed.dossier_count == 3
    assert parsed.logical_application_count == 5

    imported_at = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    with factory() as db:
        first = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=archive,
            expected_fingerprint=parsed.fingerprint,
            imported_at=imported_at,
            profile_display_name="Packet Root Test",
        )
    with factory() as db:
        rows = (
            db.query(CampaignArtifact)
            .filter(CampaignArtifact.relative_path.in_(packet_root_paths))
            .all()
        )
        assert len(rows) == 2
        assert all(row.application_id is None for row in rows)
        second = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=archive,
            expected_fingerprint=parsed.fingerprint,
            imported_at=imported_at + timedelta(days=1),
            profile_display_name="Ignored",
        )

    assert first.created is True
    assert second.created is False
    assert second.campaign_id == first.campaign_id


def test_import_campaign_uses_one_commit_then_zero_for_idempotence(
    service_vault,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, data_dir, user1_id, _ = service_vault
    archive = build_fictional_campaign_zip()
    parsed = parse_campaign_workspace(archive)
    imported_at = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    real_commit = Session.commit
    commit_count = 0

    def counted_commit(session: Session) -> None:
        nonlocal commit_count
        commit_count += 1
        real_commit(session)

    monkeypatch.setattr(Session, "commit", counted_commit)
    with factory() as db:
        first = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=archive,
            expected_fingerprint=parsed.fingerprint,
            imported_at=imported_at,
            profile_display_name="Commit Counter",
        )
    assert first.created is True
    assert commit_count == 1
    assert _journal_files(data_dir) == []

    commit_count = 0
    files_before = {
        path: path.stat().st_mtime_ns
        for path in data_dir.rglob("*")
        if path.is_file()
    }
    with factory() as db:
        second = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=archive,
            expected_fingerprint=parsed.fingerprint,
            imported_at=imported_at + timedelta(days=400),
            profile_display_name="Ignored",
        )
    assert second.created is False
    assert second.campaign_id == first.campaign_id
    assert commit_count == 0
    assert {
        path: path.stat().st_mtime_ns
        for path in data_dir.rglob("*")
        if path.is_file()
    } == files_before
    assert _journal_files(data_dir) == []


@pytest.mark.parametrize(
    "corruption",
    [
        "campaign_metadata",
        "campaign_summary",
        "application_projection",
        "application_ownership",
        "campaign_link",
        "event_identity",
        "event_data",
        "artifact_binding",
        "asset_metadata",
        "asset_bytes",
        "source_document",
    ],
)
def test_import_campaign_corrupt_existing_graph_fails_closed_without_writes(
    service_vault,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    factory, data_dir, user1_id, user2_id = service_vault
    archive = build_fictional_campaign_zip()
    parsed = parse_campaign_workspace(archive)
    imported_at = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    with factory() as db:
        import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=archive,
            expected_fingerprint=parsed.fingerprint,
            imported_at=imported_at,
            profile_display_name="Corruption Test",
        )

    with factory() as db:
        if corruption == "campaign_metadata":
            db.query(Campaign).one().name = "Corrupted campaign"
        elif corruption == "campaign_summary":
            campaign = db.query(Campaign).one()
            campaign.summary = {**campaign.summary, "task_count": 999}
        elif corruption == "application_projection":
            application = db.query(Application).filter(Application.user_id == user1_id).first()
            assert application is not None
            application.current_stage = "screening"
            application.revision += 7
        elif corruption == "application_ownership":
            application = db.query(Application).filter(Application.user_id == user1_id).first()
            assert application is not None
            application.user_id = user2_id
        elif corruption == "campaign_link":
            link = db.query(CampaignApplication).first()
            assert link is not None
            link.source_order += 1000
            link.provenance = {"sources": []}
            link.tracker_record = {"corrupted": True}
        elif corruption == "event_identity":
            stored_event = db.query(ApplicationEvent).first()
            assert stored_event is not None
            replacement = ApplicationEvent(
                id=str(uuid.uuid4()),
                application_id=stored_event.application_id,
                event_type=stored_event.event_type,
                stage=stored_event.stage,
                occurred_at=stored_event.occurred_at,
                note=stored_event.note,
                payload=stored_event.payload,
                created_at=stored_event.created_at,
            )
            db.delete(stored_event)
            db.flush()
            db.add(replacement)
        elif corruption == "event_data":
            stored_event = db.query(ApplicationEvent).first()
            assert stored_event is not None
            replacement = ApplicationEvent(
                id=stored_event.id,
                application_id=stored_event.application_id,
                event_type="note",
                stage=None,
                occurred_at=stored_event.occurred_at,
                note="corrupted event",
                payload={"corrupted": True},
                created_at=stored_event.created_at,
            )
            db.delete(stored_event)
            db.flush()
            db.add(replacement)
        elif corruption == "artifact_binding":
            artifact = db.query(CampaignArtifact).first()
            assert artifact is not None
            artifact.category = "other"
            other_asset = (
                db.query(CareerAsset)
                .filter(CareerAsset.id != artifact.asset_id)
                .first()
            )
            assert other_asset is not None
            artifact.asset_id = other_asset.id
        elif corruption == "asset_metadata":
            asset = db.query(CareerAsset).first()
            assert asset is not None
            asset.byte_size += 1
        elif corruption == "asset_bytes":
            asset = db.query(CareerAsset).first()
            assert asset is not None
            asset_path = resolve_data_path(asset.storage_path, create_root=False)
            original = asset_path.read_bytes()
            assert original
            asset_path.write_bytes(bytes([original[0] ^ 0x01]) + original[1:])
        elif corruption == "source_document":
            source = db.query(SourceDocument).first()
            assert source is not None
            source.source_role = (
                "narrative" if source.source_role != "narrative" else "profile"
            )
            source.extracted_text = f"{source.extracted_text}\ncorrupted"
            source.extracted_text_sha256 = "0" * 64
        else:  # pragma: no cover - the parametrization is closed above
            raise AssertionError(f"Unhandled corruption case: {corruption}")
        db.commit()

    with factory() as db:
        counts_before = {
            "campaigns": db.query(Campaign).count(),
            "applications": db.query(Application).count(),
            "events": db.query(ApplicationEvent).count(),
            "links": db.query(CampaignApplication).count(),
            "artifacts": db.query(CampaignArtifact).count(),
            "assets": db.query(CareerAsset).count(),
            "sources": db.query(SourceDocument).count(),
        }
    files_before = {
        path: path.stat().st_mtime_ns
        for path in data_dir.rglob("*")
        if path.is_file()
    }
    real_commit = Session.commit
    commit_count = 0

    def counted_commit(session: Session) -> None:
        nonlocal commit_count
        commit_count += 1
        real_commit(session)

    monkeypatch.setattr(Session, "commit", counted_commit)
    with factory() as db:
        with pytest.raises(CampaignImportError) as error:
            import_campaign(
                db,
                user_id=user1_id,
                archive_bytes=archive,
                expected_fingerprint=parsed.fingerprint,
                imported_at=imported_at,
                profile_display_name="Ignored",
            )
    assert error.value.status_code == 409
    assert commit_count == 0

    with factory() as db:
        assert {
            "campaigns": db.query(Campaign).count(),
            "applications": db.query(Application).count(),
            "events": db.query(ApplicationEvent).count(),
            "links": db.query(CampaignApplication).count(),
            "artifacts": db.query(CampaignArtifact).count(),
            "assets": db.query(CareerAsset).count(),
            "sources": db.query(SourceDocument).count(),
        } == counts_before
    assert {
        path: path.stat().st_mtime_ns
        for path in data_dir.rglob("*")
        if path.is_file()
    } == files_before
    assert _journal_files(data_dir) == []


def test_import_campaign_profile_bootstrap_and_preservation(service_vault) -> None:
    factory, data_dir, user1_id, user2_id = service_vault
    zip_bytes = build_fictional_campaign_zip()
    preview = parse_campaign_workspace(zip_bytes)
    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    # User 1 has no profile: missing display name fails
    with factory() as db:
        with pytest.raises(CampaignImportError) as exc_info:
            import_campaign(
                db,
                user_id=user1_id,
                archive_bytes=zip_bytes,
                expected_fingerprint=preview.fingerprint,
                imported_at=now,
                profile_display_name=None,
            )
        assert exc_info.value.status_code == 422
        assert db.query(CandidateProfile).count() == 0

    # Whitespace display name fails
    with factory() as db:
        with pytest.raises(CampaignImportError) as exc_info:
            import_campaign(
                db,
                user_id=user1_id,
                archive_bytes=zip_bytes,
                expected_fingerprint=preview.fingerprint,
                imported_at=now,
                profile_display_name="   \t  ",
            )
        assert exc_info.value.status_code == 422

    # Display name > 160 fails
    with factory() as db:
        with pytest.raises(CampaignImportError) as exc_info:
            import_campaign(
                db,
                user_id=user1_id,
                archive_bytes=zip_bytes,
                expected_fingerprint=preview.fingerprint,
                imported_at=now,
                profile_display_name="X" * 161,
            )
        assert exc_info.value.status_code == 422

    # Valid display name bootstraps minimal profile
    with factory() as db:
        import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=zip_bytes,
            expected_fingerprint=preview.fingerprint,
            imported_at=now,
            profile_display_name="Alice User",
        )
        prof1 = db.query(CandidateProfile).filter(CandidateProfile.user_id == user1_id).first()
        assert prof1 is not None
        assert prof1.display_name == "Alice User"
        assert prof1.revision == 1

    # User 2 already has an existing profile: profile is preserved unchanged
    with factory() as db:
        prof2 = CandidateProfile(
            user_id=user2_id,
            display_name="Bob Existing",
            headline="Principal Architect",
            revision=5,
        )
        db.add(prof2)
        db.commit()

        import_campaign(
            db,
            user_id=user2_id,
            archive_bytes=zip_bytes,
            expected_fingerprint=preview.fingerprint,
            imported_at=now,
            profile_display_name="Should Be Ignored",
        )
        prof2_after = db.query(CandidateProfile).filter(CandidateProfile.user_id == user2_id).first()
        assert prof2_after is not None
        assert prof2_after.display_name == "Bob Existing"
        assert prof2_after.headline == "Principal Architect"
        assert prof2_after.revision == 5


def test_import_campaign_validation_conflicts_leave_zero_writes(service_vault) -> None:
    factory, data_dir, user1_id, _ = service_vault
    zip_bytes = build_fictional_campaign_zip()
    preview = parse_campaign_workspace(zip_bytes)
    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Stale / mismatched fingerprint raises 409 conflict and leaves zero writes
    with factory() as db:
        with pytest.raises(CampaignImportError) as exc_info:
            import_campaign(
                db,
                user_id=user1_id,
                archive_bytes=zip_bytes,
                expected_fingerprint="0" * 64,
                imported_at=now,
                profile_display_name="Alice",
            )
        assert exc_info.value.status_code == 409
        assert db.query(Campaign).count() == 0
        assert db.query(Application).count() == 0
        assert db.query(CareerAsset).count() == 0

    # 2. Blank campaign name raises 422
    with factory() as db:
        with pytest.raises(CampaignImportError) as exc_info:
            import_campaign(
                db,
                user_id=user1_id,
                archive_bytes=zip_bytes,
                expected_fingerprint=preview.fingerprint,
                imported_at=now,
                campaign_name="   ",
                profile_display_name="Alice",
            )
        assert exc_info.value.status_code == 422
        assert db.query(Campaign).count() == 0

    # 3. Campaign name > 160 characters raises 422
    with factory() as db:
        with pytest.raises(CampaignImportError) as exc_info:
            import_campaign(
                db,
                user_id=user1_id,
                archive_bytes=zip_bytes,
                expected_fingerprint=preview.fingerprint,
                imported_at=now,
                campaign_name="C" * 161,
                profile_display_name="Alice",
            )
        assert exc_info.value.status_code == 422
        assert db.query(Campaign).count() == 0

    # 4. Naive imported_at raises 422
    with factory() as db:
        with pytest.raises(CampaignImportError) as exc_info:
            import_campaign(
                db,
                user_id=user1_id,
                archive_bytes=zip_bytes,
                expected_fingerprint=preview.fingerprint,
                imported_at=datetime(2026, 3, 15, 12, 0, 0),
                profile_display_name="Alice",
            )
        assert exc_info.value.status_code == 422

    # 5. Non-UTC imported_at raises 422
    tz_plus_5 = timezone(timedelta(hours=5))
    with factory() as db:
        with pytest.raises(CampaignImportError) as exc_info:
            import_campaign(
                db,
                user_id=user1_id,
                archive_bytes=zip_bytes,
                expected_fingerprint=preview.fingerprint,
                imported_at=datetime(2026, 3, 15, 17, 0, 0, tzinfo=tz_plus_5),
                profile_display_name="Alice",
            )
        assert exc_info.value.status_code == 422

    # 6. Nonexistent user raises 404
    with factory() as db:
        with pytest.raises(CampaignImportError) as exc_info:
            import_campaign(
                db,
                user_id=999999,
                archive_bytes=zip_bytes,
                expected_fingerprint=preview.fingerprint,
                imported_at=now,
                profile_display_name="Alice",
            )
        assert exc_info.value.status_code == 404

    # Assert zero files written to data directory
    assert list(data_dir.rglob("*")) == []


@pytest.mark.parametrize("failure_kind", ["archive_policy", "source_preflight"])
def test_import_campaign_validation_errors_are_bounded_and_do_not_echo_archive_data(
    service_vault,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    factory, data_dir, user1_id, _ = service_vault
    sentinel = "PRIVATE-CAMPAIGN-FILENAME-SENTINEL"
    if failure_kind == "archive_policy":
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"../{sentinel}.txt", b"private archive content")
        archive_bytes = buffer.getvalue()
        fingerprint = "0" * 64
    else:
        archive_bytes = build_fictional_campaign_zip(
            members={f"{sentinel}.pdf": b"private invalid pdf content"}
        )
        fingerprint = parse_campaign_workspace(archive_bytes).fingerprint

    real_commit = Session.commit
    commit_count = 0

    def counted_commit(session: Session) -> None:
        nonlocal commit_count
        commit_count += 1
        real_commit(session)

    monkeypatch.setattr(Session, "commit", counted_commit)
    with factory() as db:
        with pytest.raises(CampaignImportError) as error:
            import_campaign(
                db,
                user_id=user1_id,
                archive_bytes=archive_bytes,
                expected_fingerprint=fingerprint,
                imported_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
                profile_display_name="Safe Error Test",
            )
    message = str(error.value).lower()
    assert sentinel.lower() not in message
    assert "private archive content" not in message
    assert "private invalid pdf content" not in message
    assert "entry contains" not in message
    assert "valid pdf" not in message
    assert commit_count == 0
    assert list(data_dir.rglob("*")) == []


def test_import_campaign_cross_user_isolation(service_vault) -> None:
    factory, data_dir, user1_id, user2_id = service_vault
    zip_bytes = build_fictional_campaign_zip()
    preview = parse_campaign_workspace(zip_bytes)
    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    # User 1 imports archive
    with factory() as db:
        resp1 = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=zip_bytes,
            expected_fingerprint=preview.fingerprint,
            imported_at=now,
            profile_display_name="User One",
        )
    assert resp1.created is True

    # User 2 imports the identical archive
    with factory() as db:
        resp2 = import_campaign(
            db,
            user_id=user2_id,
            archive_bytes=zip_bytes,
            expected_fingerprint=preview.fingerprint,
            imported_at=now,
            profile_display_name="User Two",
        )
    assert resp2.created is True

    # Deterministic owner-scoped IDs are distinct between users
    assert resp1.campaign_id != resp2.campaign_id

    with factory() as db:
        u1_apps = db.query(Application).filter(Application.user_id == user1_id).all()
        u2_apps = db.query(Application).filter(Application.user_id == user2_id).all()
        assert len(u1_apps) == 5
        assert len(u2_apps) == 5

        u1_app_ids = {a.id for a in u1_apps}
        u2_app_ids = {a.id for a in u2_apps}
        assert u1_app_ids.isdisjoint(u2_app_ids)

        u1_events = (
            db.query(ApplicationEvent)
            .join(Application, ApplicationEvent.application_id == Application.id)
            .filter(Application.user_id == user1_id)
            .all()
        )
        u2_events = (
            db.query(ApplicationEvent)
            .join(Application, ApplicationEvent.application_id == Application.id)
            .filter(Application.user_id == user2_id)
            .all()
        )
        u1_ev_ids = {e.id for e in u1_events}
        u2_ev_ids = {e.id for e in u2_events}
        assert u1_ev_ids.isdisjoint(u2_ev_ids)

        u1_profile = (
            db.query(CandidateProfile)
            .filter(CandidateProfile.user_id == user1_id)
            .one()
        )
        u2_profile = (
            db.query(CandidateProfile)
            .filter(CandidateProfile.user_id == user2_id)
            .one()
        )
        u1_assets = (
            db.query(CareerAsset)
            .filter(CareerAsset.profile_id == u1_profile.id)
            .all()
        )
        u2_assets = (
            db.query(CareerAsset)
            .filter(CareerAsset.profile_id == u2_profile.id)
            .all()
        )
        assert {asset.id for asset in u1_assets}.isdisjoint(
            {asset.id for asset in u2_assets}
        )
        assert {asset.storage_path for asset in u1_assets} == {
            asset.storage_path for asset in u2_assets
        }

        u1_artifact_ids = {
            item.id
            for item in db.query(CampaignArtifact)
            .filter(CampaignArtifact.campaign_id == resp1.campaign_id)
            .all()
        }
        u2_artifact_ids = {
            item.id
            for item in db.query(CampaignArtifact)
            .filter(CampaignArtifact.campaign_id == resp2.campaign_id)
            .all()
        }
        assert u1_artifact_ids.isdisjoint(u2_artifact_ids)

        u1_source_ids = {
            item.id
            for item in db.query(SourceDocument)
            .filter(SourceDocument.profile_id == u1_profile.id)
            .all()
        }
        u2_source_ids = {
            item.id
            for item in db.query(SourceDocument)
            .filter(SourceDocument.profile_id == u2_profile.id)
            .all()
        }
        assert u1_source_ids.isdisjoint(u2_source_ids)

        # Per-profile rows reference the same verified content-addressed paths.
        for path_str in {asset.storage_path for asset in u1_assets + u2_assets}:
            assert resolve_data_path(path_str, create_root=False).exists()


def test_import_campaign_duplicate_content_artifacts_share_career_asset(service_vault) -> None:
    factory, data_dir, user1_id, _ = service_vault

    # Create an archive with two distinct logical artifacts having identical bytes
    base_zip = build_fictional_campaign_zip()
    bio = BytesIO()
    with zipfile.ZipFile(BytesIO(base_zip), "r") as zin:
        with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                zout.writestr(item, zin.read(item.filename))
            # Add duplicate bytes files under application-packets/
            zout.writestr("application-packets/APP-001/extra_notes.txt", b"Identical notes content 12345")
            zout.writestr("application-packets/APP-002/extra_notes.txt", b"Identical notes content 12345")

    dup_zip = bio.getvalue()
    preview = parse_campaign_workspace(dup_zip)
    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    with factory() as db:
        resp = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=dup_zip,
            expected_fingerprint=preview.fingerprint,
            imported_at=now,
            profile_display_name="Dup Tester",
        )
    assert resp.created is True

    with factory() as db:
        art1 = db.query(CampaignArtifact).filter(CampaignArtifact.relative_path == "application-packets/APP-001/extra_notes.txt").first()
        art2 = db.query(CampaignArtifact).filter(CampaignArtifact.relative_path == "application-packets/APP-002/extra_notes.txt").first()
        assert art1 is not None and art2 is not None
        assert art1.id != art2.id
        # Both logical artifacts share the exact same CareerAsset
        assert art1.asset_id == art2.asset_id


def test_import_campaign_pre_commit_rollback_cleans_new_files_preserves_shared(service_vault, monkeypatch) -> None:
    factory, data_dir, user1_id, user2_id = service_vault
    zip_bytes = build_fictional_campaign_zip()
    preview = parse_campaign_workspace(zip_bytes)
    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    # User 1 successfully imports -> publishes shared assets
    with factory() as db:
        import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=zip_bytes,
            expected_fingerprint=preview.fingerprint,
            imported_at=now,
            profile_display_name="User One",
        )

    # Snapshot disk files owned by User 1
    committed_files = {p for p in data_dir.rglob("*") if p.is_file()}
    assert len(committed_files) > 0

    # Create new archive for User 2 with one brand new unique file inside application-packets
    new_doc_path = "application-packets/APP-001/brand_new_doc.txt"
    bio = BytesIO()
    with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zin:
        with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                zout.writestr(item, zin.read(item.filename))
            zout.writestr(new_doc_path, b"Unique bytes never seen before 1234567890")

    u2_zip = bio.getvalue()
    u2_preview = parse_campaign_workspace(u2_zip)

    # Monkeypatch to raise an error during entity persistence before db.commit
    orig_add = Session.add

    def fail_add(self, instance, _warn=True):
        if isinstance(instance, CampaignArtifact) and instance.relative_path == new_doc_path:
            raise RuntimeError("Simulated pre-commit failure on artifact persistence")
        return orig_add(self, instance, _warn=_warn)

    monkeypatch.setattr(Session, "add", fail_add)

    with factory() as db:
        with pytest.raises(CampaignImportError) as error:
            import_campaign(
                db,
                user_id=user2_id,
                archive_bytes=u2_zip,
                expected_fingerprint=u2_preview.fingerprint,
                imported_at=now,
                profile_display_name="User Two",
            )
        assert db.in_transaction() is False
    assert error.value.status_code == 500
    assert "simulated" not in str(error.value).lower()
    assert "brand_new_doc" not in str(error.value).lower()

    # Verify rollback behavior:
    # 1. User 2 has zero committed campaigns
    with factory() as db:
        assert db.query(Campaign).filter(Campaign.user_id == user2_id).count() == 0

    # 2. The newly written file for brand_new_doc.txt was unlinked
    current_files = {p for p in data_dir.rglob("*") if p.is_file()}
    assert current_files == committed_files

    # 3. All pre-existing committed files belonging to User 1 are still present
    for p in committed_files:
        assert p.exists()
    assert _journal_files(data_dir) == []


def test_import_campaign_commit_uncertainty_recovery(service_vault, monkeypatch) -> None:
    factory, data_dir, user1_id, _ = service_vault
    zip_bytes = build_fictional_campaign_zip()
    preview = parse_campaign_workspace(zip_bytes)
    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    # Simulate commit uncertainty: db.commit executes real commit, but then raises an error
    orig_commit = Session.commit

    def flaky_commit(self):
        orig_commit(self)
        raise RuntimeError("Simulated connection reset immediately after database commit")

    monkeypatch.setattr(Session, "commit", flaky_commit)

    with factory() as db:
        resp = import_campaign(
            db,
            user_id=user1_id,
            archive_bytes=zip_bytes,
            expected_fingerprint=preview.fingerprint,
            imported_at=now,
            profile_display_name="Jane Doe",
        )
        assert db.in_transaction() is False

    # Recovery successfully verified the committed campaign and returned success
    assert resp.created is True
    assert resp.fingerprint == preview.fingerprint
    assert resp.application_count == 5
    assert resp.artifact_count == len(preview.artifacts)

    with factory() as db:
        assert db.query(Campaign).filter(Campaign.id == resp.campaign_id).count() == 1
    assert _journal_files(data_dir) == []


def test_import_campaign_commit_uncertainty_rejects_same_count_corruption(
    service_vault,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, data_dir, user1_id, _ = service_vault
    archive = build_fictional_campaign_zip()
    parsed = parse_campaign_workspace(archive)
    imported_at = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    real_commit = Session.commit
    replacement_event_id = str(uuid.uuid4())

    def committed_then_corrupted(session: Session) -> None:
        real_commit(session)
        engine = session.get_bind()
        with engine.begin() as connection:
            original_event_id = connection.execute(
                text("SELECT id FROM application_events ORDER BY id LIMIT 1")
            ).scalar_one()
            connection.execute(
                text("UPDATE application_events SET id = :replacement WHERE id = :original"),
                {"replacement": replacement_event_id, "original": original_event_id},
            )
        raise RuntimeError("PRIVATE commit transport detail")

    monkeypatch.setattr(Session, "commit", committed_then_corrupted)
    with factory() as db:
        with pytest.raises(CampaignImportError) as error:
            import_campaign(
                db,
                user_id=user1_id,
                archive_bytes=archive,
                expected_fingerprint=parsed.fingerprint,
                imported_at=imported_at,
                profile_display_name="Commit Recovery Test",
            )
        assert db.in_transaction() is False

    assert error.value.status_code == 500
    assert "private" not in str(error.value).lower()
    assert "transport" not in str(error.value).lower()
    assert _journal_files(data_dir) == []
    with factory() as db:
        assert db.query(Campaign).count() == 1
        assert (
            db.query(ApplicationEvent)
            .filter(ApplicationEvent.id == replacement_event_id)
            .count()
            == 1
        )
        for asset in db.query(CareerAsset).all():
            assert resolve_data_path(asset.storage_path, create_root=False).is_file()
