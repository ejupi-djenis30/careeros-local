"""Bind the audited Python dependency graph to the CareerOS release component."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from packaging.markers import UndefinedComparison, UndefinedEnvironmentName, default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from scripts.check_release_versions import release_versions, validate_versions
from scripts.release_assets import validate_stable_version


def _object(value: object, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(message)
    return value


@dataclass(frozen=True)
class LockedRequirement:
    name: str
    version: str
    purl: str


_HASHED_REQUIREMENT = re.compile(
    r"^(?P<requirement>.+?)(?P<hashes>(?:\s+--hash=sha256:[0-9a-fA-F]{64})+)$"
)
_HASH = re.compile(r"--hash=sha256:([0-9a-fA-F]{64})")


def _logical_lines(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    parts: list[str] = []
    start = 0
    for number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not parts and (not stripped or stripped.startswith("#")):
            continue
        if not stripped or stripped.startswith("#"):
            raise RuntimeError(
                f"Requirements lock has an interrupted continuation at line {number}"
            )
        continued = raw_line.rstrip().endswith("\\")
        content = raw_line.rstrip()
        if continued:
            content = content[:-1].rstrip()
        if not parts:
            start = number
        parts.append(content.strip())
        if not continued:
            result.append((start, " ".join(parts)))
            parts = []
    if parts:
        raise RuntimeError(f"Requirements lock has an unterminated continuation at line {start}")
    if not result:
        raise RuntimeError("Requirements lock contains no dependencies")
    return result


def locked_requirements(path: Path) -> dict[str, LockedRequirement]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"Cannot read requirements lock: {path}") from exc
    result: dict[str, LockedRequirement] = {}
    environment = {key: str(value) for key, value in default_environment().items()}
    for line_number, logical_line in _logical_lines(text):
        match = _HASHED_REQUIREMENT.fullmatch(logical_line)
        if match is None:
            raise RuntimeError(
                f"Requirements lock entry at line {line_number} is not exactly pinned and hash-locked"
            )
        hashes = _HASH.findall(match.group("hashes"))
        if len(hashes) != len(set(digest.lower() for digest in hashes)):
            raise RuntimeError(f"Requirements lock has duplicate hashes at line {line_number}")
        try:
            requirement = Requirement(match.group("requirement"))
        except InvalidRequirement as exc:
            raise RuntimeError(
                f"Requirements lock has an invalid entry at line {line_number}"
            ) from exc
        specifiers = list(requirement.specifier)
        if requirement.url is not None or len(specifiers) != 1:
            raise RuntimeError(f"Requirements lock entry at line {line_number} is not an exact pin")
        specifier = specifiers[0]
        if specifier.operator != "==" or specifier.version.endswith(".*"):
            raise RuntimeError(f"Requirements lock entry at line {line_number} is not an exact pin")
        try:
            version = str(Version(specifier.version))
            active = requirement.marker is None or requirement.marker.evaluate(environment)
        except (InvalidVersion, KeyError, UndefinedComparison, UndefinedEnvironmentName) as exc:
            raise RuntimeError(
                f"Requirements lock has an invalid version or marker at line {line_number}"
            ) from exc
        if not active:
            continue
        name = canonicalize_name(requirement.name)
        if name in result:
            raise RuntimeError(f"Requirements lock contains duplicate active dependency {name}")
        purl = f"pkg:pypi/{name}@{quote(version, safe='')}"
        result[name] = LockedRequirement(name=name, version=version, purl=purl)
    if not result:
        raise RuntimeError("Requirements lock has no dependencies for this marker environment")
    return result


def _components(value: dict[str, Any], *, forbidden_ref: str | None = None) -> list[dict[str, Any]]:
    components = value.get("components")
    if not isinstance(components, list) or not components:
        raise RuntimeError("Backend SBOM has no audited dependency components")
    result = [
        _object(component, "Backend SBOM contains a non-object component")
        for component in components
    ]
    references = [component.get("bom-ref") for component in result]
    if not all(isinstance(reference, str) and reference for reference in references):
        raise RuntimeError("Backend SBOM dependencies require stable bom-ref values")
    if len(set(references)) != len(references):
        raise RuntimeError("Backend SBOM contains duplicate component bom-ref values")
    if forbidden_ref is not None and forbidden_ref in references:
        raise RuntimeError("Backend SBOM dependency bom-ref collides with the CareerOS root")
    return result


def project_bom_ref(version: str) -> str:
    return f"pkg:pypi/careeros-local@{validate_stable_version(version)}"


def _bind_components(
    components: list[dict[str, Any]],
    expected: dict[str, LockedRequirement],
    *,
    add_missing_purls: bool,
) -> None:
    found: set[str] = set()
    for component in components:
        name = component.get("name")
        version = component.get("version")
        if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
            raise RuntimeError("Backend SBOM dependencies require name and version")
        canonical_name = canonicalize_name(name)
        requirement = expected.get(canonical_name)
        if requirement is None or canonical_name in found:
            raise RuntimeError("Backend SBOM components do not match the exact requirements lock")
        if version != requirement.version:
            raise RuntimeError("Backend SBOM component version differs from the requirements lock")
        purl = component.get("purl")
        if purl is None and add_missing_purls:
            component["purl"] = requirement.purl
        elif purl != requirement.purl:
            raise RuntimeError("Backend SBOM component purl differs from the requirements lock")
        found.add(canonical_name)
    if found != set(expected):
        raise RuntimeError("Backend SBOM components do not match the exact requirements lock")


def validate_backend_sbom(
    value: object, *, version: str, requirements_lock: Path
) -> dict[str, Any]:
    sbom = _object(value, "Backend SBOM must be a JSON object")
    if sbom.get("bomFormat") != "CycloneDX":
        raise RuntimeError("Backend SBOM is not CycloneDX")
    root = project_bom_ref(version)
    components = _components(sbom, forbidden_ref=root)
    _bind_components(components, locked_requirements(requirements_lock), add_missing_purls=False)
    if any(component.get("purl") == root for component in components):
        raise RuntimeError("Backend SBOM dependency purl collides with the CareerOS root")
    metadata = _object(sbom.get("metadata"), "Backend SBOM has no metadata object")
    expected_component = {
        "type": "application",
        "bom-ref": root,
        "name": "careeros-local",
        "version": validate_stable_version(version),
        "purl": root,
        "licenses": [{"license": {"id": "MIT"}}],
    }
    if metadata.get("component") != expected_component:
        raise RuntimeError("Backend SBOM does not identify the exact CareerOS release component")
    dependencies = sbom.get("dependencies")
    if not isinstance(dependencies, list):
        raise RuntimeError("Backend SBOM has no dependency graph")
    root_dependencies = [
        dependency
        for dependency in dependencies
        if isinstance(dependency, dict) and dependency.get("ref") == root
    ]
    expected_refs = sorted(str(component["bom-ref"]) for component in components)
    if root_dependencies != [{"ref": root, "dependsOn": expected_refs}]:
        raise RuntimeError("Backend SBOM root does not bind the audited dependency graph")
    return sbom


def finalize_backend_sbom(path: Path, *, version: str, requirements_lock: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    sbom = _object(value, "Backend SBOM must be a JSON object")
    root = project_bom_ref(version)
    components = _components(sbom, forbidden_ref=root)
    _bind_components(components, locked_requirements(requirements_lock), add_missing_purls=True)
    metadata = sbom.get("metadata")
    if metadata is None:
        metadata = {}
        sbom["metadata"] = metadata
    metadata = _object(metadata, "Backend SBOM metadata must be an object")
    if metadata.get("component") is not None:
        raise RuntimeError("Backend SBOM already has a root component")
    metadata["component"] = {
        "type": "application",
        "bom-ref": root,
        "name": "careeros-local",
        "version": validate_stable_version(version),
        "purl": root,
        "licenses": [{"license": {"id": "MIT"}}],
    }
    dependencies = sbom.setdefault("dependencies", [])
    if not isinstance(dependencies, list):
        raise RuntimeError("Backend SBOM dependencies must be a list")
    if any(isinstance(item, dict) and item.get("ref") == root for item in dependencies):
        raise RuntimeError("Backend SBOM already contains a CareerOS root dependency")
    dependencies.append(
        {
            "ref": root,
            "dependsOn": sorted(str(component["bom-ref"]) for component in components),
        }
    )
    validate_backend_sbom(sbom, version=version, requirements_lock=requirements_lock)
    path.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sbom


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sbom", required=True, type=Path)
    parser.add_argument("--requirements-lock", required=True, type=Path)
    arguments = parser.parse_args()
    version = validate_versions(release_versions())
    finalize_backend_sbom(
        arguments.sbom,
        version=version,
        requirements_lock=arguments.requirements_lock,
    )
    print(f"BACKEND_SBOM_FINALIZED version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
