"""Fail CI when a documented dependency exception reaches its hard expiry."""

from __future__ import annotations

import argparse
import json
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "security-exceptions.json"
REQUIRED_FIELDS = {
    "id",
    "advisory",
    "dependency",
    "version",
    "cargo_lock",
    "scope",
    "expires",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=datetime.now(UTC).date(),
        help="Override the UTC date for deterministic verification.",
    )
    return parser.parse_args()


def validate_exceptions(manifest: Path, today: date) -> list[str]:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    exceptions = payload.get("exceptions")
    if not isinstance(exceptions, list):
        return ["security exception manifest must contain an exceptions list"]

    failures: list[str] = []
    identifiers: set[str] = set()
    for index, exception in enumerate(exceptions):
        if not isinstance(exception, dict):
            failures.append(f"exception {index} must be an object")
            continue
        missing = REQUIRED_FIELDS.difference(exception)
        if missing:
            failures.append(f"exception {index} is missing: {', '.join(sorted(missing))}")
            continue
        identifier = str(exception["id"])
        if identifier in identifiers:
            failures.append(f"duplicate exception id: {identifier}")
        identifiers.add(identifier)
        try:
            expiry = date.fromisoformat(str(exception["expires"]))
        except ValueError:
            failures.append(f"{identifier} has an invalid ISO expiry date")
            continue
        if today >= expiry:
            failures.append(f"{identifier} expired on {expiry.isoformat()}")

        lockfile = (ROOT / str(exception["cargo_lock"])).resolve()
        if not lockfile.is_relative_to(ROOT):
            failures.append(f"{identifier} references a lockfile outside the repository")
            continue
        try:
            cargo_lock = tomllib.loads(lockfile.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as error:
            failures.append(f"{identifier} cannot read {lockfile.relative_to(ROOT)}: {error}")
            continue
        dependency = str(exception["dependency"])
        version = str(exception["version"])
        matches = any(
            package.get("name") == dependency and package.get("version") == version
            for package in cargo_lock.get("package", [])
        )
        if not matches:
            failures.append(
                f"{identifier} no longer matches {dependency} {version} in "
                f"{lockfile.relative_to(ROOT).as_posix()}"
            )
    return failures


def main() -> int:
    args = parse_args()
    failures = validate_exceptions(args.manifest, args.today)
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1
    print(f"Security exceptions are valid through {args.today.isoformat()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
