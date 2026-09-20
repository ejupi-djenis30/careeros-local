"""Tests for campaign preview service and reconciliation aligned with campaign-api contract."""

from __future__ import annotations

import io
import zipfile

import pytest

from backend.campaigns.archive_policy import ArchivePolicyError
from backend.campaigns.preview import build_campaign_preview, reconcile_dossier_directory_name
from tests.backend.campaigns.fixture_builder import build_fictional_campaign_zip


def test_preview_reconciles_matched_tracker_only_and_dossier_only():
    # 4 tracker rows: APP-001, APP-002, APP-003, APP-004
    # Folders in zip: APP-001, APP-002, dossier-only-001
    zip_bytes = build_fictional_campaign_zip(credentials_count=3)
    preview = build_campaign_preview(
        zip_bytes,
        archive_name="test_campaign.zip",
        user_has_profile=True,
    )

    assert preview.suggested_name == "Legacy application campaign"
    assert preview.tracker_rows == 4
    assert preview.dossier_count == 3
    assert preview.matched_count == 2  # APP-001, APP-002
    assert preview.tracker_only_count == 2  # APP-003, APP-004
    assert preview.dossier_only_count == 1  # dossier-only-001
    assert preview.logical_application_count == 5
    assert preview.artifact_count > 0
    assert preview.expanded_bytes > 0
    assert preview.credential_rows_omitted == 3
    assert any("Platform Credentials" in w and "omitted" in w for w in preview.warnings)
    assert not preview.requires_profile_name


def test_preview_profile_requirement_when_user_has_no_profile():
    zip_bytes = build_fictional_campaign_zip()
    preview = build_campaign_preview(
        zip_bytes,
        archive_name="test_campaign.zip",
        user_has_profile=False,
    )
    assert preview.requires_profile_name is True
    assert preview.suggested_profile_name is not None


def test_preview_source_status_counts():
    zip_bytes = build_fictional_campaign_zip()
    preview = build_campaign_preview(zip_bytes)
    # Tracker rows:
    # APP-001: Applied
    # APP-002: Closed
    # APP-003: Preparing
    # APP-004: Saved
    # Note: dossier-only-001 does not increment status_counts (strictly tracker source statuses)
    assert preview.status_counts.get("Applied") == 1
    assert preview.status_counts.get("Closed") == 1
    assert preview.status_counts.get("Preparing") == 1
    assert preview.status_counts.get("Saved") == 1


def test_map_source_status_to_stage():
    from backend.campaigns.schemas import map_source_status_to_stage

    assert map_source_status_to_stage("Saved") == "saved"
    assert map_source_status_to_stage("SAVED") == "saved"
    assert map_source_status_to_stage("  saved  ") == "saved"
    assert map_source_status_to_stage("Preparing") == "preparing"
    assert map_source_status_to_stage("PREPARING") == "preparing"
    assert map_source_status_to_stage("Applied") == "applied"
    assert map_source_status_to_stage("APPLIED") == "applied"
    assert map_source_status_to_stage("Closed") == "archived"
    assert map_source_status_to_stage("CLOSED") == "archived"
    # Fallback to saved
    assert map_source_status_to_stage(None) == "saved"
    assert map_source_status_to_stage("") == "saved"
    assert map_source_status_to_stage("   ") == "saved"
    assert map_source_status_to_stage("Interview") == "saved"
    assert map_source_status_to_stage("Rejected") == "saved"
    assert map_source_status_to_stage("Offer") == "saved"



def test_preview_samples_structure():
    zip_bytes = build_fictional_campaign_zip()
    preview = build_campaign_preview(zip_bytes)
    assert len(preview.sample) > 0
    sample_ids = {s.source_application_id for s in preview.sample}
    assert "APP-001" in sample_ids
    assert "dossier-only-001" in sample_ids

    app1 = next(s for s in preview.sample if s.source_application_id == "APP-001")
    assert "tracker" in app1.provenance
    assert "dossier" in app1.provenance
    assert app1.source_status == "Applied"

    dossier_sample = next(s for s in preview.sample if s.source_application_id == "dossier-only-001")
    assert dossier_sample.provenance == ["dossier"]
    assert dossier_sample.source_status is None
    assert dossier_sample.title == "Lead Architect"


def test_suffixed_dossier_directory_matching():
    # Build base archive and replace APP-002 with suffixed folder APP-002_systems-architect
    base_zip = build_fictional_campaign_zip()
    in_buf = io.BytesIO(base_zip)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            if item.filename == "application-packets/APP-002/cv.docx":
                z_out.writestr("application-packets/APP-002_systems-architect/cv.docx", z_in.read(item.filename))
            else:
                z_out.writestr(item, z_in.read(item.filename))

    preview = build_campaign_preview(out_buf.getvalue())
    assert preview.tracker_rows == 4
    assert preview.dossier_count == 3  # APP-001, APP-002_systems-architect, dossier-only-001
    assert preview.matched_count == 2  # APP-001 and APP-002
    assert preview.tracker_only_count == 2  # APP-003, APP-004
    assert preview.dossier_only_count == 1  # dossier-only-001
    assert preview.logical_application_count == 5

    app2 = next(s for s in preview.sample if s.source_application_id == "APP-002")
    assert app2.provenance == ["tracker", "dossier"]
    assert app2.title == "Systems Architect"


def test_longest_prefix_reconciliation_behavior():
    tracker_ids = {"APP", "APP_DEV", "APP_DEV_LEAD"}

    # Longest prefix followed by '_' wins
    assert reconcile_dossier_directory_name("APP_DEV_LEAD_zurich", tracker_ids) == "APP_DEV_LEAD"
    assert reconcile_dossier_directory_name("APP_DEV_zurich", tracker_ids) == "APP_DEV"
    assert reconcile_dossier_directory_name("APP_zurich", tracker_ids) == "APP"

    # Exact match wins
    assert reconcile_dossier_directory_name("APP_DEV", tracker_ids) == "APP_DEV"

    # Unmatched directory name remains unchanged as dossier-only ID
    assert reconcile_dossier_directory_name("OTHER_slug", tracker_ids) == "OTHER_slug"
    assert reconcile_dossier_directory_name("APPDEV_slug", tracker_ids) == "APPDEV_slug"


def test_duplicate_resolution_exact_and_suffixed_rejected():
    # Archive with both exact folder APP-001 and suffixed folder APP-001_lead-eng
    zip_bytes = build_fictional_campaign_zip(
        members={"application-packets/APP-001_lead-eng/notes.txt": b"notes"}
    )
    with pytest.raises(ArchivePolicyError) as exc_info:
        build_campaign_preview(zip_bytes)
    err_msg = str(exc_info.value)
    assert err_msg == "Ambiguous packet directories resolve to the same source ID 'APP-001'"
    assert "lead-eng" not in err_msg


def test_duplicate_resolution_two_suffixed_rejected():
    # Archive with two distinct suffixed folders for APP-002
    base_zip = build_fictional_campaign_zip()
    in_buf = io.BytesIO(base_zip)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            if item.filename != "application-packets/APP-002/cv.docx":
                z_out.writestr(item, z_in.read(item.filename))
        z_out.writestr("application-packets/APP-002_slug_a/cv.docx", b"cv_a")
        z_out.writestr("application-packets/APP-002_slug_b/cv.docx", b"cv_b")

    with pytest.raises(ArchivePolicyError) as exc_info:
        build_campaign_preview(out_buf.getvalue())
    err_msg = str(exc_info.value)
    assert err_msg == "Ambiguous packet directories resolve to the same source ID 'APP-002'"
    assert "slug_a" not in err_msg
    assert "slug_b" not in err_msg
