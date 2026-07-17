"""Build and smoke-check the frozen Python sidecar for the native target."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "desktop" / "careeros-backend.spec"
BUILD_ROOT = PROJECT_ROOT / ".build" / "sidecar"
TAURI_BINARIES = PROJECT_ROOT / "frontend" / "src-tauri" / "binaries"


def native_target_triple() -> str:
    python_platform = sysconfig.get_platform().lower().replace("_", "-")
    if python_platform == "win-amd64":
        return "x86_64-pc-windows-msvc"
    if python_platform in {"win-arm64", "win-aarch64"}:
        return "aarch64-pc-windows-msvc"
    machine = os.uname().machine.lower() if hasattr(os, "uname") else ""
    if sys.platform == "darwin":
        return "aarch64-apple-darwin" if machine in {"arm64", "aarch64"} else "x86_64-apple-darwin"
    if sys.platform.startswith("linux"):
        return "aarch64-unknown-linux-gnu" if machine in {"arm64", "aarch64"} else "x86_64-unknown-linux-gnu"
    raise RuntimeError(f"Unsupported sidecar build platform: {python_platform}")


def executable_name() -> str:
    return "careeros-backend.exe" if os.name == "nt" else "careeros-backend"


def run_pyinstaller(mode: str) -> Path:
    destination = BUILD_ROOT / mode
    work = BUILD_ROOT / f"work-{mode}"
    environment = os.environ.copy()
    environment["CAREEROS_PYINSTALLER_MODE"] = mode
    environment["CAREEROS_SIDECAR_CONSOLE"] = "1"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(destination),
        "--workpath",
        str(work),
        str(SPEC_PATH),
    ]
    subprocess.run(command, cwd=PROJECT_ROOT, env=environment, check=True)
    if mode == "onedir":
        return destination / "careeros-backend" / executable_name()
    return destination / executable_name()


def smoke_help(binary: Path) -> None:
    completed = subprocess.run(
        [str(binary), "--help"],
        check=False,
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0 or b"--data-dir" not in completed.stdout:
        raise RuntimeError(f"Frozen sidecar help smoke failed with code {completed.returncode}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_tauri_runtime(source_directory: Path, target: str) -> Path:
    TAURI_BINARIES.mkdir(parents=True, exist_ok=True)
    legacy_name = f"careeros-backend-{target}{'.exe' if os.name == 'nt' else ''}"
    legacy_external_binary = (TAURI_BINARIES / legacy_name).resolve()
    if legacy_external_binary.parent != TAURI_BINARIES.resolve():
        raise RuntimeError("Refusing to remove a legacy sidecar outside the binaries directory")
    legacy_external_binary.unlink(missing_ok=True)
    runtime_directory = (TAURI_BINARIES / "careeros-backend-runtime").resolve()
    if runtime_directory.parent != TAURI_BINARIES.resolve():
        raise RuntimeError("Refusing to replace a runtime outside the Tauri binaries directory")
    if runtime_directory.exists():
        shutil.rmtree(runtime_directory)
    shutil.copytree(source_directory, runtime_directory)
    destination = runtime_directory / executable_name()
    if not destination.is_file():
        raise RuntimeError("PyInstaller one-folder runtime has no executable")
    if os.name != "nt":
        destination.chmod(0o755)
    runtime_files = [path for path in runtime_directory.rglob("*") if path.is_file()]
    manifest = {
        "schemaVersion": 1,
        "layout": "onedir-resource",
        "target": target,
        "filename": destination.relative_to(TAURI_BINARIES).as_posix(),
        "sha256": sha256(destination),
        "sizeBytes": destination.stat().st_size,
        "runtimeFileCount": len(runtime_files),
        "runtimeSizeBytes": sum(path.stat().st_size for path in runtime_files),
    }
    (TAURI_BINARIES / "sidecar-build.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return destination


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--portable-onefile",
        action="store_true",
        help="Also build a non-distributed one-file diagnostic; installers always use onedir",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    diagnostic = run_pyinstaller("onedir")
    smoke_help(diagnostic)
    prepared = prepare_tauri_runtime(diagnostic.parent, native_target_triple())
    if arguments.portable_onefile:
        portable = run_pyinstaller("onefile")
        smoke_help(portable)
    print(prepared)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
