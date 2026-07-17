"""Prepare the native sidecar and launch Tauri for the matching architecture."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = PROJECT_ROOT / "frontend"
MANIFEST = FRONTEND / "src-tauri" / "binaries" / "sidecar-build.json"


def workspace_python() -> Path:
    relative = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    candidate = PROJECT_ROOT / ".venv" / relative
    return candidate if candidate.is_file() else Path(sys.executable)


def prepare_sidecar() -> str:
    subprocess.run(
        [str(workspace_python()), str(PROJECT_ROOT / "scripts" / "build_backend_sidecar.py")],
        cwd=PROJECT_ROOT,
        check=True,
    )
    return str(json.loads(MANIFEST.read_text(encoding="utf-8"))["target"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("dev", "build"))
    parser.add_argument("--debug", action="store_true")
    arguments = parser.parse_args()
    target = prepare_sidecar()
    subprocess.run(["rustup", "target", "add", target], check=True)
    command = ["npx", "tauri", arguments.command, "--target", target]
    if arguments.command == "build" and arguments.debug:
        command.append("--debug")
    subprocess.run(command, cwd=FRONTEND, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
