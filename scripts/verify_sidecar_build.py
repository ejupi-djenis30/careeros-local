"""Verify the sidecar target and export its path for artifact acceptance tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend" / "src-tauri" / "binaries" / "sidecar-build.json"


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
    github_environment = Path(os.environ["GITHUB_ENV"])
    with github_environment.open("a", encoding="utf-8", newline="\n") as destination:
        destination.write(f"CAREEROS_SIDECAR_BINARY={binary}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
