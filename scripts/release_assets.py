"""Canonical native release assets and per-target candidate contracts."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT = "CareerOS Local"
TARGET_SCHEMA_VERSION = 1
SOURCE_COMMIT = re.compile(r"^[0-9a-f]{40}$")
STABLE_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
PORTABLE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]*)$")


@dataclass(frozen=True)
class PackageKind:
    name: str
    suffix: str


@dataclass(frozen=True)
class TargetSpec:
    platform: str
    architecture: str
    packages: tuple[PackageKind, ...]


TARGETS: dict[str, TargetSpec] = {
    "x86_64-pc-windows-msvc": TargetSpec(
        "windows", "x64", (PackageKind("nsis", ".exe"), PackageKind("msi", ".msi"))
    ),
    "aarch64-pc-windows-msvc": TargetSpec(
        "windows", "arm64", (PackageKind("nsis", ".exe"), PackageKind("msi", ".msi"))
    ),
    "x86_64-apple-darwin": TargetSpec("macos", "x64", (PackageKind("dmg", ".dmg"),)),
    "aarch64-apple-darwin": TargetSpec("macos", "arm64", (PackageKind("dmg", ".dmg"),)),
    "x86_64-unknown-linux-gnu": TargetSpec(
        "linux", "x64", (PackageKind("appimage", ".AppImage"), PackageKind("deb", ".deb"))
    ),
    "aarch64-unknown-linux-gnu": TargetSpec(
        "linux", "arm64", (PackageKind("appimage", ".AppImage"), PackageKind("deb", ".deb"))
    ),
}


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def validate_source_commit(value: str) -> str:
    if not SOURCE_COMMIT.fullmatch(value):
        raise RuntimeError("Source commit must be a lowercase 40-character SHA-1")
    return value


def validate_stable_version(value: str) -> str:
    if not STABLE_VERSION.fullmatch(value):
        raise RuntimeError(f"Release version must be stable SemVer without metadata: {value}")
    return value


def validate_portable_name(name: str) -> str:
    if not PORTABLE_NAME.fullmatch(name) or name in {".", ".."}:
        raise RuntimeError(f"Release asset name is not portable: {name!r}")
    return name


def reject_casefold_collisions(names: list[str]) -> None:
    folded: dict[str, str] = {}
    for name in names:
        validate_portable_name(name)
        key = name.casefold()
        if key in folded:
            raise RuntimeError(f"Case-insensitive release asset collision: {folded[key]} / {name}")
        folded[key] = name


def canonical_package_name(version: str, spec: TargetSpec, package: PackageKind) -> str:
    validate_stable_version(version)
    qualifier = "-setup" if package.name == "nsis" else ""
    return validate_portable_name(
        f"CareerOS-Local_{version}_{spec.platform}-{spec.architecture}{qualifier}{package.suffix}"
    )


def target_manifest_name(target: str) -> str:
    if target not in TARGETS:
        raise RuntimeError(f"Unsupported release target: {target}")
    return f"candidate-{target}.json"


def target_checksum_name(target: str) -> str:
    if target not in TARGETS:
        raise RuntimeError(f"Unsupported release target: {target}")
    return f"checksums-{target}.sha256"


def file_record(path: Path, *, artifact_type: str | None = None) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"Release asset must be a regular file: {path}")
    validate_portable_name(path.name)
    record: dict[str, Any] = {
        "name": path.name,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if artifact_type is not None:
        record["type"] = artifact_type
    return record


def checksum_text(records: list[dict[str, Any]]) -> str:
    ordered = sorted(records, key=lambda record: str(record["name"]).casefold())
    return "".join(f"{record['sha256']}  {record['name']}\n" for record in ordered)


def parse_checksum_text(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    if not lines:
        raise RuntimeError("SHA-256 inventory is empty")
    records: list[dict[str, str]] = []
    for line in lines:
        match = CHECKSUM_LINE.fullmatch(line)
        if match is None:
            raise RuntimeError(f"Malformed SHA-256 inventory line: {line!r}")
        records.append({"sha256": match.group(1), "name": match.group(2)})
    reject_casefold_collisions([record["name"] for record in records])
    if records != sorted(records, key=lambda record: record["name"].casefold()):
        raise RuntimeError("SHA-256 inventory is not sorted deterministically")
    return records


def _empty_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise RuntimeError(f"Release output directory must be empty: {path}")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _discover_packages(bundle_root: Path, spec: TargetSpec) -> dict[str, Path]:
    if not bundle_root.is_dir():
        raise RuntimeError(f"Native bundle root does not exist: {bundle_root}")
    discovered: dict[str, Path] = {}
    suffixes = {package.suffix.casefold(): package for package in spec.packages}
    for path in sorted(bundle_root.rglob("*"), key=lambda value: str(value).casefold()):
        if not path.is_file():
            continue
        package = suffixes.get(path.suffix.casefold())
        if package is None:
            continue
        if path.is_symlink():
            raise RuntimeError(f"Native package is a symbolic link: {path}")
        if package.name in discovered:
            raise RuntimeError(f"Native bundle contains duplicate {package.name} packages")
        discovered[package.name] = path
    expected = {package.name for package in spec.packages}
    if set(discovered) != expected:
        raise RuntimeError(
            f"Native bundle package kinds disagree: expected={sorted(expected)}, actual={sorted(discovered)}"
        )
    return discovered


def stage_target_candidate(
    *, bundle_root: Path, output: Path, target: str, version: str, source_commit: str
) -> dict[str, Any]:
    version = validate_stable_version(version)
    source_commit = validate_source_commit(source_commit)
    try:
        spec = TARGETS[target]
    except KeyError as error:
        raise RuntimeError(f"Unsupported release target: {target}") from error
    _empty_directory(output)
    discovered = _discover_packages(bundle_root, spec)
    artifacts: list[dict[str, Any]] = []
    for package in spec.packages:
        destination = output / canonical_package_name(version, spec, package)
        shutil.copy2(discovered[package.name], destination)
        artifacts.append(file_record(destination, artifact_type=package.name))
    reject_casefold_collisions([str(record["name"]) for record in artifacts])
    (output / target_checksum_name(target)).write_text(checksum_text(artifacts), encoding="utf-8")
    manifest = {
        "schemaVersion": TARGET_SCHEMA_VERSION,
        "project": PROJECT,
        "version": version,
        "tag": f"v{version}",
        "sourceCommit": source_commit,
        "target": target,
        "platform": spec.platform,
        "architecture": spec.architecture,
        "artifacts": artifacts,
        "checksum": target_checksum_name(target),
    }
    _write_json(output / target_manifest_name(target), manifest)
    validate_target_candidate(output, target=target, version=version, source_commit=source_commit)
    return manifest


def validate_target_candidate(
    directory: Path, *, target: str, version: str, source_commit: str
) -> dict[str, Any]:
    spec = TARGETS.get(target)
    if spec is None:
        raise RuntimeError(f"Unsupported release target: {target}")
    manifest_path = directory / target_manifest_name(target)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise RuntimeError("Target candidate manifest must be a JSON object")
    expected_names = [canonical_package_name(version, spec, package) for package in spec.packages]
    expected_files = sorted(expected_names + [target_manifest_name(target), target_checksum_name(target)])
    entries = sorted(directory.iterdir(), key=lambda path: path.name)
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise RuntimeError(f"Target candidate contains a non-regular file: {directory}")
    actual_files = [path.name for path in entries]
    reject_casefold_collisions(actual_files)
    if actual_files != expected_files:
        raise RuntimeError(f"Target candidate has missing or unexpected files: {actual_files}")
    expected_header = {
        "schemaVersion": TARGET_SCHEMA_VERSION,
        "project": PROJECT,
        "version": validate_stable_version(version),
        "tag": f"v{version}",
        "sourceCommit": validate_source_commit(source_commit),
        "target": target,
        "platform": spec.platform,
        "architecture": spec.architecture,
        "checksum": target_checksum_name(target),
    }
    for key, value in expected_header.items():
        if manifest.get(key) != value:
            raise RuntimeError(f"Target candidate manifest has unexpected {key}: {manifest.get(key)!r}")
    expected_records = [
        file_record(
            directory / canonical_package_name(version, spec, package),
            artifact_type=package.name,
        )
        for package in spec.packages
    ]
    if manifest.get("artifacts") != expected_records:
        raise RuntimeError("Target candidate manifest does not match package bytes")
    parsed = parse_checksum_text((directory / target_checksum_name(target)).read_text(encoding="utf-8"))
    checksum_records = [{"sha256": item["sha256"], "name": item["name"]} for item in expected_records]
    if parsed != sorted(checksum_records, key=lambda record: record["name"].casefold()):
        raise RuntimeError("Target checksum inventory does not match canonical package bytes")
    return manifest
