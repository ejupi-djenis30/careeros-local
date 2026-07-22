from __future__ import annotations

import json
from pathlib import Path

from scripts.release_assets import TARGETS, stage_target_candidate
from scripts.release_contract import EVIDENCE_FILES, assemble_release_bundle

VERSION = "1.2.0"
COMMIT = "a" * 40
RELEASE_DATE = "2026-07-22"


def write_evidence(path: Path) -> Path:
    path.mkdir(parents=True)
    cyclonedx = {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": []}
    for name in EVIDENCE_FILES:
        destination = path / name
        if name.endswith("-sbom.cdx.json"):
            payload: object = cyclonedx
        elif name.endswith(".json"):
            payload = {"evidence": name}
        else:
            destination.write_text(f"evidence for {name}\n", encoding="utf-8")
            continue
        destination.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_native_candidates(path: Path) -> Path:
    path.mkdir(parents=True)
    for index, (target, spec) in enumerate(TARGETS.items()):
        bundle = path / f"raw-{target}"
        bundle.mkdir()
        for package_index, package in enumerate(spec.packages):
            (bundle / f"upstream-{package_index}{package.suffix}").write_bytes(
                f"{index}:{package.name}".encode()
            )
        output = path / target
        stage_target_candidate(
            bundle_root=bundle,
            output=output,
            target=target,
            version=VERSION,
            source_commit=COMMIT,
        )
    return path


def write_release_bundle(tmp_path: Path, license_path: Path) -> tuple[Path, Path]:
    native = write_native_candidates(tmp_path / "native")
    evidence = write_evidence(tmp_path / "evidence")
    output = tmp_path / "release"
    checksums = tmp_path / "attestation" / "native-subjects.sha256"
    assemble_release_bundle(
        native_root=native,
        evidence_root=evidence,
        output=output,
        native_checksums=checksums,
        version=VERSION,
        source_commit=COMMIT,
        release_date=RELEASE_DATE,
        license_path=license_path,
    )
    return output, checksums
