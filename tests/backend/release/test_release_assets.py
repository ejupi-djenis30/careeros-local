from __future__ import annotations

from pathlib import Path

import pytest

from scripts.release_assets import (
    TARGETS,
    canonical_package_name,
    reject_casefold_collisions,
    stage_target_candidate,
    validate_portable_name,
    validate_target_candidate,
)
from tests.backend.release.helpers import COMMIT, VERSION


def test_canonical_names_are_portable_and_casefold_unique() -> None:
    names = [
        canonical_package_name(VERSION, spec, package)
        for spec in TARGETS.values()
        for package in spec.packages
    ]

    assert all(" " not in name and validate_portable_name(name) == name for name in names)
    reject_casefold_collisions(names)


def test_staging_rejects_duplicate_package_types(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "one.exe").write_bytes(b"one")
    (bundle / "two.exe").write_bytes(b"two")
    (bundle / "only.msi").write_bytes(b"msi")

    with pytest.raises(RuntimeError, match="duplicate nsis"):
        stage_target_candidate(
            bundle_root=bundle,
            output=tmp_path / "candidate",
            target="x86_64-pc-windows-msvc",
            version=VERSION,
            source_commit=COMMIT,
        )


def test_candidate_manifest_and_download_checksum_bind_exact_bytes(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "installer.exe").write_bytes(b"exe")
    (bundle / "installer.msi").write_bytes(b"msi")
    output = tmp_path / "candidate"
    manifest = stage_target_candidate(
        bundle_root=bundle,
        output=output,
        target="x86_64-pc-windows-msvc",
        version=VERSION,
        source_commit=COMMIT,
    )

    assert [record["type"] for record in manifest["artifacts"]] == ["nsis", "msi"]
    checksum = (output / manifest["checksum"]).read_text(encoding="utf-8")
    assert all(record["name"] in checksum for record in manifest["artifacts"])

    (output / manifest["artifacts"][0]["name"]).write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="manifest does not match"):
        validate_target_candidate(
            output,
            target="x86_64-pc-windows-msvc",
            version=VERSION,
            source_commit=COMMIT,
        )


def test_staging_rejects_empty_release_packages(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "installer.exe").write_bytes(b"")
    (bundle / "installer.msi").write_bytes(b"msi")

    with pytest.raises(RuntimeError, match="must not be empty"):
        stage_target_candidate(
            bundle_root=bundle,
            output=tmp_path / "candidate",
            target="x86_64-pc-windows-msvc",
            version=VERSION,
            source_commit=COMMIT,
        )


@pytest.mark.parametrize("name", ["CareerOS Local.exe", "../escape.exe", "installer?.exe"])
def test_nonportable_names_fail_closed(name: str) -> None:
    with pytest.raises(RuntimeError, match="not portable"):
        validate_portable_name(name)


def test_casefold_collision_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="Case-insensitive"):
        reject_casefold_collisions(["CareerOS.exe", "careeros.EXE"])
