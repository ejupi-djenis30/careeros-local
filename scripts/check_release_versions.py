"""Fail fast when release metadata or a version tag drifts out of sync."""

from __future__ import annotations

import ast
import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object in {path}")
    return cast(dict[str, Any], value)


def _toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as source:
        return tomllib.load(source)


def _python_string_constant(path: Path, name: str) -> str:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for statement in module.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if (
            isinstance(target, ast.Name)
            and target.id == name
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            return statement.value.value
    raise RuntimeError(f"{path} has no string constant named {name}")


def release_versions(root: Path = ROOT) -> dict[str, str]:
    pyproject = _toml(root / "pyproject.toml")
    package = _json(root / "frontend" / "package.json")
    package_lock = _json(root / "frontend" / "package-lock.json")
    tauri = _json(root / "frontend" / "src-tauri" / "tauri.conf.json")
    cargo = _toml(root / "frontend" / "src-tauri" / "Cargo.toml")
    cargo_lock = _toml(root / "frontend" / "src-tauri" / "Cargo.lock")

    locked_package = package_lock.get("packages", {})
    if not isinstance(locked_package, dict) or not isinstance(locked_package.get(""), dict):
        raise RuntimeError("frontend/package-lock.json has no root package metadata")

    locked_crate = next(
        (
            entry
            for entry in cargo_lock.get("package", [])
            if isinstance(entry, dict) and entry.get("name") == "careeros-local"
        ),
        None,
    )
    if locked_crate is None:
        raise RuntimeError("frontend/src-tauri/Cargo.lock has no careeros-local package")

    values = {
        "backend/__init__.py": _python_string_constant(
            root / "backend" / "__init__.py", "__version__"
        ),
        "pyproject.toml": pyproject["project"]["version"],  # type: ignore[index]
        "frontend/package.json": package["version"],
        "frontend/package-lock.json": locked_package[""]["version"],
        "frontend/src-tauri/tauri.conf.json": tauri["version"],
        "frontend/src-tauri/Cargo.toml": cargo["package"]["version"],  # type: ignore[index]
        "frontend/src-tauri/Cargo.lock": locked_crate["version"],
    }
    if not all(isinstance(value, str) for value in values.values()):
        raise RuntimeError("Every release version must be a string")
    return {name: str(value) for name, value in values.items()}


def validate_versions(versions: dict[str, str], tag: str | None = None) -> str:
    unique = set(versions.values())
    if len(unique) != 1:
        details = ", ".join(f"{name}={value}" for name, value in versions.items())
        raise RuntimeError(f"Release versions disagree: {details}")
    version = unique.pop()
    if not SEMANTIC_VERSION.fullmatch(version):
        raise RuntimeError(f"Release version is not semantic: {version}")
    if tag and tag != f"v{version}":
        raise RuntimeError(f"Tag {tag} does not match release version v{version}")
    return version


def main() -> int:
    ref_type = os.environ.get("GITHUB_REF_TYPE")
    tag = os.environ.get("GITHUB_REF_NAME") if ref_type == "tag" else None
    versions = release_versions()
    version = validate_versions(versions, tag)
    print(f"RELEASE_VERSION={version} SOURCES={len(versions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
