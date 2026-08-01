"""Build and smoke-check the frozen Python sidecar for the native target."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import sysconfig
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "desktop" / "careeros-backend.spec"
BUILD_ROOT = PROJECT_ROOT / ".build" / "sidecar"
TAURI_BINARIES = PROJECT_ROOT / "frontend" / "src-tauri" / "binaries"
SIDECAR_MANIFEST_SCHEMA = 2
RUNTIME_LAYOUT = "onedir-resource"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
SUPPORTED_TARGETS = {
    "aarch64-apple-darwin",
    "aarch64-pc-windows-msvc",
    "aarch64-unknown-linux-gnu",
    "x86_64-apple-darwin",
    "x86_64-pc-windows-msvc",
    "x86_64-unknown-linux-gnu",
}


def _is_link_like(path: Path) -> bool:
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


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
        return (
            "aarch64-unknown-linux-gnu"
            if machine in {"arm64", "aarch64"}
            else "x86_64-unknown-linux-gnu"
        )
    raise RuntimeError(f"Unsupported sidecar build platform: {python_platform}")


def executable_name() -> str:
    return "careeros-backend.exe" if os.name == "nt" else "careeros-backend"


def run_pyinstaller(mode: str, *, console: bool) -> Path:
    destination = BUILD_ROOT / mode
    work = BUILD_ROOT / f"work-{mode}"
    environment = os.environ.copy()
    environment["CAREEROS_PYINSTALLER_MODE"] = mode
    environment["CAREEROS_SIDECAR_CONSOLE"] = "1" if console else "0"
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


def smoke_help(binary: Path, *, require_help_output: bool) -> None:
    completed = subprocess.run(
        [str(binary), "--help"],
        check=False,
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0 or (require_help_output and b"--data-dir" not in completed.stdout):
        raise RuntimeError(f"Frozen sidecar help smoke failed with code {completed.returncode}")
    if completed.stdout and b"--data-dir" not in completed.stdout:
        raise RuntimeError("Frozen sidecar returned unexpected help output")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contained_tree(source_directory: Path) -> Path:
    if _is_link_like(source_directory):
        raise RuntimeError("PyInstaller one-folder output must not be a link or junction")
    source_root = source_directory.resolve(strict=True)
    if not source_root.is_dir():
        raise RuntimeError("PyInstaller one-folder output is not a directory")
    for path in source_root.rglob("*"):
        if not _is_link_like(path):
            continue
        try:
            target = path.resolve(strict=True)
        except OSError as error:
            raise RuntimeError(f"PyInstaller output contains a broken link: {path}") from error
        if not target.is_relative_to(source_root):
            raise RuntimeError(f"PyInstaller output link escapes its runtime tree: {path}")
    return source_root


def runtime_inventory(runtime_directory: Path) -> dict[str, int | str]:
    """Return a deterministic, path-bound digest of one prepared runtime tree."""
    root = runtime_directory.resolve(strict=True)
    if _is_link_like(runtime_directory) or not root.is_dir():
        raise RuntimeError("Prepared sidecar runtime must be a regular directory")
    files: list[tuple[str, Path]] = []
    folded: dict[str, str] = {}
    for path in root.rglob("*"):
        if _is_link_like(path):
            raise RuntimeError(f"Prepared sidecar runtime contains a symbolic link: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise RuntimeError(f"Prepared sidecar runtime contains a special file: {path}")
        relative = path.relative_to(root).as_posix()
        key = relative.casefold()
        if key in folded:
            raise RuntimeError(
                f"Prepared sidecar runtime has a case-insensitive collision: "
                f"{folded[key]} / {relative}"
            )
        folded[key] = relative
        files.append((relative, path))

    files.sort(key=lambda item: (item[0].casefold(), item[0]))
    digest = hashlib.sha256(b"careeros-sidecar-runtime-v1\0")
    total_size = 0
    for relative, path in files:
        encoded = relative.encode("utf-8")
        size = path.stat().st_size
        file_digest = sha256(path)
        if not _SHA256.fullmatch(file_digest):  # Defensive contract assertion.
            raise RuntimeError("Prepared sidecar file digest is malformed")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(size.to_bytes(8, "big"))
        digest.update(bytes.fromhex(file_digest))
        total_size += size
    if not files or total_size <= 0:
        raise RuntimeError("Prepared sidecar runtime is empty")
    return {
        "runtimeFileCount": len(files),
        "runtimeSizeBytes": total_size,
        "runtimeSha256": digest.hexdigest(),
    }


def prepare_tauri_runtime(source_directory: Path, target: str) -> Path:
    if target not in SUPPORTED_TARGETS:
        raise RuntimeError(f"Unsupported native sidecar target: {target}")
    source_directory = _contained_tree(source_directory)
    if _is_link_like(TAURI_BINARIES):
        raise RuntimeError("Tauri binaries directory must not be a link or junction")
    TAURI_BINARIES.mkdir(parents=True, exist_ok=True)
    if _is_link_like(TAURI_BINARIES) or not TAURI_BINARIES.is_dir():
        raise RuntimeError("Tauri binaries path is not a regular directory")
    legacy_name = f"careeros-backend-{target}{'.exe' if os.name == 'nt' else ''}"
    legacy_external_binary = TAURI_BINARIES / legacy_name
    if _is_link_like(legacy_external_binary):
        raise RuntimeError("Refusing to remove a linked legacy sidecar")
    if legacy_external_binary.resolve().parent != TAURI_BINARIES.resolve():
        raise RuntimeError("Refusing to remove a legacy sidecar outside the binaries directory")
    legacy_external_binary.unlink(missing_ok=True)
    runtime_directory = TAURI_BINARIES / "careeros-backend-runtime"
    if _is_link_like(runtime_directory):
        raise RuntimeError("Refusing to replace a linked sidecar runtime")
    if runtime_directory.resolve().parent != TAURI_BINARIES.resolve():
        raise RuntimeError("Refusing to replace a runtime outside the Tauri binaries directory")
    if runtime_directory.exists():
        shutil.rmtree(runtime_directory)
    # PyInstaller can use internal relative links on POSIX. The containment
    # check above prevents dereferencing an out-of-tree target; copying as
    # regular files gives every installer the same explicit resource layout.
    shutil.copytree(source_directory, runtime_directory, symlinks=False)
    destination = runtime_directory / executable_name()
    if not destination.is_file():
        raise RuntimeError("PyInstaller one-folder runtime has no executable")
    if os.name != "nt":
        destination.chmod(0o755)
    manifest = {
        "schemaVersion": SIDECAR_MANIFEST_SCHEMA,
        "layout": RUNTIME_LAYOUT,
        "target": target,
        "filename": destination.relative_to(TAURI_BINARIES).as_posix(),
        "sha256": sha256(destination),
        "sizeBytes": destination.stat().st_size,
        **runtime_inventory(runtime_directory),
    }
    manifest_path = TAURI_BINARIES / "sidecar-build.json"
    temporary_manifest = TAURI_BINARIES / "sidecar-build.json.tmp"
    if _is_link_like(manifest_path) or _is_link_like(temporary_manifest):
        raise RuntimeError("Refusing to write the sidecar manifest through a link or junction")
    temporary_manifest.unlink(missing_ok=True)
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary_manifest.replace(manifest_path)
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
    packaged = run_pyinstaller("onedir", console=False)
    # Windowed PyInstaller executables intentionally have no attached stdout
    # on Windows. Their complete lifecycle is exercised after bundling; here we
    # still require a clean --help exit and validate text wherever it exists.
    smoke_help(packaged, require_help_output=os.name != "nt")
    prepared = prepare_tauri_runtime(packaged.parent, native_target_triple())
    if arguments.portable_onefile:
        portable = run_pyinstaller("onefile", console=True)
        smoke_help(portable, require_help_output=True)
    print(prepared)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
