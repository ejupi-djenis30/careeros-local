"""Privacy and determinism contracts for aggregate-only campaign validation."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from backend.campaigns.aggregate_validation import build_campaign_validation_report
from backend.campaigns.parser import parse_campaign_workspace
from tests.backend.campaigns.fixture_builder import build_fictional_campaign_zip

REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATE_CLI = REPO_ROOT / "scripts" / "validate_campaign_archive.py"
REPORT_KEYS = {
    "artifact_count",
    "credential_rows_omitted",
    "descriptive_suffix_match_count",
    "dossier_count",
    "dossier_only_count",
    "expanded_bytes",
    "logical_application_count",
    "matched_count",
    "member_count",
    "member_digest_commitment",
    "member_sha256",
    "source_fingerprint",
    "status_counts",
    "tracker_only_count",
    "tracker_rows",
    "typed_projection_counts",
}


def _archive_with_descriptive_packet_dir() -> bytes:
    original = build_fictional_campaign_zip(credentials_count=2)
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(
        output, "w", zipfile.ZIP_DEFLATED
    ) as target:
        for item in reversed(source.infolist()):
            name = item.filename.replace(
                "application-packets/APP-001/",
                "application-packets/APP-001_descriptive-role/",
            )
            info = zipfile.ZipInfo(name, date_time=(2024, 2, 3, 4, 5, 6))
            info.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(info, source.read(item))
    return output.getvalue()


def test_validation_report_is_exact_deterministic_and_aggregate_only() -> None:
    archive = _archive_with_descriptive_packet_dir()
    parsed = parse_campaign_workspace(archive)

    first = build_campaign_validation_report(archive)
    second = build_campaign_validation_report(archive)

    assert first == second
    assert set(first) == REPORT_KEYS
    assert first["source_fingerprint"] == parsed.fingerprint
    assert first["member_count"] == 16
    assert first["expanded_bytes"] == parsed.inspection.total_byte_size
    assert first["tracker_rows"] == 4
    assert first["dossier_count"] == 3
    assert first["matched_count"] == 2
    assert first["tracker_only_count"] == 2
    assert first["dossier_only_count"] == 1
    assert first["logical_application_count"] == 5
    assert first["artifact_count"] == 16
    assert first["credential_rows_omitted"] == 2
    assert first["descriptive_suffix_match_count"] == 1
    assert first["status_counts"] == {
        "Applied": 1,
        "Closed": 1,
        "Preparing": 1,
        "Saved": 1,
    }
    assert first["typed_projection_counts"] == {
        "application_date": 2,
        "date_found": 4,
        "follow_up_date": 2,
        "job_posting_url": 2,
        "last_update": 2,
        "platform_source": 4,
        "platform_url": 2,
    }

    expected_digests = sorted(
        member.sha256 for member in parsed.inspection.members.values()
    )
    assert first["member_sha256"] == expected_digests
    commitment_bytes = b"".join(bytes.fromhex(item) for item in expected_digests)
    assert first["member_digest_commitment"] == hashlib.sha256(
        commitment_bytes
    ).hexdigest()

    serialized = json.dumps(first, ensure_ascii=False, sort_keys=True)
    for private_fragment in (
        "APP-001",
        "Acme",
        "Globex",
        "Fictional",
        "Profile.md",
        "vacancy.md",
        "descriptive-role",
        "pass0",
        "private synthetic",
    ):
        assert private_fragment not in serialized


def test_validation_report_is_independent_of_zip_order_and_timestamps() -> None:
    original = build_fictional_campaign_zip(credentials_count=1)
    rewritten = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(
        rewritten, "w", zipfile.ZIP_DEFLATED
    ) as target:
        for item in reversed(source.infolist()):
            info = zipfile.ZipInfo(item.filename, date_time=(2025, 6, 7, 8, 9, 10))
            info.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(info, source.read(item))

    assert build_campaign_validation_report(original) == build_campaign_validation_report(
        rewritten.getvalue()
    )


def test_validation_cli_prints_only_canonical_report(tmp_path: Path) -> None:
    archive_path = tmp_path / "PRIVATE_PERSON_campaign.zip"
    archive_path.write_bytes(_archive_with_descriptive_packet_dir())

    completed = subprocess.run(
        [sys.executable, str(VALIDATE_CLI), str(archive_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert set(report) == REPORT_KEYS
    assert completed.stdout.strip() == json.dumps(
        report, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    assert "PRIVATE_PERSON" not in completed.stdout
    assert str(archive_path) not in completed.stdout
    assert completed.stderr == ""


def test_validation_cli_failure_is_generic_and_does_not_echo_path(tmp_path: Path) -> None:
    archive_path = tmp_path / "PRIVATE_PERSON_invalid.zip"
    archive_path.write_bytes(b"not a zip and must not be echoed")

    completed = subprocess.run(
        [sys.executable, str(VALIDATE_CLI), str(archive_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "Campaign archive validation failed.\n"
    assert "PRIVATE_PERSON" not in completed.stderr
    assert str(archive_path) not in completed.stderr
    assert "Traceback" not in completed.stderr
