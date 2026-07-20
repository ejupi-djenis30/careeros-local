from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_release_versions import ROOT
from scripts.license_contract import APPROVED_LICENSE_SHA256
from scripts.release_contract import (
    EVIDENCE_ARCHIVE,
    assemble_release_bundle,
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
    write_native_candidates,
    write_release_bundle,
)


def test_bundle_has_exact_global_inventory_and_valid_native_subjects(tmp_path: Path) -> None:
    bundle, native_checksums = write_release_bundle(tmp_path, ROOT / "LICENSE")

    assert sorted((path.name for path in bundle.iterdir()), key=str.casefold) == expected_public_names(
        VERSION
    )
    assert len(expected_public_names(VERSION)) == 23
    manifest = validate_release_bundle(
        bundle,
        version=VERSION,
        source_commit=COMMIT,
        release_date=RELEASE_DATE,
        license_path=ROOT / "LICENSE",
    )
    native_records = [record for target in manifest["targets"] for record in target["artifacts"]]
    validate_native_subject_checksums(native_checksums, records=native_records)


def test_non_mit_text_named_license_is_rejected(tmp_path: Path) -> None:
    fake = tmp_path / "fake" / "LICENSE"
    fake.parent.mkdir()
    fake.write_text("This is not the approved license.\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="approved MIT license"):
        write_release_bundle(tmp_path / "case", fake)


def test_approved_license_binding_is_stable_across_checkout_newlines(tmp_path: Path) -> None:
    canonical = (ROOT / "LICENSE").read_bytes().replace(b"\r\n", b"\n")
    checkout_license = tmp_path / "checkout" / "LICENSE"
    checkout_license.parent.mkdir()
    checkout_license.write_bytes(canonical.replace(b"\n", b"\r\n"))

    bundle, _ = write_release_bundle(tmp_path / "case", checkout_license)
    manifest = validate_release_bundle(
        bundle,
        version=VERSION,
        source_commit=COMMIT,
        release_date=RELEASE_DATE,
        license_path=checkout_license,
    )

    assert manifest["license"] == {
        "spdx": "MIT",
        "name": "LICENSE",
        "normalization": "utf-8-lf",
        "size": len(canonical),
        "sha256": APPROVED_LICENSE_SHA256,
    }
    assert (bundle / "LICENSE").read_bytes() == canonical


def test_public_license_is_required_and_tampering_fails_closed(tmp_path: Path) -> None:
    bundle, _ = write_release_bundle(tmp_path, ROOT / "LICENSE")
    public_license = bundle / "LICENSE"
    public_license.unlink()

    with pytest.raises(RuntimeError, match="missing or unexpected"):
        validate_release_bundle(
            bundle,
            version=VERSION,
            source_commit=COMMIT,
            release_date=RELEASE_DATE,
            license_path=ROOT / "LICENSE",
        )

    public_license.write_bytes(b"tampered license\n")
    with pytest.raises(RuntimeError, match="differs from the approved text"):
        validate_release_bundle(
            bundle,
            version=VERSION,
            source_commit=COMMIT,
            release_date=RELEASE_DATE,
            license_path=ROOT / "LICENSE",
        )


def _assemble_candidates(tmp_path: Path, native: Path) -> None:
    assemble_release_bundle(
        native_root=native,
        evidence_root=write_evidence(tmp_path / "evidence"),
        output=tmp_path / "release",
        native_checksums=tmp_path / "attestation" / "native-subjects.sha256",
        version=VERSION,
        source_commit=COMMIT,
        release_date=RELEASE_DATE,
        license_path=ROOT / "LICENSE",
    )


def test_missing_native_target_fails_closed(tmp_path: Path) -> None:
    native = write_native_candidates(tmp_path / "native")
    next(native.rglob("candidate-aarch64-unknown-linux-gnu.json")).unlink()

    with pytest.raises(RuntimeError, match="Expected 6 native target manifests, found 5"):
        _assemble_candidates(tmp_path, native)


def test_extra_native_target_fails_closed(tmp_path: Path) -> None:
    native = write_native_candidates(tmp_path / "native")
    foreign = native / "foreign"
    foreign.mkdir()
    (foreign / "candidate-foreign-target.json").write_text(
        '{"target":"foreign-target"}\n', encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="Expected 6 native target manifests, found 7"):
        _assemble_candidates(tmp_path, native)


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
