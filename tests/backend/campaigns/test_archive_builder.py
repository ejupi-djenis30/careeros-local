"""Acceptance contracts for the local deterministic campaign ZIP builder."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path

import pytest

import scripts.campaign_archive_builder as builder
from backend.campaigns.archive_policy import inspect_and_validate_campaign_archive

REPO_ROOT = Path(__file__).resolve().parents[3]
BUILD_CLI = REPO_ROOT / "scripts" / "build_campaign_archive.py"


def _seed_tree(root: Path) -> dict[str, bytes]:
    allowed = {
        "ApplicationTracker.xlsx": b"original-tracker-with-synthetic-credential-marker",
        "Profile.md": b"# Private Synthetic Profile",
        "Diploma.PDF": b"%PDF-1.4 synthetic",
        "assets/photo.jpg": b"synthetic-image",
        "application-packets/APP-001/vacancy.md": b"private synthetic vacancy",
        "cv-templates/cv.html": b"<html>private synthetic cv</html>",
        "cover-letter-templates/letter.md": b"private synthetic letter",
        "email-templates/email.md": b"private synthetic email",
        "html-templates/card.html": b"<div>private synthetic card</div>",
        "scripts/local_helper.py": b"print('private synthetic helper')",
    }
    excluded = {
        "outputs/export.pdf": b"must stay out",
        "backups/campaign.zip": b"must stay out",
        "tmp/cache.bin": b"must stay out",
        "careeros-local/.env": b"must stay out",
        "notes-private.md": b"must stay out",
    }
    for name, payload in {**allowed, **excluded}.items():
        path = root / Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return allowed


def test_builder_is_allowlist_only_deterministic_and_keeps_original_tracker(
    tmp_path: Path,
) -> None:
    source = tmp_path / "private-source-name"
    source.mkdir()
    expected = _seed_tree(source)
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    first_result = builder.build_campaign_archive(source, first)
    second_result = builder.build_campaign_archive(source, second)

    assert first.read_bytes() == second.read_bytes()
    assert first_result == second_result
    assert first_result.member_count == len(expected)
    assert first_result.total_byte_size == sum(map(len, expected.values()))
    assert first_result.archive_sha256 == hashlib.sha256(first.read_bytes()).hexdigest()

    with zipfile.ZipFile(first) as archive:
        infos = archive.infolist()
        assert archive.comment == b""
        assert [item.filename for item in infos] == sorted(expected)
        assert all(not item.is_dir() for item in infos)
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in infos)
        assert all(item.comment == b"" and item.extra == b"" for item in infos)
        assert {item.filename: archive.read(item) for item in infos} == expected
        assert archive.read("ApplicationTracker.xlsx") == expected["ApplicationTracker.xlsx"]

    inspected = inspect_and_validate_campaign_archive(first.read_bytes())
    assert inspected.fingerprint == first_result.source_fingerprint
    assert inspected.member_count == first_result.member_count
    assert inspected.total_byte_size == first_result.total_byte_size


@pytest.mark.parametrize(
    ("limit_name", "limit"),
    [
        ("MAX_FILE_BYTES", 3),
        ("MAX_MEMBERS", 1),
        ("MAX_EXPANDED_BYTES", 3),
        ("MAX_COMPRESSED_BYTES", 1),
    ],
)
def test_builder_limit_failure_is_atomic_and_preserves_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
    limit: int,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "Profile.md").write_bytes(b"four")
    (source / "Goal.md").write_bytes(b"five")
    output = tmp_path / "campaign.zip"
    output.write_bytes(b"existing-output-must-survive")
    monkeypatch.setattr(builder, limit_name, limit)

    with pytest.raises(builder.CampaignArchiveBuildError):
        builder.build_campaign_archive(source, output)

    assert output.read_bytes() == b"existing-output-must-survive"
    assert set(tmp_path.iterdir()) == {source, output}


def test_builder_rejects_output_inside_source_tree(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "Profile.md").write_text("synthetic", encoding="utf-8")

    with pytest.raises(builder.CampaignArchiveBuildError):
        builder.build_campaign_archive(source, source / "campaign.zip")

    assert not (source / "campaign.zip").exists()


def test_builder_rejects_symlink_without_following_it(tmp_path: Path) -> None:
    source = tmp_path / "source"
    assets = source / "assets"
    assets.mkdir(parents=True)
    outside = tmp_path / "private-outside.txt"
    outside.write_bytes(b"must never be read")
    link = assets / "linked.txt"
    try:
        os.symlink(outside, link)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(builder.CampaignArchiveBuildError):
        builder.build_campaign_archive(source, tmp_path / "campaign.zip")

    assert not (tmp_path / "campaign.zip").exists()


def test_builder_rejects_symlinked_source_root(tmp_path: Path) -> None:
    real_source = tmp_path / "real-source"
    real_source.mkdir()
    (real_source / "Profile.md").write_text("synthetic", encoding="utf-8")
    linked_source = tmp_path / "linked-source"
    try:
        os.symlink(real_source, linked_source, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")

    with pytest.raises(builder.CampaignArchiveBuildError):
        builder.build_campaign_archive(linked_source, tmp_path / "campaign.zip")

    assert not (tmp_path / "campaign.zip").exists()


def test_builder_rejects_symlinked_existing_output_without_touching_target(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "Profile.md").write_text("synthetic", encoding="utf-8")
    target = tmp_path / "private-existing-target.zip"
    target.write_bytes(b"existing-target-must-survive")
    output = tmp_path / "linked-output.zip"
    try:
        os.symlink(target, output)
    except OSError as exc:
        pytest.skip(f"file symlink creation is unavailable: {exc}")

    with pytest.raises(builder.CampaignArchiveBuildError):
        builder.build_campaign_archive(source, output)

    assert output.is_symlink()
    assert target.read_bytes() == b"existing-target-must-survive"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction contract")
def test_builder_rejects_windows_directory_junction(tmp_path: Path) -> None:
    source = tmp_path / "source"
    assets = source / "assets"
    assets.mkdir(parents=True)
    (source / "Profile.md").write_text("synthetic", encoding="utf-8")
    outside = tmp_path / "private-outside-directory"
    outside.mkdir()
    (outside / "secret.txt").write_bytes(b"must never be read")
    junction = assets / "linked-directory"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip("directory junction creation is unavailable")

    try:
        with pytest.raises(builder.CampaignArchiveBuildError):
            builder.build_campaign_archive(source, tmp_path / "campaign.zip")
    finally:
        os.rmdir(junction)

    assert not (tmp_path / "campaign.zip").exists()


def test_builder_rejects_nfc_casefold_collision(tmp_path: Path) -> None:
    source = tmp_path / "source"
    assets = source / "assets"
    assets.mkdir(parents=True)
    composed = assets / "caf\u00e9.txt"
    decomposed = assets / "cafe\u0301.txt"
    composed.write_bytes(b"one")
    decomposed.write_bytes(b"two")
    if len(list(assets.iterdir())) != 2:
        pytest.skip("filesystem normalizes Unicode filenames")
    assert unicodedata.normalize("NFC", composed.name) == unicodedata.normalize(
        "NFC", decomposed.name
    )

    with pytest.raises(builder.CampaignArchiveBuildError):
        builder.build_campaign_archive(source, tmp_path / "campaign.zip")


def test_builder_cli_prints_canonical_aggregate_json_without_paths(tmp_path: Path) -> None:
    source = tmp_path / "PRIVATE_PERSON_campaign"
    source.mkdir()
    _seed_tree(source)
    output = tmp_path / "campaign.zip"

    completed = subprocess.run(
        [sys.executable, str(BUILD_CLI), str(source), str(output)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert set(report) == {
        "archive_sha256",
        "member_count",
        "source_fingerprint",
        "total_byte_size",
    }
    assert completed.stdout.strip() == json.dumps(
        report, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    assert "PRIVATE_PERSON" not in completed.stdout
    assert str(source) not in completed.stdout
    assert str(output) not in completed.stdout
    assert completed.stderr == ""
    assert output.is_file()
