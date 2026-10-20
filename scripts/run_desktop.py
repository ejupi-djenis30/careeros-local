"""Prepare the native sidecar and launch Tauri with installed, locked tools."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = PROJECT_ROOT / "frontend"
MANIFEST = FRONTEND / "src-tauri" / "binaries" / "sidecar-build.json"


def command_path(name: str) -> str:
    """Resolve an installed build command without provisioning it."""
    resolved = shutil.which(name)
    if resolved is None:
        raise RuntimeError(
            f"Required desktop build command is unavailable: {name}. "
            "Install the Rust/Tauri prerequisites documented in docs/development.md."
        )
    return resolved


def local_tauri_cli() -> str:
    executable = FRONTEND / "node_modules" / ".bin" / ("tauri.cmd" if os.name == "nt" else "tauri")
    if not executable.is_file():
        raise RuntimeError(
            "The local Tauri CLI is missing. Run npm ci --ignore-scripts --prefix frontend "
            "with the Node version in .nvmrc before building."
        )
    return str(executable)


def workspace_python() -> Path:
    relative = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    candidate = PROJECT_ROOT / ".venv" / relative
    return candidate if candidate.is_file() else Path(sys.executable)


def native_target(python: Path) -> str:
    """Use the sidecar interpreter's architecture, which may differ from this process."""
    result = subprocess.run(
        [
            str(python),
            "-c",
            "from scripts.build_backend_sidecar import native_target_triple; "
            "print(native_target_triple())",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    target = result.stdout.strip()
    if not target:
        raise RuntimeError("The sidecar Python interpreter did not report a native target.")
    return target


def require_rust_target(target: str) -> None:
    result = subprocess.run(
        [command_path("rustup"), "target", "list", "--installed"],
        cwd=FRONTEND,
        check=True,
        capture_output=True,
        text=True,
    )
    if target not in result.stdout.splitlines():
        raise RuntimeError(
            f"The Rust target {target} is not installed. Run rustup target add {target} "
            "explicitly before building; see docs/development.md."
        )


def prepare_sidecar(python: Path) -> str:
    subprocess.run(
        [str(python), str(PROJECT_ROOT / "scripts" / "build_backend_sidecar.py")],
        cwd=PROJECT_ROOT,
        check=True,
    )
    return str(json.loads(MANIFEST.read_text(encoding="utf-8"))["target"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("dev", "build"))
    parser.add_argument("--debug", action="store_true")
    arguments = parser.parse_args()
    cli = local_tauri_cli()
    python = workspace_python()
    target = native_target(python)
    require_rust_target(target)
    if prepare_sidecar(python) != target:
        raise RuntimeError("The prepared sidecar target differs from the checked Rust target.")
    command = [cli, arguments.command, "--target", target]
    if arguments.command == "build":
        if arguments.debug:
            command.append("--debug")
        command.extend(["--", "--locked"])
    subprocess.run(command, cwd=FRONTEND, check=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
