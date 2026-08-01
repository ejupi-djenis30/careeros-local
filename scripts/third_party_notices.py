"""Build and verify the license notices shipped with every CareerOS distribution."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NOTICE_NAME = "THIRD_PARTY_NOTICES.txt"
NOTICE_PATH = ROOT / NOTICE_NAME
NOTICE_SCHEMA = 1
MAX_NOTICE_BYTES = 4 * 1024 * 1024
APPROVED_NOTICE_SHA256 = "6a4c1922d2ba8bf3128ce23cc7f6294af4b9dc679cc2573a7f3bbe73df2378b3"

MANIFEST_START = "----- BEGIN CAREEROS THIRD-PARTY MANIFEST -----"
MANIFEST_END = "----- END CAREEROS THIRD-PARTY MANIFEST -----"
TEXT_START = "----- BEGIN THIRD-PARTY TEXT {identifier} -----"
TEXT_END = "----- END THIRD-PARTY TEXT {identifier} -----"
LEGAL_FILE_PATTERN = re.compile(
    r"^(?:LICENSE|LICENCE|COPYING|NOTICE|COPYRIGHT)(?:[._-].*)?$",
    re.IGNORECASE,
)
REQUIREMENT_PATTERN = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s\\;]+)")
CANONICAL_NAME_PATTERN = re.compile(r"[-_.]+")

SOURCE_FILES = (
    ".python-version",
    "frontend/package-lock.json",
    "frontend/src-tauri/Cargo.lock",
    "requirements.lock",
    "requirements-tooling.lock",
)

RUST_LICENSE_SELECTIONS: dict[str, tuple[str, ...]] = {
    "MIT": ("MIT",),
    "Apache-2.0": ("Apache-2.0",),
    "Unicode-3.0": ("Unicode-3.0",),
    "MPL-2.0": ("MPL-2.0",),
    "BSD-3-Clause": ("BSD-3-Clause",),
    "Zlib": ("Zlib",),
    "ISC": ("ISC",),
    "MIT OR Apache-2.0": ("MIT",),
    "Apache-2.0 OR MIT": ("MIT",),
    "MIT/Apache-2.0": ("MIT",),
    "Apache-2.0/MIT": ("MIT",),
    "Apache-2.0 / MIT": ("MIT",),
    "Zlib OR Apache-2.0 OR MIT": ("MIT",),
    "MIT OR Apache-2.0 OR Zlib": ("MIT",),
    "MIT OR Zlib OR Apache-2.0": ("MIT",),
    "Unlicense OR MIT": ("MIT",),
    "Unlicense/MIT": ("MIT",),
    "BSD-2-Clause OR Apache-2.0 OR MIT": ("MIT",),
    "BSD-3-Clause OR MIT OR Apache-2.0": ("MIT",),
    "BSD-3-Clause/MIT": ("MIT",),
    "MIT OR Apache-2.0 OR LGPL-2.1-or-later": ("MIT",),
    "CC0-1.0 OR MIT-0 OR Apache-2.0": ("Apache-2.0",),
    "0BSD OR MIT OR Apache-2.0": ("MIT",),
    "Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT": ("MIT",),
    "Apache-2.0 WITH LLVM-exception": ("Apache-2.0", "LLVM-exception"),
    "BSD-3-Clause AND MIT": ("BSD-3-Clause", "MIT"),
    "Apache-2.0 AND MIT": ("Apache-2.0", "MIT"),
    "(MIT OR Apache-2.0) AND Unicode-3.0": ("MIT", "Unicode-3.0"),
    "(Apache-2.0 OR MIT) AND BSD-3-Clause": ("MIT", "BSD-3-Clause"),
}


@dataclass(frozen=True)
class LegalText:
    source: str
    text: str


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_name(value: str) -> str:
    return CANONICAL_NAME_PATTERN.sub("-", value).casefold()


def _normalized_text(payload: bytes, *, source: str) -> str:
    if b"\0" in payload:
        raise RuntimeError(f"Third-party legal text contains a NUL byte: {source}")
    try:
        value = payload.decode("utf-8")
    except UnicodeDecodeError:
        try:
            value = payload.decode("latin-1")
        except UnicodeDecodeError as error:
            raise RuntimeError(f"Third-party legal text is not decodable: {source}") from error
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not value:
        raise RuntimeError(f"Third-party legal text is empty: {source}")
    if len(value.encode("utf-8")) > 512 * 1024:
        raise RuntimeError(f"Third-party legal text is unexpectedly large: {source}")
    return value + "\n"


def _legal_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and not path.is_symlink() and LEGAL_FILE_PATTERN.fullmatch(path.name)
        ),
        key=lambda path: path.name.casefold(),
    )


def _lock_hashes(root: Path = ROOT) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in SOURCE_FILES:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"Third-party notice source is missing or unsafe: {relative}")
        result[relative] = _sha256(path.read_bytes())
    return result


def _node_inventory(root: Path = ROOT) -> list[dict[str, str]]:
    lockfile = json.loads((root / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    if lockfile.get("lockfileVersion") != 3 or not isinstance(lockfile.get("packages"), dict):
        raise RuntimeError("Expected frontend/package-lock.json lockfileVersion 3")
    packages: dict[tuple[str, str], dict[str, str]] = {}
    for path, metadata in lockfile["packages"].items():
        if not path.startswith("node_modules/") or metadata.get("dev") is True:
            continue
        name = metadata.get("name") or path.split("/node_modules/")[-1].removeprefix(
            "node_modules/"
        )
        version = metadata.get("version")
        license_expression = metadata.get("license")
        if not all(
            isinstance(value, str) and value for value in (name, version, license_expression)
        ):
            raise RuntimeError(f"Incomplete production npm metadata: {path}")
        packages[(name, version)] = {
            "ecosystem": "frontend",
            "name": name,
            "version": version,
            "license": license_expression,
            "source": path,
        }
    if not packages:
        raise RuntimeError("No frontend production packages were found")
    return [
        packages[key] for key in sorted(packages, key=lambda item: (item[0].casefold(), item[1]))
    ]


def _locked_python_versions(path: Path) -> dict[str, str]:
    packages: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = REQUIREMENT_PATTERN.match(line)
        if match is None:
            continue
        name = _canonical_name(match.group("name"))
        version = match.group("version")
        previous = packages.setdefault(name, version)
        if previous != version:
            raise RuntimeError(f"Python lock contains conflicting versions for {name}")
    if not packages:
        raise RuntimeError(f"No locked Python packages were found in {path.name}")
    return packages


def _python_inventory(root: Path = ROOT) -> list[dict[str, str]]:
    return [
        {
            "ecosystem": "python",
            "name": name,
            "version": version,
            "license": "",
            "source": "requirements.lock",
        }
        for name, version in sorted(_locked_python_versions(root / "requirements.lock").items())
    ]


def _cargo_inventory(root: Path = ROOT) -> list[dict[str, str]]:
    with (root / "frontend" / "src-tauri" / "Cargo.lock").open("rb") as source:
        lockfile = tomllib.load(source)
    packages: list[dict[str, str]] = []
    for package in lockfile.get("package", []):
        name = package.get("name")
        version = package.get("version")
        source = package.get("source", "workspace")
        if name == "careeros-local" and source == "workspace":
            continue
        if not all(isinstance(value, str) and value for value in (name, version, source)):
            raise RuntimeError("Cargo.lock contains incomplete package metadata")
        packages.append(
            {
                "ecosystem": "rust",
                "name": name,
                "version": version,
                "license": "",
                "source": source,
            }
        )
    packages.sort(key=lambda item: (item["name"].casefold(), item["version"], item["source"]))
    if not packages:
        raise RuntimeError("No Rust dependency packages were found")
    return packages


def _runtime_inventory(root: Path = ROOT) -> list[dict[str, str]]:
    python_version = (root / ".python-version").read_text(encoding="utf-8").strip()
    tooling = _locked_python_versions(root / "requirements-tooling.lock")
    pyinstaller_version = tooling.get("pyinstaller")
    if not python_version or not pyinstaller_version:
        raise RuntimeError("Pinned CPython and PyInstaller versions are required")
    return [
        {
            "ecosystem": "runtime",
            "name": "cpython",
            "version": python_version,
            "license": "PSF-2.0",
            "source": ".python-version",
        },
        {
            "ecosystem": "runtime",
            "name": "pyinstaller",
            "version": pyinstaller_version,
            "license": "GPL-2.0-or-later WITH Bootloader-exception",
            "source": "requirements-tooling.lock",
        },
    ]


def expected_inventory(root: Path = ROOT) -> list[dict[str, str]]:
    inventory = [
        *_node_inventory(root),
        *_python_inventory(root),
        *_cargo_inventory(root),
        *_runtime_inventory(root),
    ]
    return sorted(
        inventory,
        key=lambda item: (
            item["ecosystem"],
            item["name"].casefold(),
            item["version"],
            item["source"],
        ),
    )


def _metadata_by_python_package() -> dict[tuple[str, str], importlib.metadata.Distribution]:
    distributions: dict[tuple[str, str], importlib.metadata.Distribution] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        version = distribution.version
        if name and version:
            distributions[(_canonical_name(name), version)] = distribution
    return distributions


def _python_legal_texts(
    package: dict[str, str],
    distributions: dict[tuple[str, str], importlib.metadata.Distribution],
) -> tuple[str, list[LegalText]]:
    key = (package["name"], package["version"])
    distribution = distributions.get(key)
    if distribution is None:
        raise RuntimeError(
            f"Locked Python distribution is not installed: {package['name']}@{package['version']}"
        )
    metadata = distribution.metadata
    license_expression = (
        metadata.get("License-Expression")
        or metadata.get("License")
        or "License files supplied by the distribution"
    ).strip()
    declared_files = metadata.get_all("License-File") or []
    paths: list[Path] = []
    for relative in declared_files:
        candidate = Path(str(distribution.locate_file(relative)))
        if candidate.is_file() and not candidate.is_symlink():
            paths.append(candidate)
    if not paths:
        for entry in distribution.files or []:
            if LEGAL_FILE_PATTERN.fullmatch(Path(entry).name):
                candidate = Path(str(distribution.locate_file(entry)))
                if candidate.is_file() and not candidate.is_symlink():
                    paths.append(candidate)
    unique_paths = sorted(set(paths), key=lambda path: path.as_posix().casefold())
    texts = [
        LegalText(
            source=f"python:{package['name']}@{package['version']}/{path.name}",
            text=_normalized_text(path.read_bytes(), source=str(path)),
        )
        for path in unique_paths
    ]
    if not texts and "\n" in license_expression:
        texts.append(
            LegalText(
                source=f"python:{package['name']}@{package['version']}/METADATA-License",
                text=_normalized_text(
                    license_expression.encode("utf-8"),
                    source=f"{package['name']} METADATA License",
                ),
            )
        )
    if not texts:
        raise RuntimeError(
            f"Locked Python distribution has no distributable legal text: "
            f"{package['name']}@{package['version']}"
        )
    return license_expression.splitlines()[0], texts


def _node_legal_texts(root: Path, package: dict[str, str]) -> list[LegalText]:
    directory = root / "frontend" / package["source"]
    paths = _legal_files(directory)
    if not paths:
        raise RuntimeError(
            f"Frontend production package has no distributable legal text: "
            f"{package['name']}@{package['version']}"
        )
    return [
        LegalText(
            source=f"frontend:{package['name']}@{package['version']}/{path.name}",
            text=_normalized_text(path.read_bytes(), source=str(path)),
        )
        for path in paths
    ]


def selected_rust_licenses(expression: str) -> tuple[str, ...]:
    try:
        return RUST_LICENSE_SELECTIONS[expression]
    except KeyError as error:
        raise RuntimeError(f"Unreviewed Rust license expression: {expression}") from error


def _cargo_metadata(root: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "cargo",
            "metadata",
            "--locked",
            "--format-version",
            "1",
            "--manifest-path",
            str(root / "frontend" / "src-tauri" / "Cargo.toml"),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise RuntimeError("Cargo metadata must be a JSON object")
    return value


def _cargo_packages(metadata: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    packages: dict[tuple[str, str, str], dict[str, Any]] = {}
    for package in metadata["packages"]:
        source = package.get("source") or "workspace"
        if package["name"] == "careeros-local" and source == "workspace":
            continue
        packages[(package["name"], package["version"], source)] = package
    return packages


def _canonical_rust_texts(
    packages: dict[tuple[str, str, str], dict[str, Any]],
) -> dict[str, LegalText]:
    result: dict[str, LegalText] = {}
    for identifier in (
        "Apache-2.0",
        "BSD-3-Clause",
        "ISC",
        "MIT",
        "MPL-2.0",
        "Unicode-3.0",
        "Zlib",
        "Apache-2.0 WITH LLVM-exception",
    ):
        candidates = sorted(
            (package for package in packages.values() if package.get("license") == identifier),
            key=lambda package: (package["name"].casefold(), package["version"]),
        )
        for package in candidates:
            directory = Path(package["manifest_path"]).parent
            paths = _legal_files(directory)
            preferred = sorted(
                paths,
                key=lambda path: (
                    path.name.casefold() in {"copyright", "notice"},
                    path.name.casefold(),
                ),
            )
            if not preferred:
                continue
            path = preferred[0]
            result[identifier] = LegalText(
                source=f"rust-canonical:{identifier}/{package['name']}@{package['version']}/{path.name}",
                text=_normalized_text(path.read_bytes(), source=str(path)),
            )
            break
        if identifier not in result:
            raise RuntimeError(f"No canonical Rust legal text is available for {identifier}")
    result["LLVM-exception"] = result["Apache-2.0 WITH LLVM-exception"]
    return result


def _runtime_legal_texts(
    package: dict[str, str],
    distributions: dict[tuple[str, str], importlib.metadata.Distribution],
) -> list[LegalText]:
    if package["name"] == "cpython":
        interpreter_version = platform.python_version()
        if interpreter_version != package["version"]:
            raise RuntimeError(
                "The notice generator must run with pinned CPython "
                f"{package['version']}, not {interpreter_version}"
            )
        candidates = sorted(Path(sys.base_prefix).glob("LICENSE*"), key=lambda path: path.name)
        if len(candidates) != 1 or not candidates[0].is_file():
            raise RuntimeError("The CPython runtime license is unavailable")
        return [
            LegalText(
                source=f"runtime:cpython@{package['version']}/{candidates[0].name}",
                text=_normalized_text(candidates[0].read_bytes(), source=str(candidates[0])),
            )
        ]
    _license, texts = _python_legal_texts(package, distributions)
    return [
        LegalText(
            source=text.source.replace("python:", "runtime:", 1),
            text=text.text,
        )
        for text in texts
    ]


def build_notice(root: Path = ROOT) -> str:
    inventory = expected_inventory(root)
    distributions = _metadata_by_python_package()
    cargo_packages = _cargo_packages(_cargo_metadata(root))
    canonical_rust = _canonical_rust_texts(cargo_packages)
    text_sources: dict[str, set[str]] = defaultdict(set)
    text_values: dict[str, str] = {}
    components: list[dict[str, Any]] = []

    def register(text: LegalText) -> str:
        identifier = _sha256(text.text.encode("utf-8"))
        text_values[identifier] = text.text
        text_sources[identifier].add(text.source)
        return identifier

    for package in inventory:
        package = dict(package)
        legal_texts: list[LegalText]
        selected: tuple[str, ...] = ()
        if package["ecosystem"] == "frontend":
            legal_texts = _node_legal_texts(root, package)
        elif package["ecosystem"] == "python":
            package["license"], legal_texts = _python_legal_texts(package, distributions)
        elif package["ecosystem"] == "runtime":
            legal_texts = _runtime_legal_texts(package, distributions)
        else:
            key = (package["name"], package["version"], package["source"])
            metadata = cargo_packages.get(key)
            if metadata is None:
                raise RuntimeError(
                    f"Cargo metadata is missing locked package {package['name']}@{package['version']}"
                )
            expression = metadata.get("license")
            if not isinstance(expression, str) or not expression:
                raise RuntimeError(
                    f"Rust package has no license expression: {package['name']}@{package['version']}"
                )
            package["license"] = expression
            selected = selected_rust_licenses(expression)
            directory = Path(metadata["manifest_path"]).parent
            legal_texts = [
                LegalText(
                    source=f"rust:{package['name']}@{package['version']}/{path.name}",
                    text=_normalized_text(path.read_bytes(), source=str(path)),
                )
                for path in _legal_files(directory)
            ]
            legal_texts.extend(canonical_rust[identifier] for identifier in selected)
        identifiers = sorted({register(text) for text in legal_texts})
        if not identifiers:
            raise RuntimeError(
                f"Third-party component has no legal text: "
                f"{package['ecosystem']}:{package['name']}@{package['version']}"
            )
        components.append(
            {
                **package,
                "selectedLicenses": list(selected),
                "textIds": identifiers,
            }
        )

    manifest = {
        "schemaVersion": NOTICE_SCHEMA,
        "sourceLocks": _lock_hashes(root),
        "componentCounts": {
            ecosystem: sum(component["ecosystem"] == ecosystem for component in components)
            for ecosystem in ("frontend", "python", "runtime", "rust")
        },
        "components": components,
        "texts": [
            {
                "id": identifier,
                "sha256": identifier,
                "sources": sorted(text_sources[identifier], key=str.casefold),
            }
            for identifier in sorted(text_values)
        ],
    }
    parts = [
        "CAREEROS LOCAL THIRD-PARTY NOTICES\n",
        "\n",
        "This file contains copyright and license notices for third-party runtime\n",
        "components distributed with CareerOS Local. It is separate from LICENSE,\n",
        "which covers the CareerOS Local project itself.\n",
        "\n",
        f"{MANIFEST_START}\n",
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False),
        "\n",
        f"{MANIFEST_END}\n",
    ]
    for identifier in sorted(text_values):
        parts.extend(
            [
                "\n",
                f"{TEXT_START.format(identifier=identifier)}\n",
                text_values[identifier],
                f"{TEXT_END.format(identifier=identifier)}\n",
            ]
        )
    notice = "".join(parts)
    if len(notice.encode("utf-8")) > MAX_NOTICE_BYTES:
        raise RuntimeError("Generated third-party notice exceeds the distribution size limit")
    return notice


def _manifest_from_notice(notice: str) -> tuple[dict[str, Any], dict[str, str]]:
    if "\r" in notice:
        raise RuntimeError("Third-party notice must use canonical LF newlines")
    if not notice.startswith("CAREEROS LOCAL THIRD-PARTY NOTICES\n"):
        raise RuntimeError("Third-party notice has an invalid header")
    manifest_prefix = f"{MANIFEST_START}\n"
    manifest_suffix = f"\n{MANIFEST_END}\n"
    if notice.count(manifest_prefix) != 1 or notice.count(manifest_suffix) != 1:
        raise RuntimeError("Third-party notice must contain exactly one manifest")
    manifest_text = notice.split(manifest_prefix, 1)[1].split(manifest_suffix, 1)[0]
    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError as error:
        raise RuntimeError("Third-party notice manifest is invalid JSON") from error
    texts: dict[str, str] = {}
    text_records = manifest.get("texts")
    if not isinstance(text_records, list):
        raise RuntimeError("Third-party notice manifest has no text inventory")
    for record in text_records:
        identifier = record.get("id") if isinstance(record, dict) else None
        if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{64}", identifier):
            raise RuntimeError("Third-party notice contains an invalid text id")
        start = f"{TEXT_START.format(identifier=identifier)}\n"
        end = f"{TEXT_END.format(identifier=identifier)}\n"
        if notice.count(start) != 1 or notice.count(end) != 1:
            raise RuntimeError(f"Third-party notice text markers are invalid: {identifier}")
        payload = notice.split(start, 1)[1].split(end, 1)[0]
        if _sha256(payload.encode("utf-8")) != identifier or record.get("sha256") != identifier:
            raise RuntimeError(f"Third-party notice text digest is invalid: {identifier}")
        texts[identifier] = payload
    return manifest, texts


def verify_notice_bytes(
    payload: bytes,
    *,
    root: Path = ROOT,
    approved_sha256: str = APPROVED_NOTICE_SHA256,
) -> dict[str, Any]:
    if not payload or len(payload) > MAX_NOTICE_BYTES:
        raise RuntimeError("Third-party notice is empty or oversized")
    if approved_sha256 != "TO_BE_GENERATED" and _sha256(payload) != approved_sha256:
        raise RuntimeError("THIRD_PARTY_NOTICES.txt differs from the approved generated payload")
    try:
        notice = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeError("Third-party notice must be UTF-8") from error
    manifest, texts = _manifest_from_notice(notice)
    if manifest.get("schemaVersion") != NOTICE_SCHEMA:
        raise RuntimeError("Third-party notice schema is unsupported")
    if manifest.get("sourceLocks") != _lock_hashes(root):
        raise RuntimeError("Third-party notice is stale for the locked dependency sources")
    expected = expected_inventory(root)
    components = manifest.get("components")
    if not isinstance(components, list):
        raise RuntimeError("Third-party notice has no component inventory")
    actual_inventory = [
        {key: component.get(key) for key in ("ecosystem", "name", "version", "license", "source")}
        for component in components
    ]
    expected_keys = [
        (item["ecosystem"], item["name"], item["version"], item["source"]) for item in expected
    ]
    actual_keys = [
        (item["ecosystem"], item["name"], item["version"], item["source"])
        for item in actual_inventory
    ]
    if actual_keys != expected_keys:
        raise RuntimeError("Third-party notice component inventory is stale or incomplete")
    counts = {
        ecosystem: sum(item["ecosystem"] == ecosystem for item in actual_inventory)
        for ecosystem in ("frontend", "python", "runtime", "rust")
    }
    if manifest.get("componentCounts") != counts:
        raise RuntimeError("Third-party notice component counts are incorrect")
    referenced: set[str] = set()
    for component in components:
        if not isinstance(component.get("license"), str) or not component["license"]:
            raise RuntimeError("Third-party notice component has no license declaration")
        identifiers = component.get("textIds")
        if (
            not isinstance(identifiers, list)
            or not identifiers
            or any(identifier not in texts for identifier in identifiers)
        ):
            raise RuntimeError("Third-party notice component has missing legal text")
        referenced.update(identifiers)
    if referenced != set(texts):
        raise RuntimeError("Third-party notice contains orphaned or unreferenced legal text")
    return manifest


def verify_notice_file(path: Path = NOTICE_PATH, *, root: Path = ROOT) -> dict[str, Any]:
    if path.name != NOTICE_NAME or path.is_symlink() or not path.is_file():
        raise RuntimeError(f"Canonical {NOTICE_NAME} is missing or unsafe")
    return verify_notice_bytes(path.read_bytes(), root=root)


def find_packaged_notice(
    package_root: Path, *, source: Path = NOTICE_PATH, root: Path = ROOT
) -> tuple[Path, dict[str, Any]]:
    """Verify the canonical notice at a Tauri/container resource root."""
    if package_root.is_symlink() or not package_root.is_dir():
        raise RuntimeError(f"Extracted package root is missing or unsafe: {package_root}")
    source_payload = source.read_bytes()
    verify_notice_bytes(source_payload, root=root)
    notice_path = package_root / NOTICE_NAME
    if notice_path.is_symlink() or not notice_path.is_file():
        raise RuntimeError(f"Packaged {NOTICE_NAME} is missing or unsafe: {notice_path}")
    if notice_path.read_bytes() != source_payload:
        raise RuntimeError(f"Packaged {NOTICE_NAME} differs from the approved generated payload")
    matches: list[Path] = []
    pending = [package_root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            children = sorted(entries, key=lambda entry: entry.name.casefold(), reverse=True)
        for entry in children:
            path = Path(entry.path)
            if entry.name.casefold() == NOTICE_NAME.casefold():
                if entry.is_symlink():
                    raise RuntimeError(f"Packaged {NOTICE_NAME} alias is unsafe: {path}")
                if not entry.is_file(follow_symlinks=False):
                    raise RuntimeError(f"Packaged {NOTICE_NAME} alias is unsafe: {path}")
                matches.append(path)
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)
    matches.sort(key=lambda item: str(item).casefold())
    if matches != [notice_path]:
        raise RuntimeError(
            f"Expected exactly one approved {NOTICE_NAME} under {package_root}; "
            f"found {len(matches)}"
        )
    if notice_path.read_bytes() != source_payload:
        raise RuntimeError(f"Packaged {NOTICE_NAME} differs from the approved generated payload")
    return notice_path, verify_notice_bytes(source_payload, root=root)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--package-root", type=Path)
    arguments = parser.parse_args()
    if arguments.write:
        NOTICE_PATH.write_text(build_notice(), encoding="utf-8", newline="\n")
        print(
            f"THIRD_PARTY_NOTICES_WRITTEN bytes={NOTICE_PATH.stat().st_size} "
            f"sha256={_sha256(NOTICE_PATH.read_bytes())}"
        )
        return 0
    if arguments.package_root is not None:
        package_root = arguments.package_root
        if not package_root.is_absolute():
            package_root = Path.cwd() / package_root
        path, manifest = find_packaged_notice(package_root)
        print(
            json.dumps(
                {
                    "path": str(path.resolve()),
                    "sha256": APPROVED_NOTICE_SHA256,
                    "componentCounts": manifest["componentCounts"],
                },
                sort_keys=True,
            )
        )
        return 0
    payload = NOTICE_PATH.read_bytes()
    if arguments.check:
        generated = build_notice().encode("utf-8")
        if payload != generated:
            raise RuntimeError(
                "THIRD_PARTY_NOTICES.txt is approved but is not reproducible from this toolchain"
            )
    manifest = verify_notice_bytes(payload)
    counts = manifest["componentCounts"]
    print(
        ("THIRD_PARTY_NOTICES_OK " if arguments.check else "THIRD_PARTY_NOTICES_VERIFIED ")
        + " ".join(f"{key}={counts[key]}" for key in ("frontend", "python", "runtime", "rust"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
