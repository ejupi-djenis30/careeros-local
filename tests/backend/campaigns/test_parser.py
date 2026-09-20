"""Tests for parsed campaign workspace representation and preview parity."""

from __future__ import annotations

import io
import zipfile
from dataclasses import FrozenInstanceError
from datetime import date
from typing import Any

import pytest

from backend.campaigns.archive_policy import ArchivePolicyError
from backend.campaigns.parser import parse_campaign_workspace
from backend.campaigns.parser_types import (
    ParsedApplication,
    ParsedArtifact,
    ParsedCampaign,
)
from backend.campaigns.preview import (
    build_campaign_preview,
    preview_from_parsed_campaign,
)
from backend.campaigns.xlsx_reader import read_campaign_workbook
from tests.backend.campaigns.fixture_builder import build_fictional_campaign_zip


def test_parse_campaign_workspace_structure_and_bindings() -> None:
    zip_bytes = build_fictional_campaign_zip()
    parsed = parse_campaign_workspace(zip_bytes)

    assert isinstance(parsed, ParsedCampaign)
    assert all(isinstance(a, ParsedApplication) for a in parsed.applications)
    assert all(isinstance(art, ParsedArtifact) for art in parsed.artifacts)
    assert len(parsed.fingerprint) == 64
    assert parsed.suggested_name == "Legacy application campaign"
    assert parsed.suggested_profile_name == "Fictional Profile"

    # Tracker digest and sanitized replacement
    assert parsed.tracker_sha256 is not None
    assert parsed.sanitized_tracker_bytes is not None
    assert parsed.sanitized_tracker_sha256 is not None
    assert parsed.tracker_sha256 != parsed.sanitized_tracker_sha256

    # Logical artifact count unchanged
    assert len(parsed.artifacts) == len(parsed.inspection.members)

    # ApplicationTracker artifact is replaced by sanitized bytes
    tracker_artifact = next((a for a in parsed.artifacts if a.relative_path == "ApplicationTracker.xlsx"), None)
    assert tracker_artifact is not None
    assert tracker_artifact.category == "tracker"
    assert tracker_artifact.raw_bytes == parsed.sanitized_tracker_bytes
    assert tracker_artifact.sha256 == parsed.sanitized_tracker_sha256
    assert tracker_artifact.source_application_id is None

    # Sanitized tracker has credentials_count == 0
    san_read = read_campaign_workbook(parsed.sanitized_tracker_bytes)
    assert san_read.credentials_count == 0
    assert len(san_read.rows) == len(parsed.tracker_rows)

    # Dossier packet artifacts are bound to source application IDs
    packet_artifacts = [a for a in parsed.artifacts if a.relative_path.startswith("application-packets/")]
    assert len(packet_artifacts) > 0
    for pa in packet_artifacts:
        assert pa.source_application_id in ("APP-001", "APP-002", "dossier-only-001")

    # Root artifacts are not bound to any application
    root_artifacts = [a for a in parsed.artifacts if not a.relative_path.startswith("application-packets/")]
    for ra in root_artifacts:
        assert ra.source_application_id is None


def test_preview_parity_between_direct_and_parsed() -> None:
    zip_bytes = build_fictional_campaign_zip()

    preview_direct = build_campaign_preview(zip_bytes, user_has_profile=False)
    parsed = parse_campaign_workspace(zip_bytes)
    preview_projected = preview_from_parsed_campaign(parsed, user_has_profile=False)

    assert preview_direct.fingerprint == preview_projected.fingerprint
    assert preview_direct.suggested_name == preview_projected.suggested_name
    assert preview_direct.suggested_profile_name == preview_projected.suggested_profile_name
    assert preview_direct.tracker_rows == preview_projected.tracker_rows
    assert preview_direct.dossier_count == preview_projected.dossier_count
    assert preview_direct.matched_count == preview_projected.matched_count
    assert preview_direct.tracker_only_count == preview_projected.tracker_only_count
    assert preview_direct.dossier_only_count == preview_projected.dossier_only_count
    assert preview_direct.logical_application_count == preview_projected.logical_application_count
    assert preview_direct.artifact_count == preview_projected.artifact_count
    assert preview_direct.expanded_bytes == preview_projected.expanded_bytes
    assert preview_direct.status_counts == preview_projected.status_counts
    assert preview_direct.credential_rows_omitted == preview_projected.credential_rows_omitted
    assert preview_direct.warnings == preview_projected.warnings
    assert preview_direct.requires_profile_name == preview_projected.requires_profile_name
    assert len(preview_direct.sample) == len(preview_projected.sample)

    for item_dir, item_proj in zip(preview_direct.sample, preview_projected.sample):
        assert item_dir.source_application_id == item_proj.source_application_id
        assert item_dir.title == item_proj.title
        assert item_dir.company == item_proj.company
        assert item_dir.source_status == item_proj.source_status
        assert item_dir.provenance == item_proj.provenance


def test_parsed_campaign_immutability() -> None:
    zip_bytes = build_fictional_campaign_zip()
    parsed = parse_campaign_workspace(zip_bytes)

    # 1. Dataclass top-level attribute reassignment
    with pytest.raises(FrozenInstanceError):
        parsed.fingerprint = "mutated"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        parsed.applications[0].title = "mutated"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        parsed.artifacts[0].relative_path = "mutated"  # type: ignore[misc]

    # 2. Ordered sequence container immutability (tuples)
    with pytest.raises(AttributeError):
        parsed.headers.append("NewHeader")  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        parsed.headers[0] = "NewHeader"  # type: ignore[index]

    with pytest.raises(AttributeError):
        parsed.tracker_rows.append(parsed.tracker_rows[0])  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        parsed.tracker_rows[0] = parsed.tracker_rows[0]  # type: ignore[index]

    with pytest.raises(AttributeError):
        parsed.applications.append(parsed.applications[0])  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        parsed.applications[0] = parsed.applications[0]  # type: ignore[index]

    with pytest.raises(AttributeError):
        parsed.artifacts.append(parsed.artifacts[0])  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        parsed.artifacts[0] = parsed.artifacts[0]  # type: ignore[index]

    with pytest.raises(AttributeError):
        parsed.warnings.append("Extra warning")  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        parsed.warnings[0] = "Extra warning"  # type: ignore[index]

    # 3. Read-only mappings (MappingProxyType)
    with pytest.raises(TypeError):
        parsed.status_counts["Saved"] = 999  # type: ignore[index]
    with pytest.raises(AttributeError):
        parsed.status_counts.pop("Saved")  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        del parsed.status_counts["Saved"]  # type: ignore[operator]

    with pytest.raises(TypeError):
        parsed.inspection.members["new_entry"] = parsed.artifacts[0]  # type: ignore[index]
    with pytest.raises(AttributeError):
        parsed.inspection.members.pop("ApplicationTracker.xlsx")  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        del parsed.inspection.members["ApplicationTracker.xlsx"]  # type: ignore[operator]

    # 4. Nested container immutability on applications
    app0 = parsed.applications[0]
    with pytest.raises(TypeError):
        app0.tracker_record["Application ID"] = "HACKED"  # type: ignore[index]
    with pytest.raises(AttributeError):
        app0.tracker_record.pop("Application ID")  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        del app0.tracker_record["Application ID"]  # type: ignore[operator]

    with pytest.raises(TypeError):
        app0.provenance["sources"] = ("tampered",)  # type: ignore[index]
    with pytest.raises(AttributeError):
        app0.provenance["sources"].append("tampered")  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        app0.provenance["sources"][0] = "tampered"  # type: ignore[index]

    # 5. Tracker application row raw_record immutability
    row0 = parsed.tracker_rows[0]
    with pytest.raises(TypeError):
        row0.raw_record["Application ID"] = "HACKED"  # type: ignore[index]
    with pytest.raises(AttributeError):
        row0.raw_record.pop("Application ID")  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        del row0.raw_record["Application ID"]  # type: ignore[operator]


def test_collision_and_safe_error_handling() -> None:
    # Build archive with colliding suffixed packet directories
    base_zip = build_fictional_campaign_zip()
    in_buf = io.BytesIO(base_zip)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            if item.filename != "application-packets/APP-002/cv.docx":
                z_out.writestr(item, z_in.read(item.filename))
        z_out.writestr("application-packets/APP-002_slug_1/cv.docx", b"cv_1")
        z_out.writestr("application-packets/APP-002_slug_2/cv.docx", b"cv_2")

    colliding_zip = out_buf.getvalue()

    with pytest.raises(ArchivePolicyError) as exc_info:
        parse_campaign_workspace(colliding_zip)

    assert "Ambiguous packet directories" in str(exc_info.value)
    assert "APP-002" in str(exc_info.value)
    # Ensure error does not leak secrets
    assert "password" not in str(exc_info.value).lower()


def test_zero_db_and_filesystem_mutations(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    # Verify no open(..., 'w') calls happen during parse or preview
    original_open = builtins.open

    def guarded_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if any(write_flag in mode for write_flag in ("w", "a", "+")):
            raise AssertionError(f"Write operation attempted during campaign parse: {file} mode={mode}")
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)

    zip_bytes = build_fictional_campaign_zip()
    parsed = parse_campaign_workspace(zip_bytes)
    preview = preview_from_parsed_campaign(parsed)

    assert parsed is not None
    assert preview is not None


def test_parsed_campaign_preserves_scalars_dates_nulls() -> None:
    zip_bytes = build_fictional_campaign_zip()
    parsed = parse_campaign_workspace(zip_bytes)

    # Check APP-001 has dates, strings, and null fields preserved
    app1 = next((a for a in parsed.applications if a.source_application_id == "APP-001"), None)
    assert app1 is not None
    assert app1.found_at == date(2026, 1, 10)
    assert app1.applied_at == date(2026, 1, 12)
    assert app1.follow_up_at == date(2026, 1, 26)
    assert app1.last_update_at == date(2026, 1, 15)
    assert app1.notes == "Synthetic fictional note"
    assert app1.outcome is None  # APP-001 has no outcome in fixture

    # Check APP-002 has outcome and null next_action
    app2 = next((a for a in parsed.applications if a.source_application_id == "APP-002"), None)
    assert app2 is not None
    assert app2.outcome == "Position cancelled"
    assert app2.next_action is None

    # Check tracker_record contains exact 28 keys
    assert len(app1.tracker_record) == 28
    assert app1.tracker_record["Date Found"] == "2026-01-10"
    assert app1.tracker_record["Outcome"] is None
