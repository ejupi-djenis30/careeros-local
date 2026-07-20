"""Assemble and verify the exact cross-platform CareerOS release contract."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import shutil
import tarfile
from datetime import date
from pathlib import Path
from typing import Any

from scripts.release_assets import (
    PROJECT,
    TARGETS,
    canonical_package_name,
    checksum_text,
    file_record,
    parse_checksum_text,
    reject_casefold_collisions,
    sha256_file,
    target_checksum_name,
    validate_portable_name,
    validate_source_commit,
    validate_stable_version,
    validate_target_candidate,
)

RELEASE_SCHEMA_VERSION = 2
RELEASE_MANIFEST = "release-manifest.json"
GLOBAL_CHECKSUMS = "SHA256SUMS"
EVIDENCE_ARCHIVE = "supply-chain-evidence.tar.gz"
MAX_EVIDENCE_FILE_SIZE = 64 * 1024 * 1024
MAX_EVIDENCE_ARCHIVE_SIZE = 256 * 1024 * 1024
RELEASE_DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
EVIDENCE_FILES = (
    "backend-licenses.json",
    "backend-sbom.cdx.json",
    "cargo-exception-tree.txt",
    "frontend-audit.json",
    "frontend-licenses.json",
    "frontend-sbom.cdx.json",
    "python-dev-audit.json",
    "python-production-audit.json",
    "python-tooling-audit.json",
    "rust-audit.json",
    "rust-licenses.json",
    "rust-sbom.cdx.json",
    "security-exceptions.json",
)


def sbom_asset_names(version: str) -> dict[str, str]:
    validate_stable_version(version)
    return {
        "backend": f"careeros-backend-{version}.cdx.json",
        "frontend": f"careeros-frontend-{version}.cdx.json",
        "rust": f"careeros-rust-{version}.cdx.json",
    }


def validate_release_date(value: str) -> str:
    if not RELEASE_DATE_PATTERN.fullmatch(value):
        raise RuntimeError(f"Release date must use YYYY-MM-DD: {value}")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise RuntimeError(f"Release date is not valid: {value}") from error
    return value


def _json_file(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Release evidence is not valid JSON: {path.name}") from error


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _ensure_empty_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise RuntimeError(f"Release output directory must be empty: {path}")


def inventory_directory(directory: Path, *, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    excluded = exclude or set()
    entries = sorted(directory.iterdir(), key=lambda path: path.name.casefold())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise RuntimeError(f"Release directory may contain regular files only: {directory}")
    names = [path.name for path in entries]
    reject_casefold_collisions(names)
    return [file_record(path) for path in entries if path.name not in excluded]


def _validate_cyclonedx(path: Path) -> dict[str, Any]:
    value = _json_file(path)
    if not isinstance(value, dict) or value.get("bomFormat") != "CycloneDX":
        raise RuntimeError(f"Release SBOM is not CycloneDX JSON: {path.name}")
    if not isinstance(value.get("specVersion"), str) or not isinstance(value.get("components"), list):
        raise RuntimeError(f"Release SBOM is missing its versioned component graph: {path.name}")
    return value


def validate_evidence_directory(directory: Path) -> list[dict[str, Any]]:
    if not directory.is_dir():
        raise RuntimeError(f"Supply-chain evidence directory does not exist: {directory}")
    entries = sorted(directory.iterdir(), key=lambda path: path.name)
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise RuntimeError("Supply-chain evidence may contain regular files only")
    names = [path.name for path in entries]
    if names != sorted(EVIDENCE_FILES):
        raise RuntimeError(f"Supply-chain evidence has missing or unexpected files: {names}")
    if any(path.stat().st_size == 0 for path in entries):
        raise RuntimeError("Supply-chain evidence contains an empty file")
    if any(path.stat().st_size > MAX_EVIDENCE_FILE_SIZE for path in entries):
        raise RuntimeError("Supply-chain evidence contains an oversized file")
    for name in ("backend-sbom.cdx.json", "frontend-sbom.cdx.json", "rust-sbom.cdx.json"):
        _validate_cyclonedx(directory / name)
    for name in (
        "backend-licenses.json",
        "frontend-audit.json",
        "frontend-licenses.json",
        "python-dev-audit.json",
        "python-production-audit.json",
        "python-tooling-audit.json",
        "rust-audit.json",
        "security-exceptions.json",
    ):
        _json_file(directory / name)
    return [file_record(path) for path in entries]


def create_deterministic_evidence_archive(evidence: Path, destination: Path) -> list[dict[str, Any]]:
    records = validate_evidence_directory(evidence)
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                for name in EVIDENCE_FILES:
                    payload = (evidence / name).read_bytes()
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    info.mode = 0o644
                    info.mtime = 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    archive.addfile(info, io.BytesIO(payload))
    return records


def _archive_records(path: Path) -> list[dict[str, Any]]:
    if path.stat().st_size > MAX_EVIDENCE_ARCHIVE_SIZE:
        raise RuntimeError("Supply-chain evidence archive is oversized")
    records: list[dict[str, Any]] = []
    with tarfile.open(path, mode="r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if names != list(EVIDENCE_FILES):
            raise RuntimeError(f"Evidence archive has missing or unexpected members: {names}")
        for member in members:
            validate_portable_name(member.name)
            if not member.isfile() or member.issym() or member.islnk():
                raise RuntimeError(f"Evidence archive member is not a regular file: {member.name}")
            if member.size > MAX_EVIDENCE_FILE_SIZE:
                raise RuntimeError(f"Evidence archive member is oversized: {member.name}")
            if (
                member.mode != 0o644
                or member.mtime != 0
                or member.uid != 0
                or member.gid != 0
                or member.uname
                or member.gname
            ):
                raise RuntimeError(f"Evidence archive metadata is not deterministic: {member.name}")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"Cannot read evidence archive member: {member.name}")
            payload = extracted.read()
            records.append(
                {
                    "name": member.name,
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
    return records


def expected_public_names(version: str) -> list[str]:
    names: list[str] = []
    for target, spec in TARGETS.items():
        names.extend(canonical_package_name(version, spec, package) for package in spec.packages)
        names.append(target_checksum_name(target))
    names.extend(sbom_asset_names(version).values())
    names.extend((EVIDENCE_ARCHIVE, RELEASE_MANIFEST, GLOBAL_CHECKSUMS))
    reject_casefold_collisions(names)
    return sorted(names, key=str.casefold)


def _native_candidates(native_root: Path, version: str, source_commit: str) -> list[dict[str, Any]]:
    manifests = sorted(native_root.rglob("candidate-*.json"), key=lambda path: path.name)
    if len(manifests) != len(TARGETS):
        raise RuntimeError(f"Expected {len(TARGETS)} native target manifests, found {len(manifests)}")
    candidates: dict[str, dict[str, Any]] = {}
    for manifest_path in manifests:
        raw = _json_file(manifest_path)
        if not isinstance(raw, dict) or not isinstance(raw.get("target"), str):
            raise RuntimeError(f"Invalid native target manifest: {manifest_path}")
        target = raw["target"]
        if target in candidates:
            raise RuntimeError(f"Duplicate native target manifest: {target}")
        candidates[target] = validate_target_candidate(
            manifest_path.parent, target=target, version=version, source_commit=source_commit
        )
    if set(candidates) != set(TARGETS):
        raise RuntimeError(f"Native target set is incomplete: {sorted(candidates)}")
    return [candidates[target] for target in TARGETS]


def validate_native_subject_checksums(
    path: Path, *, records: list[dict[str, Any]]
) -> list[dict[str, str]]:
    parsed = parse_checksum_text(path.read_text(encoding="utf-8"))
    expected = sorted(
        ({"sha256": str(record["sha256"]), "name": str(record["name"])} for record in records),
        key=lambda record: record["name"].casefold(),
    )
    if parsed != expected:
        raise RuntimeError("Native subject checksums do not match the release candidate")
    return parsed


def assemble_release_bundle(
    *,
    native_root: Path,
    evidence_root: Path,
    output: Path,
    native_checksums: Path,
    version: str,
    source_commit: str,
    release_date: str,
    license_path: Path,
) -> dict[str, Any]:
    version = validate_stable_version(version)
    source_commit = validate_source_commit(source_commit)
    release_date = validate_release_date(release_date)
    _ensure_empty_directory(output)
    if license_path.name != "LICENSE" or license_path.is_symlink() or not license_path.is_file():
        raise RuntimeError("The approved repository LICENSE file is required")
    candidates = _native_candidates(native_root, version, source_commit)
    targets: list[dict[str, Any]] = []
    native_records: list[dict[str, Any]] = []
    for candidate in candidates:
        target = str(candidate["target"])
        source = next(native_root.rglob(f"candidate-{target}.json")).parent
        target_records: list[dict[str, Any]] = []
        for artifact in candidate["artifacts"]:
            destination = output / str(artifact["name"])
            shutil.copy2(source / destination.name, destination)
            record = file_record(destination, artifact_type=str(artifact["type"]))
            target_records.append(record)
            native_records.append(record)
        checksum_name = target_checksum_name(target)
        shutil.copy2(source / checksum_name, output / checksum_name)
        targets.append(
            {
                "target": target,
                "platform": candidate["platform"],
                "architecture": candidate["architecture"],
                "artifacts": target_records,
                "checksum": file_record(output / checksum_name),
            }
        )
    evidence_records = create_deterministic_evidence_archive(evidence_root, output / EVIDENCE_ARCHIVE)
    sboms: dict[str, dict[str, Any]] = {}
    for component, public_name in sbom_asset_names(version).items():
        source_name = f"{component}-sbom.cdx.json"
        shutil.copy2(evidence_root / source_name, output / public_name)
        sboms[component] = file_record(output / public_name)
    manifest = {
        "schemaVersion": RELEASE_SCHEMA_VERSION,
        "project": PROJECT,
        "version": version,
        "tag": f"v{version}",
        "releaseDate": release_date,
        "sourceCommit": source_commit,
        "signedPackages": False,
        "license": {"spdx": "MIT", **file_record(license_path)},
        "targets": targets,
        "sboms": sboms,
        "evidenceArchive": file_record(output / EVIDENCE_ARCHIVE),
        "evidenceFiles": evidence_records,
    }
    _write_json(output / RELEASE_MANIFEST, manifest)
    inventory = inventory_directory(output)
    (output / GLOBAL_CHECKSUMS).write_text(checksum_text(inventory), encoding="utf-8")
    if native_checksums.exists() or native_checksums.is_symlink():
        raise RuntimeError("Native subject checksum output must not already exist")
    native_checksums.parent.mkdir(parents=True, exist_ok=True)
    native_checksums.write_text(checksum_text(native_records), encoding="utf-8")
    validate_native_subject_checksums(native_checksums, records=native_records)
    validate_release_bundle(
        output,
        version=version,
        source_commit=source_commit,
        release_date=release_date,
        license_path=license_path,
    )
    return manifest


def validate_release_bundle(
    directory: Path,
    *,
    version: str,
    source_commit: str,
    release_date: str,
    license_path: Path,
) -> dict[str, Any]:
    version = validate_stable_version(version)
    source_commit = validate_source_commit(source_commit)
    release_date = validate_release_date(release_date)
    if license_path.name != "LICENSE" or license_path.is_symlink() or not license_path.is_file():
        raise RuntimeError("The approved repository LICENSE file is required")
    actual_names = [record["name"] for record in inventory_directory(directory)]
    if actual_names != expected_public_names(version):
        raise RuntimeError(f"Release bundle has missing or unexpected files: {actual_names}")
    inventory = inventory_directory(directory, exclude={GLOBAL_CHECKSUMS})
    parsed = parse_checksum_text((directory / GLOBAL_CHECKSUMS).read_text(encoding="utf-8"))
    expected_checksums = [
        {"sha256": str(record["sha256"]), "name": str(record["name"])} for record in inventory
    ]
    if parsed != expected_checksums:
        raise RuntimeError("SHA256SUMS does not match the exact public asset inventory")
    manifest = _json_file(directory / RELEASE_MANIFEST)
    if not isinstance(manifest, dict):
        raise RuntimeError("Release manifest must be a JSON object")
    expected_header = {
        "schemaVersion": RELEASE_SCHEMA_VERSION,
        "project": PROJECT,
        "version": version,
        "tag": f"v{version}",
        "releaseDate": release_date,
        "sourceCommit": source_commit,
        "signedPackages": False,
        "license": {"spdx": "MIT", **file_record(license_path)},
    }
    for key, value in expected_header.items():
        if manifest.get(key) != value:
            raise RuntimeError(f"Release manifest has unexpected {key}: {manifest.get(key)!r}")
    targets = manifest.get("targets")
    if not isinstance(targets, list) or [item.get("target") for item in targets] != list(TARGETS):
        raise RuntimeError("Release manifest target order or coverage is incorrect")
    native_names: list[str] = []
    for item in targets:
        target = str(item["target"])
        spec = TARGETS[target]
        if item.get("platform") != spec.platform or item.get("architecture") != spec.architecture:
            raise RuntimeError(f"Release manifest platform metadata is incorrect for {target}")
        records = [
            file_record(
                directory / canonical_package_name(version, spec, package),
                artifact_type=package.name,
            )
            for package in spec.packages
        ]
        if item.get("artifacts") != records:
            raise RuntimeError(f"Release manifest package bytes are incorrect for {target}")
        native_names.extend(str(record["name"]) for record in records)
        checksum_name = target_checksum_name(target)
        if item.get("checksum") != file_record(directory / checksum_name):
            raise RuntimeError(f"Release manifest checksum asset is incorrect for {target}")
        target_lines = parse_checksum_text((directory / checksum_name).read_text(encoding="utf-8"))
        expected_lines = [{"sha256": record["sha256"], "name": record["name"]} for record in records]
        if target_lines != sorted(expected_lines, key=lambda record: str(record["name"]).casefold()):
            raise RuntimeError(f"Target checksum inventory is incorrect for {target}")
    reject_casefold_collisions(native_names)
    sboms = manifest.get("sboms")
    if not isinstance(sboms, dict):
        raise RuntimeError("Release manifest is missing SBOM records")
    for component, name in sbom_asset_names(version).items():
        _validate_cyclonedx(directory / name)
        if sboms.get(component) != file_record(directory / name):
            raise RuntimeError(f"Release manifest SBOM record is incorrect for {component}")
    evidence_records = _archive_records(directory / EVIDENCE_ARCHIVE)
    if manifest.get("evidenceFiles") != evidence_records:
        raise RuntimeError("Release manifest evidence members do not match the deterministic archive")
    if manifest.get("evidenceArchive") != file_record(directory / EVIDENCE_ARCHIVE):
        raise RuntimeError("Release manifest evidence archive digest is incorrect")
    by_name = {record["name"]: record for record in evidence_records}
    for component, name in sbom_asset_names(version).items():
        source_record = by_name[f"{component}-sbom.cdx.json"]
        if source_record["sha256"] != sha256_file(directory / name):
            raise RuntimeError(f"Published {component} SBOM differs from supply-chain evidence")
    return manifest
