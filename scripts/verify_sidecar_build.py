"""Verify the sidecar target and export its path for artifact acceptance tests."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from scripts.build_backend_sidecar import (
    RUNTIME_LAYOUT,
    SIDECAR_MANIFEST_SCHEMA,
    _is_link_like,
    runtime_inventory,
    sha256,
)
from scripts.release_assets import TARGETS

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


SOURCE_BUILT_CRYPTOGRAPHY_TARGETS = {
    "aarch64-pc-windows-msvc",
    "x86_64-apple-darwin",
}
OPENSSL_DYNAMIC_LIBRARY_PREFIXES = (
    "libcrypto",
    "libeay",
    "libssl",
    "ssleay",
)
MANIFEST_FIELDS = {
    "filename",
    "layout",
    "runtimeFileCount",
    "runtimeSha256",
    "runtimeSizeBytes",
    "schemaVersion",
    "sha256",
    "sizeBytes",
    "target",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
WINDOWS_PE_MACHINES = {
    "x86_64-pc-windows-msvc": 0x8664,
    "aarch64-pc-windows-msvc": 0xAA64,
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


def _is_dynamic_openssl_dependency(dependency: str) -> bool:
    basename = dependency.replace("\\", "/").rsplit("/", maxsplit=1)[-1].casefold()
    return basename.startswith(OPENSSL_DYNAMIC_LIBRARY_PREFIXES)


def _macos_dependencies(extension: Path) -> tuple[str, ...]:
    completed = subprocess.run(
        ["otool", "-L", str(extension)],
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(
        line.strip().split(" (", maxsplit=1)[0]
        for line in completed.stdout.splitlines()[1:]
        if line.strip()
    )


def _windows_dependencies(extension: Path) -> tuple[str, ...]:
    import pefile  # type: ignore[import-untyped]

    image = pefile.PE(str(extension), fast_load=True)
    try:
        image.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
        )
        return tuple(
            entry.dll.decode("ascii", errors="replace")
            for entry in getattr(image, "DIRECTORY_ENTRY_IMPORT", ())
        )
    finally:
        image.close()


def _verify_cryptography_linkage(runtime_root: Path, expected_target: str) -> None:
    if expected_target not in SOURCE_BUILT_CRYPTOGRAPHY_TARGETS:
        return

    bindings = runtime_root / "cryptography" / "hazmat" / "bindings"
    extensions = sorted(path for path in bindings.glob("_rust*") if path.is_file())
    if len(extensions) != 1:
        raise RuntimeError(
            f"Expected exactly one packaged cryptography Rust extension, found {len(extensions)}"
        )

    extension = extensions[0]
    if expected_target == "x86_64-apple-darwin":
        dependencies = _macos_dependencies(extension)
    else:
        dependencies = _windows_dependencies(extension)
    dynamic_openssl = sorted(
        dependency for dependency in dependencies if _is_dynamic_openssl_dependency(dependency)
    )
    if dynamic_openssl:
        raise RuntimeError(
            "Source-built cryptography must link OpenSSL statically; dynamic dependencies: "
            + ", ".join(dynamic_openssl)
        )


def _expected_binary_name(target: str) -> str:
    return "careeros-backend.exe" if "windows" in target else "careeros-backend"


def _contained_manifest_binary(payload: dict[str, object], expected_target: str) -> Path:
    filename = payload.get("filename")
    if not isinstance(filename, str) or not filename or "\\" in filename:
        raise RuntimeError("Prepared sidecar manifest has an invalid binary filename")
    relative = Path(filename)
    expected_relative = Path("careeros-backend-runtime") / _expected_binary_name(expected_target)
    if relative != expected_relative or relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError("Prepared sidecar manifest binary path is not canonical")
    root = MANIFEST.parent.resolve(strict=True)
    candidate = root / relative
    if _is_link_like(candidate):
        raise RuntimeError("Prepared sidecar binary must not be a link or junction")
    binary = candidate.resolve(strict=True)
    if not binary.is_relative_to(root) or not binary.is_file():
        raise RuntimeError("Prepared sidecar binary escapes or is not a regular file")
    return binary


def _verify_windows_subsystem(binary: Path, expected_target: str) -> None:
    if "windows" not in expected_target:
        return
    import pefile  # type: ignore[import-untyped]

    image = pefile.PE(str(binary), fast_load=True)
    try:
        expected_machine = WINDOWS_PE_MACHINES[expected_target]
        if image.FILE_HEADER.Machine != expected_machine:
            raise RuntimeError(
                "Packaged Windows sidecar architecture does not match "
                f"{expected_target}: 0x{image.FILE_HEADER.Machine:04x}"
            )
        # IMAGE_SUBSYSTEM_WINDOWS_GUI: the packaged sidecar must never create a
        # console window behind the native application.
        if image.OPTIONAL_HEADER.Subsystem != 2:
            raise RuntimeError("Packaged Windows sidecar is not a windowed executable")
    finally:
        image.close()


def main() -> int:
    expected = os.environ["EXPECTED_TARGET"]
    if expected not in TARGETS:
        raise RuntimeError(f"Unsupported expected sidecar target: {expected}")
    if (
        _is_link_like(MANIFEST.parent)
        or _is_link_like(MANIFEST)
        or not MANIFEST.is_file()
        or not 0 < MANIFEST.stat().st_size <= 16 * 1024
    ):
        raise RuntimeError("Prepared sidecar manifest is missing or not a regular file")
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != MANIFEST_FIELDS:
        raise RuntimeError("Prepared sidecar manifest schema is incomplete or has unknown fields")
    if payload.get("schemaVersion") != SIDECAR_MANIFEST_SCHEMA:
        raise RuntimeError("Prepared sidecar manifest schema version is unsupported")
    if payload.get("target") != expected:
        raise RuntimeError(f"Sidecar target {payload.get('target')} does not match {expected}")
    if payload.get("layout") != RUNTIME_LAYOUT:
        raise RuntimeError("Installers require the one-folder resource layout")
    binary = _contained_manifest_binary(payload, expected)
    if (
        not isinstance(payload.get("sizeBytes"), int)
        or payload["sizeBytes"] <= 0
        or binary.stat().st_size != payload["sizeBytes"]
        or not isinstance(payload.get("sha256"), str)
        or not SHA256_PATTERN.fullmatch(payload["sha256"])
        or sha256(binary) != payload["sha256"]
    ):
        raise RuntimeError("Prepared sidecar binary bytes do not match its manifest")
    runtime_directory = MANIFEST.parent / "careeros-backend-runtime"
    actual_inventory = runtime_inventory(runtime_directory)
    expected_inventory = {
        "runtimeFileCount": payload.get("runtimeFileCount"),
        "runtimeSizeBytes": payload.get("runtimeSizeBytes"),
        "runtimeSha256": payload.get("runtimeSha256"),
    }
    if actual_inventory != expected_inventory:
        raise RuntimeError("Prepared sidecar runtime inventory does not match its manifest")
    runtime_root = runtime_directory / "_internal"
    if not runtime_root.is_dir():
        raise RuntimeError("Prepared sidecar runtime tree is missing")
    _verify_runtime_tree(runtime_root)
    _verify_cryptography_linkage(runtime_root, expected)
    _verify_windows_subsystem(binary, expected)
    github_environment = Path(os.environ["GITHUB_ENV"])
    if "\r" in str(binary) or "\n" in str(binary):
        raise RuntimeError("Prepared sidecar path is unsafe for GITHUB_ENV")
    with github_environment.open("a", encoding="utf-8", newline="\n") as destination:
        destination.write(f"CAREEROS_SIDECAR_BINARY={binary}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
