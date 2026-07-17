"""Verify the sidecar target and export its path for artifact acceptance tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend" / "src-tauri" / "binaries" / "sidecar-build.json"
REQUIRED_RESOURCES = (
    "backend/inference/model_catalog.json",
    "backend/inference/model_catalog.sha256",
    "backend/ai/fixtures/golden-1.0.0.json",
)
FORBIDDEN_PACKAGE_NAMES = {
    "anthropic",
    "fitz",
    "g4f",
    "groq",
    "openai",
    "pymupdf",
    "supabase",
}


def _is_forbidden_package_path(relative_path: Path) -> bool:
    normalized_parts = tuple(part.casefold().replace("_", "-") for part in relative_path.parts)
    if any(
        part == name or part.startswith(f"{name}-")
        for part in normalized_parts
        for name in FORBIDDEN_PACKAGE_NAMES
    ):
        return True
    normalized_path = "/".join(normalized_parts)
    return "/google/generativeai/" in f"/{normalized_path}/"


def _verify_runtime_tree(runtime_root: Path) -> None:
    for resource in REQUIRED_RESOURCES:
        if not (runtime_root / Path(resource)).is_file():
            raise RuntimeError(f"Prepared sidecar is missing required resource: {resource}")

    forbidden = sorted(
        path.relative_to(runtime_root).as_posix()
        for path in runtime_root.rglob("*")
        if _is_forbidden_package_path(path.relative_to(runtime_root))
    )
    if forbidden:
        raise RuntimeError(
            "Prepared sidecar contains forbidden remote or legacy AI packages: "
            + ", ".join(forbidden[:10])
        )


def main() -> int:
    expected = os.environ["EXPECTED_TARGET"]
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("target") != expected:
        raise RuntimeError(f"Sidecar target {payload.get('target')} does not match {expected}")
    if payload.get("layout") != "onedir-resource":
        raise RuntimeError("Installers require the one-folder resource layout")
    binary = MANIFEST.parent / Path(str(payload["filename"])).as_posix()
    if not binary.is_file() or binary.stat().st_size != int(payload["sizeBytes"]):
        raise RuntimeError("Prepared sidecar is missing or has an unexpected size")
    runtime_root = MANIFEST.parent / "careeros-backend-runtime" / "_internal"
    if not runtime_root.is_dir():
        raise RuntimeError("Prepared sidecar runtime tree is missing")
    _verify_runtime_tree(runtime_root)
    github_environment = Path(os.environ["GITHUB_ENV"])
    with github_environment.open("a", encoding="utf-8", newline="\n") as destination:
        destination.write(f"CAREEROS_SIDECAR_BINARY={binary}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
