"""Canonical project-license checks shared by release and package verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LICENSE_NAME = "LICENSE"
APPROVED_LICENSE_SHA256 = "7e1d73415a3de7fa896ac8871ae0aea8fc736e9f0d274bf658c18399236976c6"


def approved_license_bytes(path: Path = ROOT / LICENSE_NAME) -> bytes:
    """Return the approved license as canonical UTF-8 text with LF newlines."""
    if path.name != LICENSE_NAME or path.is_symlink() or not path.is_file():
        raise RuntimeError("The approved repository LICENSE file is required")
    payload = path.read_bytes()
    if not payload:
        raise RuntimeError("The approved repository LICENSE file must not be empty")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeError("The approved MIT LICENSE must be UTF-8 text") from error
    canonical = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    if digest != APPROVED_LICENSE_SHA256:
        raise RuntimeError("LICENSE content does not match the approved MIT license")
    return canonical


def approved_license_record(path: Path = ROOT / LICENSE_NAME) -> dict[str, Any]:
    payload = approved_license_bytes(path)
    return {
        "spdx": "MIT",
        "name": LICENSE_NAME,
        "normalization": "utf-8-lf",
        "size": len(payload),
        "sha256": APPROVED_LICENSE_SHA256,
    }


def write_public_license(source: Path, destination: Path) -> dict[str, Any]:
    if destination.name != LICENSE_NAME or destination.exists() or destination.is_symlink():
        raise RuntimeError("Public LICENSE destination must be a new canonical LICENSE file")
    destination.write_bytes(approved_license_bytes(source))
    return verify_distributed_license(destination, source=source)


def verify_distributed_license(
    path: Path, *, source: Path = ROOT / LICENSE_NAME
) -> dict[str, Any]:
    if path.name != LICENSE_NAME or path.is_symlink() or not path.is_file():
        raise RuntimeError(f"Packaged project LICENSE is missing or unsafe: {path}")
    expected = approved_license_bytes(source)
    if path.read_bytes() != expected:
        raise RuntimeError(f"Packaged project LICENSE differs from the approved text: {path}")
    return approved_license_record(source)


def find_packaged_license(
    package_root: Path, *, source: Path = ROOT / LICENSE_NAME
) -> tuple[Path, dict[str, Any]]:
    """Verify the exact Tauri resource destination and reject duplicate project notices."""
    if package_root.is_symlink() or not package_root.is_dir():
        raise RuntimeError(f"Extracted package root is missing or unsafe: {package_root}")
    expected = approved_license_bytes(source)
    license_path = package_root / LICENSE_NAME
    verify_distributed_license(license_path, source=source)
    matches: list[Path] = []
    pending = [package_root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            children = sorted(entries, key=lambda entry: entry.name.casefold(), reverse=True)
        for entry in children:
            path = Path(entry.path)
            if entry.name.casefold() == LICENSE_NAME.casefold():
                if entry.is_symlink():
                    raise RuntimeError(f"Packaged LICENSE alias is unsafe: {path}")
                if entry.is_file(follow_symlinks=False) and path.read_bytes() == expected:
                    matches.append(path)
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)
    matches.sort(key=lambda item: str(item).casefold())
    if matches != [license_path]:
        raise RuntimeError(
            f"Expected exactly one approved project LICENSE under {package_root}; "
            f"found {len(matches)}"
        )
    return license_path, approved_license_record(source)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", required=True, type=Path)
    arguments = parser.parse_args()
    package_root = arguments.package_root
    if not package_root.is_absolute():
        package_root = Path.cwd() / package_root
    path, record = find_packaged_license(package_root)
    print(json.dumps({**record, "path": str(path.resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
