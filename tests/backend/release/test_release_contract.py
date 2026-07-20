from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_release_versions import ROOT
from scripts.release_contract import (
    EVIDENCE_ARCHIVE,
    expected_public_names,
    validate_evidence_directory,
    validate_native_subject_checksums,
    validate_release_bundle,
    validate_release_date,
)
from tests.backend.release.helpers import (
    COMMIT,
    RELEASE_DATE,
    VERSION,
    write_evidence,
    write_release_bundle,
)


def test_bundle_has_exact_global_inventory_and_valid_native_subjects(tmp_path: Path) -> None:
    bundle, native_checksums = write_release_bundle(tmp_path, ROOT / "LICENSE")

    assert sorted((path.name for path in bundle.iterdir()), key=str.casefold) == expected_public_names(
        VERSION
    )
    assert len(expected_public_names(VERSION)) == 22
    manifest = validate_release_bundle(
        bundle,
        version=VERSION,
        source_commit=COMMIT,
        release_date=RELEASE_DATE,
        license_path=ROOT / "LICENSE",
    )
    native_records = [record for target in manifest["targets"] for record in target["artifacts"]]
    validate_native_subject_checksums(native_checksums, records=native_records)


def test_bundle_rejects_tampering_and_unexpected_files(tmp_path: Path) -> None:
    bundle, _ = write_release_bundle(tmp_path, ROOT / "LICENSE")
    package = next(path for path in bundle.iterdir() if path.suffix == ".exe")
    package.write_bytes(b"tampered")

    with pytest.raises(RuntimeError, match="SHA256SUMS"):
        validate_release_bundle(
            bundle,
            version=VERSION,
            source_commit=COMMIT,
            release_date=RELEASE_DATE,
            license_path=ROOT / "LICENSE",
        )

    (bundle / "unexpected.txt").write_text("no", encoding="utf-8")
    with pytest.raises(RuntimeError, match="missing or unexpected"):
        validate_release_bundle(
            bundle,
            version=VERSION,
            source_commit=COMMIT,
            release_date=RELEASE_DATE,
            license_path=ROOT / "LICENSE",
        )


def test_evidence_archive_is_safe_and_bound_to_public_sboms(tmp_path: Path) -> None:
    bundle, _ = write_release_bundle(tmp_path, ROOT / "LICENSE")
    archive = bundle / EVIDENCE_ARCHIVE
    first = archive.read_bytes()

    bundle_two, _ = write_release_bundle(tmp_path / "second", ROOT / "LICENSE")
    assert first == (bundle_two / EVIDENCE_ARCHIVE).read_bytes()

    public_sbom = bundle / f"careeros-backend-{VERSION}.cdx.json"
    public_sbom.write_text('{"bomFormat":"CycloneDX","specVersion":"1.6","components":[]}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="SHA256SUMS"):
        validate_release_bundle(
            bundle,
            version=VERSION,
            source_commit=COMMIT,
            release_date=RELEASE_DATE,
            license_path=ROOT / "LICENSE",
        )


def test_incomplete_or_foreign_evidence_fails_closed(tmp_path: Path) -> None:
    evidence = write_evidence(tmp_path / "evidence")
    (evidence / "frontend-audit.json").unlink()
    with pytest.raises(RuntimeError, match="missing or unexpected"):
        validate_evidence_directory(evidence)

    (evidence / "foreign.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="missing or unexpected"):
        validate_evidence_directory(evidence)


@pytest.mark.parametrize("value", ["20260720", "2026-7-20", "2026-02-30"])
def test_release_date_must_be_canonical_and_valid(value: str) -> None:
    with pytest.raises(RuntimeError, match="Release date"):
        validate_release_date(value)
