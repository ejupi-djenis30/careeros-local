"""Validate narrowly scoped npm audit exceptions until upstream fixes are installable."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "frontend-security-exceptions.json"
SEVERITIES = {"high", "critical"}
ADVISORY_PATTERN = re.compile(r"^GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}$")
REQUIRED_FIELDS = {
    "id",
    "advisory",
    "dependency",
    "version",
    "package_lock",
    "guard",
    "scope",
    "patched_package",
    "patched_version",
    "expires",
    "reason",
}
EXPECTED_EXCEPTIONS = (
    {
        "id": "CE-NPM-2026-002",
        "advisory": "GHSA-qwww-vcr4-c8h2",
        "dependency": "react-router",
        "version": "7.18.1",
        "package_lock": "frontend/package-lock.json",
        "guard": "client-no-rsc",
        "scope": "Client-side DOM routing without React Server Components",
        "patched_package": "react-router-dom",
        "patched_version": "8.3.0",
        "expires": "2026-07-31",
        "reason": (
            "The advisory affects unstable RSC APIs that CareerOS does not import, and the "
            "patched npm package is not yet published."
        ),
    },
)
RSC_MARKERS = (
    "react-router/rsc",
    "@vitejs/plugin-rsc",
    "unstable_rsc",
    "rscstaticrouter",
    "rschydratedrouter",
    "matchrscserverrequest",
    "routerscserverrequest",
    "getrscstream",
    "rsc-action-id",
    "react-server",
    '"use server"',
    "'use server'",
)
SOURCE_SUFFIXES = {".cjs", ".cts", ".js", ".jsx", ".mjs", ".mts", ".ts", ".tsx"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--npm-audit-exit-code", type=int, required=True)
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=datetime.now(UTC).date(),
        help="Override the UTC date for deterministic verification.",
    )
    return parser.parse_args()


def _object(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(message)
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return _object(
            json.loads(path.read_text(encoding="utf-8")), f"{path} must contain a JSON object"
        )
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot read JSON from {path}: {error}") from error


def _advisory_id(via: dict[str, Any]) -> str:
    url = via.get("url")
    parsed = urllib.parse.urlparse(url) if isinstance(url, str) else None
    advisory = parsed.path.rsplit("/", 1)[-1] if parsed is not None else ""
    if (
        parsed is None
        or parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.path != f"/advisories/{advisory}"
        or parsed.params
        or parsed.query
        or parsed.fragment
        or not ADVISORY_PATTERN.fullmatch(advisory)
    ):
        raise RuntimeError(f"High-severity npm advisory has no canonical GHSA URL: {url!r}")
    return advisory


def collect_advisories(audit: dict[str, Any]) -> dict[str, dict[str, str]]:
    if audit.get("auditReportVersion") != 2:
        raise RuntimeError("Only npm audit report version 2 is supported")
    vulnerabilities = _object(audit.get("vulnerabilities"), "npm audit is missing vulnerabilities")
    metadata = _object(audit.get("metadata"), "npm audit is missing metadata")
    counts = _object(
        metadata.get("vulnerabilities"),
        "npm audit metadata is missing vulnerability counts",
    )
    calculated = {
        severity: sum(
            1
            for details in vulnerabilities.values()
            if isinstance(details, dict) and str(details.get("severity", "")).lower() == severity
        )
        for severity in SEVERITIES
    }
    for severity, count in calculated.items():
        if counts.get(severity) != count:
            raise RuntimeError(
                f"npm audit {severity} count is inconsistent: metadata={counts.get(severity)!r} "
                f"calculated={count}"
            )

    def resolve(package: str, seen: frozenset[str]) -> dict[str, dict[str, str]]:
        if package in seen:
            raise RuntimeError(f"npm audit contains a vulnerability cycle at {package}")
        details = _object(
            vulnerabilities.get(package), f"npm audit references unknown package {package}"
        )
        resolved: dict[str, dict[str, str]] = {}
        via_items = details.get("via")
        if not isinstance(via_items, list):
            raise RuntimeError(f"npm audit vulnerability {package} has no via list")
        for via in via_items:
            if isinstance(via, str):
                resolved.update(resolve(via, seen | {package}))
                continue
            via_object = _object(via, f"npm audit vulnerability {package} has an invalid via entry")
            severity = str(via_object.get("severity", "")).lower()
            if severity not in SEVERITIES:
                continue
            advisory = _advisory_id(via_object)
            if via_object.get("name") != package or via_object.get("dependency") != package:
                raise RuntimeError(f"npm advisory {advisory} does not match dependency {package}")
            nodes = details.get("nodes")
            if not isinstance(nodes, list) or f"node_modules/{package}" not in nodes:
                raise RuntimeError(f"npm advisory {advisory} does not identify its installed node")
            record = {"dependency": package, "severity": severity}
            previous = resolved.get(advisory)
            if previous is not None and previous != record:
                raise RuntimeError(f"npm advisory {advisory} resolves inconsistently")
            resolved[advisory] = record
        return resolved

    records: dict[str, dict[str, str]] = {}
    for package, details in vulnerabilities.items():
        details = _object(details, f"npm audit vulnerability {package} must be an object")
        if str(details.get("severity", "")).lower() not in SEVERITIES:
            continue
        nodes = details.get("nodes")
        if (
            not isinstance(nodes, list)
            or not nodes
            or not all(isinstance(node, str) for node in nodes)
        ):
            raise RuntimeError(f"npm audit vulnerability {package} has invalid nodes")
        resolved = resolve(package, frozenset())
        if not resolved:
            raise RuntimeError(
                f"High-severity npm vulnerability {package} has no resolvable advisory"
            )
        for advisory, record in resolved.items():
            previous = records.get(advisory)
            if previous is not None and previous != record:
                raise RuntimeError(f"npm advisory {advisory} resolves inconsistently")
            records[advisory] = record
    return records


def _repository_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise RuntimeError(f"Security exception path escapes the repository: {relative}")
    return path


def _verify_guard(root: Path, exception: dict[str, Any]) -> None:
    guard = exception["guard"]
    if guard != "client-no-rsc":
        raise RuntimeError(f"{exception['id']} declares an unknown guard: {guard}")

    package = _load_json(root / "frontend/package.json")
    dependency_names = set(
        _object(package.get("dependencies"), "frontend dependencies must be an object")
    )
    dependency_names.update(
        _object(package.get("devDependencies"), "frontend devDependencies must be an object")
    )
    forbidden_dependencies = sorted(
        name
        for name in dependency_names
        if name.startswith("@react-router/")
        or name.startswith("react-server-dom")
        or name == "@vitejs/plugin-rsc"
    )
    if forbidden_dependencies:
        raise RuntimeError(f"{exception['id']} cannot allow React Router server packages")

    source_root = root / "frontend/src"
    source_files = sorted(
        path
        for path in source_root.rglob("*")
        if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES
    )
    for entrypoint in (root / "frontend/vite.config.js", root / "frontend/index.html"):
        if entrypoint.is_file():
            source_files.append(entrypoint)
    if not source_files:
        raise RuntimeError(f"{exception['id']} cannot verify an empty frontend source tree")
    for path in source_files:
        if path.is_symlink():
            raise RuntimeError(
                f"{exception['id']} cannot verify symlinked source: "
                f"{path.relative_to(root).as_posix()}"
            )
        text = path.read_text(encoding="utf-8").lower()
        marker = next((candidate for candidate in RSC_MARKERS if candidate in text), None)
        if marker is not None:
            raise RuntimeError(
                f"{exception['id']} RSC guard failed in {path.relative_to(root).as_posix()}: {marker}"
            )
    main_source = (root / "frontend/src/main.jsx").read_text(encoding="utf-8")
    if "from 'react-dom/client'" not in main_source or "createRoot(" not in main_source:
        raise RuntimeError(f"{exception['id']} cannot prove the client-only React entrypoint")


def patched_version_available(package: str, version: str) -> bool:
    encoded = urllib.parse.quote(package, safe="")
    request = urllib.request.Request(
        f"https://registry.npmjs.org/{encoded}/{version}",
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "CareerOS-security-policy/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"npm registry returned unexpected status {response.status} for "
                    f"{package}@{version}"
                )
            try:
                metadata = _object(
                    json.load(response),
                    f"npm registry returned invalid metadata for {package}@{version}",
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise RuntimeError(
                    f"npm registry returned invalid JSON for {package}@{version}"
                ) from error
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise RuntimeError(
            f"npm registry verification failed for {package}@{version}: HTTP {error.code}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"npm registry verification failed for {package}@{version}: {error.reason}"
        ) from error
    if metadata.get("name") != package or metadata.get("version") != version:
        raise RuntimeError(f"npm registry returned mismatched metadata for {package}@{version}")
    dist = _object(
        metadata.get("dist"),
        f"npm registry metadata has no distribution for {package}@{version}",
    )
    tarball = dist.get("tarball")
    if not isinstance(tarball, str):
        raise RuntimeError(f"npm registry metadata has no tarball for {package}@{version}")
    parsed_tarball = urllib.parse.urlparse(tarball)
    if (
        parsed_tarball.scheme != "https"
        or parsed_tarball.hostname != "registry.npmjs.org"
        or not isinstance(dist.get("integrity") or dist.get("shasum"), str)
    ):
        raise RuntimeError(
            f"npm registry returned an untrusted distribution for {package}@{version}"
        )
    tarball_request = urllib.request.Request(
        tarball,
        headers={
            "Accept": "application/octet-stream",
            "Cache-Control": "no-cache",
            "Range": "bytes=0-0",
            "User-Agent": "CareerOS-security-policy/1",
        },
    )
    try:
        with closing(urllib.request.urlopen(tarball_request, timeout=15)) as response:
            if response.status not in {200, 206} or not response.read(1):
                raise RuntimeError(f"npm registry tarball is not readable for {package}@{version}")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise RuntimeError(
            f"npm registry tarball verification failed for {package}@{version}: HTTP {error.code}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"npm registry tarball verification failed for {package}@{version}: {error.reason}"
        ) from error
    return True


def validate_policy(
    audit: dict[str, Any],
    manifest: dict[str, Any],
    *,
    root: Path = ROOT,
    today: date,
    registry_checker: Callable[[str, str], bool] = patched_version_available,
) -> list[str]:
    if manifest.get("schema_version") != 1:
        raise RuntimeError("Frontend security exception schema version must be 1")
    raw_exceptions = manifest.get("exceptions")
    if not isinstance(raw_exceptions, list) or not raw_exceptions:
        raise RuntimeError("Frontend security exception manifest must contain exceptions")
    if raw_exceptions != list(EXPECTED_EXCEPTIONS):
        raise RuntimeError(
            "Frontend security exception manifest must contain only the reviewed "
            "React Router exception"
        )

    exceptions: dict[str, dict[str, Any]] = {}
    identifiers: set[str] = set()
    for index, value in enumerate(raw_exceptions):
        exception = _object(value, f"Frontend security exception {index} must be an object")
        if set(exception) != REQUIRED_FIELDS:
            missing = sorted(REQUIRED_FIELDS.difference(exception))
            extra = sorted(set(exception).difference(REQUIRED_FIELDS))
            raise RuntimeError(
                f"Frontend security exception {index} has missing={missing} extra={extra}"
            )
        identifier = str(exception["id"])
        advisory = str(exception["advisory"])
        if identifier in identifiers:
            raise RuntimeError(f"Duplicate frontend security exception id: {identifier}")
        if advisory in exceptions or not ADVISORY_PATTERN.fullmatch(advisory):
            raise RuntimeError(f"Duplicate or invalid frontend advisory: {advisory}")
        identifiers.add(identifier)
        exceptions[advisory] = exception

    advisories = collect_advisories(audit)
    if set(advisories) != set(exceptions):
        unknown = sorted(set(advisories).difference(exceptions))
        stale = sorted(set(exceptions).difference(advisories))
        raise RuntimeError(
            f"Frontend audit exception coverage differs: unknown={unknown} stale={stale}"
        )

    accepted: list[str] = []
    for advisory in sorted(advisories):
        record = advisories[advisory]
        exception = exceptions[advisory]
        if record["dependency"] != exception["dependency"]:
            raise RuntimeError(
                f"{advisory} moved from {exception['dependency']} to {record['dependency']}"
            )
        try:
            expiry = date.fromisoformat(str(exception["expires"]))
        except ValueError as error:
            raise RuntimeError(f"{exception['id']} has an invalid ISO expiry date") from error
        if today >= expiry:
            raise RuntimeError(f"{exception['id']} expired on {expiry.isoformat()}")
        for field in ("scope", "reason"):
            if not isinstance(exception[field], str) or not exception[field].strip():
                raise RuntimeError(f"{exception['id']} must explain its {field}")

        lock_path = _repository_path(root, str(exception["package_lock"]))
        lock = _load_json(lock_path)
        packages = _object(lock.get("packages"), f"{lock_path} has no packages map")
        metadata = _object(
            packages.get(f"node_modules/{exception['dependency']}"),
            f"{exception['id']} no longer exists in {lock_path.relative_to(root)}",
        )
        if metadata.get("version") != exception["version"]:
            raise RuntimeError(
                f"{exception['id']} no longer matches {exception['dependency']} "
                f"{exception['version']} in {lock_path.relative_to(root).as_posix()}"
            )
        _verify_guard(root, exception)
        if registry_checker(str(exception["patched_package"]), str(exception["patched_version"])):
            raise RuntimeError(
                f"{exception['id']} must be removed: {exception['patched_package']}@"
                f"{exception['patched_version']} is now available"
            )
        accepted.append(advisory)
    return accepted


def _run() -> None:
    args = parse_args()
    if args.npm_audit_exit_code not in {0, 1}:
        raise RuntimeError(
            f"npm audit failed operationally with exit code {args.npm_audit_exit_code}"
        )
    audit = _load_json(args.audit)
    accepted = validate_policy(
        audit,
        _load_json(args.manifest),
        today=args.today,
    )
    if accepted and args.npm_audit_exit_code != 1:
        raise RuntimeError("npm audit reported covered vulnerabilities without a failing exit code")
    if not accepted and args.npm_audit_exit_code != 0:
        raise RuntimeError("npm audit failed without a covered high-severity advisory")
    print(
        "Frontend npm exceptions accepted until patched packages are published: "
        + ", ".join(accepted)
    )


def main() -> int:
    try:
        _run()
    except RuntimeError as error:
        print(f"ERROR: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
