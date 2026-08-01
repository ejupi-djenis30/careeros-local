"""Canonical Agent Access wheel and lock release candidate contract."""

from __future__ import annotations

import base64
import configparser
import csv
import hashlib
import io
import json
import re
import shutil
import stat
import tomllib
import unicodedata
import zipfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.license_contract import approved_license_record
from scripts.release_assets import (
    PROJECT,
    file_record,
    reject_casefold_collisions,
    validate_source_commit,
    validate_stable_version,
)
from scripts.third_party_notices import NOTICE_NAME, verify_notice_bytes

AGENT_CANDIDATE_SCHEMA_VERSION = 1
AGENT_CANDIDATE_MANIFEST = "candidate-agent.json"
AGENT_REQUIREMENTS_LOCK = "requirements.lock"
AGENT_REQUIRES_PYTHON = ">=3.12,<3.14"
AGENT_WHEEL_TAG = "py3-none-any"
MAX_AGENT_WHEEL_SIZE = 64 * 1024 * 1024
MAX_AGENT_MEMBER_SIZE = 32 * 1024 * 1024
MAX_AGENT_MEMBERS = 4_096
MAX_AGENT_TOTAL_UNCOMPRESSED_SIZE = 128 * 1024 * 1024
MAX_AGENT_COMPRESSION_RATIO = 200
EXPECTED_ENTRY_POINTS = {
    "careeros": "backend.automation.cli:main",
    "careeros-mcp": "backend.automation.mcp_server:main",
}
REQUIRED_WHEEL_MEMBERS = {
    "backend/ai/fixtures/golden-1.0.0.json",
    "backend/ai/fixtures/golden-1.1.0.json",
    "backend/automation/cli.py",
    "backend/automation/mcp_server.py",
    "backend/data/skill_taxonomy.json",
    "backend/inference/model_catalog.json",
    "backend/inference/model_catalog.sha256",
    "backend/migrations/alembic.ini",
    "backend/migrations/script.py.mako",
    "desktop/backend_main.py",
}
FORBIDDEN_MEMBER_NAMES = {
    ".env",
    ".installation-secret",
    "careeros.db",
}
_WINDOWS_RESERVED_STEM = re.compile(
    r"^(?:CON|PRN|AUX|NUL|CLOCK\$|COM[1-9¹²³]|LPT[1-9¹²³])$",
    re.IGNORECASE,
)
_WINDOWS_FORBIDDEN_CHARACTERS = frozenset('<>:"|?*')


class _CaseSensitiveConfigParser(configparser.ConfigParser):
    def optionxform(self, optionstr: str) -> str:
        return optionstr


def canonical_agent_wheel_name(version: str) -> str:
    return f"careeros_local-{validate_stable_version(version)}-{AGENT_WHEEL_TAG}.whl"


def agent_public_names(version: str) -> tuple[str, str]:
    return canonical_agent_wheel_name(version), AGENT_REQUIREMENTS_LOCK


def _project_metadata(project_root: Path) -> tuple[str, list[str]]:
    with (project_root / "pyproject.toml").open("rb") as source:
        project = tomllib.load(source)["project"]
    requires_python = project.get("requires-python")
    dependencies = project.get("dependencies")
    if requires_python != AGENT_REQUIRES_PYTHON:
        raise RuntimeError(
            f"Agent Access requires-python drifted from {AGENT_REQUIRES_PYTHON}: "
            f"{requires_python!r}"
        )
    if not isinstance(dependencies, list) or not all(
        isinstance(dependency, str) for dependency in dependencies
    ):
        raise RuntimeError("pyproject.toml has no exact Agent Access dependency list")
    return requires_python, sorted(dependencies, key=str.casefold)


def _portable_member_key(info: zipfile.ZipInfo) -> tuple[str, tuple[str, ...]]:
    name = info.filename
    is_directory = info.is_dir()
    if (
        not name
        or "\\" in name
        or name.startswith("/")
        or any(unicodedata.category(character) == "Cc" for character in name)
    ):
        raise RuntimeError(f"Agent wheel has a non-portable member: {name!r}")
    if name.endswith("/") != is_directory:
        raise RuntimeError(f"Agent wheel has an ambiguous member type: {name!r}")
    path = name[:-1] if is_directory else name
    parts = tuple(path.split("/"))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise RuntimeError(f"Agent wheel has an unsafe member path: {name!r}")
    for part in parts:
        if unicodedata.normalize("NFC", part) != part:
            raise RuntimeError(f"Agent wheel has a non-canonical Unicode member: {name!r}")
        if any(character in _WINDOWS_FORBIDDEN_CHARACTERS for character in part) or part.endswith(
            (" ", ".")
        ):
            raise RuntimeError(f"Agent wheel has a Windows-unsafe member: {name!r}")
        windows_stem = part.split(".", 1)[0].rstrip(" .")
        if _WINDOWS_RESERVED_STEM.fullmatch(windows_stem):
            raise RuntimeError(f"Agent wheel has a Windows-reserved member: {name!r}")
    canonical_parts = tuple(part.casefold() for part in parts)
    return "/".join(canonical_parts), canonical_parts


def _member_names(archive: zipfile.ZipFile) -> tuple[list[str], dict[str, zipfile.ZipInfo]]:
    infos = archive.infolist()
    if not infos:
        raise RuntimeError("Agent wheel is empty")
    if len(infos) > MAX_AGENT_MEMBERS:
        raise RuntimeError(
            f"Agent wheel contains too many members: {len(infos)} > {MAX_AGENT_MEMBERS}"
        )
    by_name: dict[str, zipfile.ZipInfo] = {}
    aliases: dict[str, tuple[str, bool]] = {}
    total_uncompressed_size = 0
    total_compressed_size = 0
    for info in infos:
        name = info.filename
        key, canonical_parts = _portable_member_key(info)
        previous = aliases.get(key)
        if previous is not None:
            raise RuntimeError(f"Agent wheel has a portable path collision: {previous[0]} / {name}")
        for index in range(1, len(canonical_parts)):
            ancestor_key = "/".join(canonical_parts[:index])
            ancestor = aliases.get(ancestor_key)
            if ancestor is not None and not ancestor[1]:
                raise RuntimeError(
                    f"Agent wheel has a file/directory path collision: {ancestor[0]} / {name}"
                )
        if not info.is_dir():
            descendant_prefix = key + "/"
            descendant = next(
                (
                    alias_name
                    for alias_key, (alias_name, _is_directory) in aliases.items()
                    if alias_key.startswith(descendant_prefix)
                ),
                None,
            )
            if descendant is not None:
                raise RuntimeError(
                    f"Agent wheel has a file/directory path collision: {name} / {descendant}"
                )
        aliases[key] = (name, info.is_dir())
        if stat.S_ISLNK(info.external_attr >> 16):
            raise RuntimeError(f"Agent wheel contains a symbolic link: {name}")
        if info.file_size > MAX_AGENT_MEMBER_SIZE:
            raise RuntimeError(f"Agent wheel contains an oversized member: {name}")
        if info.file_size > MAX_AGENT_COMPRESSION_RATIO * max(1, info.compress_size):
            raise RuntimeError(f"Agent wheel contains a suspiciously compressed member: {name}")
        total_uncompressed_size += info.file_size
        total_compressed_size += info.compress_size
        if total_uncompressed_size > MAX_AGENT_TOTAL_UNCOMPRESSED_SIZE:
            raise RuntimeError("Agent wheel exceeds the uncompressed size limit")
        by_name[name] = info
    if total_uncompressed_size > MAX_AGENT_COMPRESSION_RATIO * max(1, total_compressed_size):
        raise RuntimeError("Agent wheel exceeds the aggregate compression ratio limit")
    return list(by_name), by_name


def _dist_info_prefix(names: list[str], version: str) -> str:
    prefix = f"careeros_local-{version}.dist-info/"
    prefixes = {
        name.split("/", 1)[0] + "/" for name in names if ".dist-info/" in name and "/" in name
    }
    if prefixes != {prefix}:
        raise RuntimeError(f"Agent wheel has an unexpected dist-info inventory: {sorted(prefixes)}")
    return prefix


def _metadata(
    archive: zipfile.ZipFile,
    *,
    prefix: str,
    version: str,
    project_root: Path,
) -> dict[str, Any]:
    message = BytesParser(policy=default).parsebytes(archive.read(prefix + "METADATA"))
    requires_python, expected_dependencies = _project_metadata(project_root)
    expected = {
        "Name": "careeros-local",
        "Version": version,
    }
    for name, value in expected.items():
        if message.get(name) != value:
            raise RuntimeError(f"Agent wheel METADATA has unexpected {name}: {message.get(name)!r}")
    wheel_requires_python = message.get("Requires-Python")
    if not isinstance(wheel_requires_python, str) or sorted(
        clause.strip() for clause in wheel_requires_python.split(",")
    ) != sorted(clause.strip() for clause in requires_python.split(",")):
        raise RuntimeError(
            f"Agent wheel METADATA has unexpected Requires-Python: {wheel_requires_python!r}"
        )
    dependencies = sorted(message.get_all("Requires-Dist", []), key=str.casefold)
    if dependencies != expected_dependencies:
        raise RuntimeError("Agent wheel dependency metadata differs from pyproject.toml")
    if message.get("License-Expression") != "MIT" and message.get("License") != "MIT":
        raise RuntimeError("Agent wheel does not declare the approved MIT license")
    return {
        "name": "careeros-local",
        "version": version,
        "requiresPython": requires_python,
        "dependencies": dependencies,
    }


def _wheel_metadata(archive: zipfile.ZipFile, *, prefix: str) -> None:
    message = BytesParser(policy=default).parsebytes(archive.read(prefix + "WHEEL"))
    if message.get("Wheel-Version") != "1.0":
        raise RuntimeError(f"Unsupported Agent wheel version: {message.get('Wheel-Version')!r}")
    if message.get("Root-Is-Purelib") != "true":
        raise RuntimeError("Agent wheel must be a pure-Python distribution")
    if message.get_all("Tag", []) != [AGENT_WHEEL_TAG]:
        raise RuntimeError(
            f"Agent wheel has unexpected compatibility tags: {message.get_all('Tag')}"
        )


def _entry_points(archive: zipfile.ZipFile, *, prefix: str) -> dict[str, str]:
    parser = _CaseSensitiveConfigParser(interpolation=None)
    parser.read_string(archive.read(prefix + "entry_points.txt").decode("utf-8"))
    if parser.sections() != ["console_scripts"]:
        raise RuntimeError(f"Agent wheel has unexpected entry-point groups: {parser.sections()}")
    entry_points = dict(parser.items("console_scripts"))
    if entry_points != EXPECTED_ENTRY_POINTS:
        raise RuntimeError(f"Agent wheel has unexpected console entry points: {entry_points}")
    return entry_points


def _required_resources(
    archive: zipfile.ZipFile,
    *,
    names: list[str],
    prefix: str,
    project_root: Path,
) -> None:
    files = {name for name in names if not name.endswith("/")}
    required = set(REQUIRED_WHEEL_MEMBERS)
    required.update(
        path.relative_to(project_root).as_posix()
        for path in (project_root / "backend" / "migrations" / "versions").glob("*.py")
    )
    missing = sorted(required - files)
    if missing:
        raise RuntimeError(f"Agent wheel is missing runtime resources: {missing}")
    top_levels = {PurePosixPath(name).parts[0] for name in files}
    if top_levels != {"backend", "desktop", prefix.removesuffix("/")}:
        raise RuntimeError(f"Agent wheel has unexpected top-level content: {sorted(top_levels)}")
    forbidden = sorted(
        name
        for name in files
        if PurePosixPath(name).name.casefold() in FORBIDDEN_MEMBER_NAMES
        or PurePosixPath(name).suffix.casefold() in {".db", ".sqlite", ".sqlite3"}
    )
    if forbidden:
        raise RuntimeError(f"Agent wheel contains private runtime state: {forbidden}")
    licenses = [name for name in files if name == prefix + "licenses/LICENSE"]
    if licenses != [prefix + "licenses/LICENSE"]:
        raise RuntimeError("Agent wheel must contain exactly one canonical LICENSE")
    expected_license = approved_license_record(project_root / "LICENSE")
    wheel_license = archive.read(licenses[0]).replace(b"\r\n", b"\n")
    if hashlib.sha256(wheel_license).hexdigest() != expected_license["sha256"]:
        raise RuntimeError("Agent wheel LICENSE differs from the approved project license")
    notices = [name for name in files if name == prefix + f"licenses/{NOTICE_NAME}"]
    if notices != [prefix + f"licenses/{NOTICE_NAME}"]:
        raise RuntimeError(f"Agent wheel must contain exactly one canonical {NOTICE_NAME}")
    wheel_notices = archive.read(notices[0]).replace(b"\r\n", b"\n")
    verify_notice_bytes(wheel_notices, root=project_root)
    if wheel_notices != (project_root / NOTICE_NAME).read_bytes():
        raise RuntimeError("Agent wheel third-party notices differ from the approved payload")


def _record(archive: zipfile.ZipFile, *, names: list[str], prefix: str) -> None:
    record_name = prefix + "RECORD"
    rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
    if not rows or any(len(row) != 3 for row in rows):
        raise RuntimeError("Agent wheel RECORD is malformed")
    indexed: dict[str, tuple[str, str]] = {}
    for name, digest, size in rows:
        if name in indexed:
            raise RuntimeError(f"Agent wheel RECORD contains a duplicate: {name}")
        indexed[name] = (digest, size)
    files = {name for name in names if not name.endswith("/")}
    if set(indexed) != files:
        raise RuntimeError("Agent wheel RECORD does not match its exact file inventory")
    for name in sorted(files):
        digest, size = indexed[name]
        if name == record_name:
            if digest or size:
                raise RuntimeError("Agent wheel RECORD must leave its own digest and size empty")
            continue
        payload = archive.read(name)
        expected_digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=")
        if digest != "sha256=" + expected_digest.decode("ascii") or size != str(len(payload)):
            raise RuntimeError(f"Agent wheel RECORD does not bind member bytes: {name}")


def validate_agent_wheel(path: Path, *, version: str, project_root: Path) -> dict[str, Any]:
    version = validate_stable_version(version)
    if path.name != canonical_agent_wheel_name(version):
        raise RuntimeError(f"Unexpected Agent wheel filename: {path.name}")
    record = file_record(path, artifact_type="python-wheel")
    if record["size"] > MAX_AGENT_WHEEL_SIZE:
        raise RuntimeError("Agent wheel exceeds the release size limit")
    if not zipfile.is_zipfile(path):
        raise RuntimeError("Agent wheel is not a valid ZIP archive")
    with zipfile.ZipFile(path) as archive:
        names, _infos = _member_names(archive)
        prefix = _dist_info_prefix(names, version)
        required_dist_info = {
            prefix + "METADATA",
            prefix + "WHEEL",
            prefix + "entry_points.txt",
            prefix + "RECORD",
            prefix + "licenses/LICENSE",
            prefix + f"licenses/{NOTICE_NAME}",
        }
        if not required_dist_info.issubset(names):
            raise RuntimeError(
                f"Agent wheel is missing dist-info files: {sorted(required_dist_info - set(names))}"
            )
        metadata = _metadata(archive, prefix=prefix, version=version, project_root=project_root)
        _wheel_metadata(archive, prefix=prefix)
        entry_points = _entry_points(archive, prefix=prefix)
        _required_resources(
            archive,
            names=names,
            prefix=prefix,
            project_root=project_root,
        )
        _record(archive, names=names, prefix=prefix)
    record["wheelTag"] = AGENT_WHEEL_TAG
    record["requiresPython"] = metadata["requiresPython"]
    record["entryPoints"] = entry_points
    return record


def _ensure_empty_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise RuntimeError(f"Agent candidate output directory must be empty: {path}")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def stage_agent_candidate(
    *,
    wheel_root: Path,
    requirements_lock: Path,
    output: Path,
    version: str,
    source_commit: str,
    project_root: Path,
) -> dict[str, Any]:
    version = validate_stable_version(version)
    source_commit = validate_source_commit(source_commit)
    if not wheel_root.is_dir():
        raise RuntimeError(f"Agent wheel root does not exist: {wheel_root}")
    entries = sorted(wheel_root.iterdir(), key=lambda path: path.name.casefold())
    if len(entries) != 1 or entries[0].name != canonical_agent_wheel_name(version):
        raise RuntimeError(
            f"Agent wheel root must contain exactly {canonical_agent_wheel_name(version)}"
        )
    source_wheel = entries[0]
    validate_agent_wheel(source_wheel, version=version, project_root=project_root)
    if requirements_lock.name != AGENT_REQUIREMENTS_LOCK:
        raise RuntimeError("Agent dependency lock must be named requirements.lock")
    lock_record = file_record(requirements_lock, artifact_type="python-requirements-lock")
    if b"--generate-hashes" not in requirements_lock.read_bytes():
        raise RuntimeError("Agent dependency lock is not the reviewed hash-locked graph")
    _ensure_empty_directory(output)
    wheel_destination = output / canonical_agent_wheel_name(version)
    lock_destination = output / AGENT_REQUIREMENTS_LOCK
    shutil.copy2(source_wheel, wheel_destination)
    shutil.copy2(requirements_lock, lock_destination)
    staged_wheel_record = validate_agent_wheel(
        wheel_destination, version=version, project_root=project_root
    )
    staged_lock_record = file_record(lock_destination, artifact_type="python-requirements-lock")
    manifest = {
        "schemaVersion": AGENT_CANDIDATE_SCHEMA_VERSION,
        "project": PROJECT,
        "version": version,
        "tag": f"v{version}",
        "sourceCommit": source_commit,
        "wheel": staged_wheel_record,
        "requirementsLock": staged_lock_record,
    }
    if staged_lock_record["sha256"] != lock_record["sha256"]:
        raise RuntimeError("Agent dependency lock changed while staging")
    _write_json(output / AGENT_CANDIDATE_MANIFEST, manifest)
    validate_agent_candidate(
        output,
        version=version,
        source_commit=source_commit,
        project_root=project_root,
        source_requirements_lock=requirements_lock,
    )
    return manifest


def validate_agent_candidate(
    directory: Path,
    *,
    version: str,
    source_commit: str,
    project_root: Path,
    source_requirements_lock: Path,
) -> dict[str, Any]:
    version = validate_stable_version(version)
    source_commit = validate_source_commit(source_commit)
    expected_files = sorted(
        [
            AGENT_CANDIDATE_MANIFEST,
            AGENT_REQUIREMENTS_LOCK,
            canonical_agent_wheel_name(version),
        ],
        key=str.casefold,
    )
    entries = sorted(directory.iterdir(), key=lambda path: path.name.casefold())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise RuntimeError("Agent candidate may contain regular files only")
    actual_files = [path.name for path in entries]
    reject_casefold_collisions(actual_files)
    if actual_files != expected_files:
        raise RuntimeError(f"Agent candidate has missing or unexpected files: {actual_files}")
    manifest = json.loads((directory / AGENT_CANDIDATE_MANIFEST).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise RuntimeError("Agent candidate manifest must be a JSON object")
    expected_header = {
        "schemaVersion": AGENT_CANDIDATE_SCHEMA_VERSION,
        "project": PROJECT,
        "version": version,
        "tag": f"v{version}",
        "sourceCommit": source_commit,
    }
    for key, value in expected_header.items():
        if manifest.get(key) != value:
            raise RuntimeError(
                f"Agent candidate manifest has unexpected {key}: {manifest.get(key)!r}"
            )
    wheel_record = validate_agent_wheel(
        directory / canonical_agent_wheel_name(version),
        version=version,
        project_root=project_root,
    )
    lock_record = file_record(
        directory / AGENT_REQUIREMENTS_LOCK,
        artifact_type="python-requirements-lock",
    )
    source_lock_record = file_record(
        source_requirements_lock,
        artifact_type="python-requirements-lock",
    )
    if lock_record["sha256"] != source_lock_record["sha256"]:
        raise RuntimeError("Agent candidate requirements.lock differs from the tagged source")
    if manifest.get("wheel") != wheel_record:
        raise RuntimeError("Agent candidate manifest does not match wheel bytes")
    if manifest.get("requirementsLock") != lock_record:
        raise RuntimeError("Agent candidate manifest does not match requirements.lock bytes")
    return manifest
