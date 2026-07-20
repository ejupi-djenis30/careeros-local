"""Create a deterministic SHA-256 inventory for native desktop bundles."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

if __package__ is None:  # Support direct `python scripts/...` invocation.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.release_assets import reject_casefold_collisions, validate_portable_name  # noqa: E402

RELEASE_SUFFIXES = {".appimage", ".deb", ".dmg", ".exe", ".msi"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def release_artifacts(bundle_root: Path) -> list[Path]:
    """Return only the distributable files flattened into the GitHub release."""
    artifacts = sorted(
        (
            path
            for path in bundle_root.rglob("*")
            if path.is_file() and path.suffix.lower() in RELEASE_SUFFIXES
        ),
        key=lambda path: path.name.lower(),
    )
    names = [validate_portable_name(path.name) for path in artifacts]
    try:
        reject_casefold_collisions(names)
    except RuntimeError as error:
        raise RuntimeError("Desktop bundles contain duplicate release filenames") from error
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    bundle_root = root / "frontend" / "src-tauri" / "target" / arguments.target / "release" / "bundle"
    artifacts = release_artifacts(bundle_root)
    if not artifacts:
        raise RuntimeError(f"No desktop bundles were created under {bundle_root}")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{digest(path)}  {path.name}" for path in artifacts]
    arguments.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
