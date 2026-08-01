"""Restart-durable ownership records for content-addressed Career Vault assets."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.career.models import CareerAsset
from backend.core.config import settings
from backend.storage.atomic import (
    StorageWriteError,
    atomic_write,
    durable_unlink,
    read_stable_bounded_file,
    read_verified,
    resolve_data_path,
)

_JOURNAL_DIRECTORY = "assets/.publication-journal"
_JOURNAL_SCHEMA_VERSION = 1
_JOURNAL_MAX_BYTES = 16 * 1024
_JOURNAL_SCAN_LIMIT = 10_000
_RECOVERY_FILE_BYTES_LIMIT = 512 * 1024 * 1024
_JOURNAL_FIELDS = {
    "byte_size",
    "kind",
    "operation_id",
    "profile_id",
    "schema_version",
    "sha256",
    "storage_path",
}
_KINDS = {"profile_photo", "source_document"}


@dataclass(frozen=True, slots=True)
class AssetPublicationJournal:
    operation_id: str
    profile_id: str
    kind: str
    storage_path: str
    sha256: str
    byte_size: int
    relative_path: str


def _canonical_uuid(value: object, *, field: str) -> str:
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError(f"Invalid asset publication {field}")
    try:
        parsed = UUID(value)
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"Invalid asset publication {field}") from exc
    if str(parsed) != value:
        raise ValueError(f"Invalid asset publication {field}")
    return value


def _expected_storage_path(kind: str, sha256: str) -> str:
    if kind == "source_document":
        return f"assets/{sha256[:2]}/{sha256}"
    if kind == "profile_photo":
        return f"assets/photos/{sha256[:2]}/{sha256}.jpg"
    raise ValueError("Invalid asset publication kind")


def _validated_payload(payload: object, *, filename: str) -> AssetPublicationJournal:
    if not isinstance(payload, dict) or set(payload) != _JOURNAL_FIELDS:
        raise ValueError("Invalid asset publication journal")
    operation_id = _canonical_uuid(payload.get("operation_id"), field="operation id")
    profile_id = _canonical_uuid(payload.get("profile_id"), field="profile id")
    kind = payload.get("kind")
    sha256 = payload.get("sha256")
    byte_size = payload.get("byte_size")
    storage_path = payload.get("storage_path")
    if (
        payload.get("schema_version") != _JOURNAL_SCHEMA_VERSION
        or kind not in _KINDS
        or not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
        or isinstance(byte_size, bool)
        or not isinstance(byte_size, int)
        or not 0 < byte_size <= settings.MAX_UPLOAD_FILE_SIZE
        or not isinstance(storage_path, str)
        or storage_path != _expected_storage_path(kind, sha256)
        or filename != f"{operation_id}.json"
    ):
        raise ValueError("Invalid asset publication journal")
    resolve_data_path(storage_path, create_root=False)
    return AssetPublicationJournal(
        operation_id=operation_id,
        profile_id=profile_id,
        kind=kind,
        storage_path=storage_path,
        sha256=sha256,
        byte_size=byte_size,
        relative_path=f"{_JOURNAL_DIRECTORY}/{filename}",
    )


def _is_reparse_point(metadata: os.stat_result) -> bool:
    return bool(int(getattr(metadata, "st_file_attributes", 0)) & 0x400)


def _read_stable_journal_bytes(path: Path) -> bytes:
    payload = read_stable_bounded_file(path, maximum_size=_JOURNAL_MAX_BYTES)
    if not payload:
        raise ValueError("Invalid asset publication journal file")
    return payload


def _load_journal(path: Path) -> AssetPublicationJournal:
    try:
        payload = json.loads(_read_stable_journal_bytes(path).decode("utf-8"))
        return _validated_payload(payload, filename=path.name)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise StorageWriteError(
            "Asset publication recovery metadata is invalid; verify the local data directory."
        ) from exc


def all_asset_publication_journals() -> list[AssetPublicationJournal]:
    """Load one bounded, fully validated snapshot of the journal namespace."""

    directory = resolve_data_path(_JOURNAL_DIRECTORY, create_root=False)
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        return []
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse_point(metadata)
    ):
        raise StorageWriteError(
            "Asset publication recovery metadata is invalid; verify the local data directory."
        )
    paths: list[Path] = []
    try:
        for count, path in enumerate(directory.iterdir(), start=1):
            if count > _JOURNAL_SCAN_LIMIT:
                raise StorageWriteError("Too many pending asset publication recovery records")
            if path.suffix != ".json":
                raise StorageWriteError(
                    "Asset publication recovery metadata is invalid; "
                    "verify the local data directory."
                )
            paths.append(path)
    except StorageWriteError:
        raise
    except OSError as exc:
        raise StorageWriteError(
            "Asset publication recovery metadata could not be scanned; "
            "verify the local data directory."
        ) from exc
    return [_load_journal(path) for path in sorted(paths)]


def write_asset_publication_journal(
    *,
    operation_id: str,
    profile_id: str,
    kind: str,
    storage_path: str,
    sha256: str,
    byte_size: int,
) -> str:
    """Durably claim a prospective asset path before publishing its bytes."""

    filename = f"{operation_id}.json"
    validated = _validated_payload(
        {
            "byte_size": byte_size,
            "kind": kind,
            "operation_id": operation_id,
            "profile_id": profile_id,
            "schema_version": _JOURNAL_SCHEMA_VERSION,
            "sha256": sha256,
            "storage_path": storage_path,
        },
        filename=filename,
    )
    payload = json.dumps(
        {
            "byte_size": validated.byte_size,
            "kind": validated.kind,
            "operation_id": validated.operation_id,
            "profile_id": validated.profile_id,
            "schema_version": _JOURNAL_SCHEMA_VERSION,
            "sha256": validated.sha256,
            "storage_path": validated.storage_path,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    atomic_write(validated.relative_path, payload)
    return validated.relative_path


def remove_asset_publication_journal(relative_path: str) -> bool:
    expected_parent = resolve_data_path(_JOURNAL_DIRECTORY, create_root=False)
    path = resolve_data_path(relative_path, create_root=False)
    if path.parent != expected_parent or path.suffix != ".json":
        raise ValueError("Invalid asset publication journal path")
    return durable_unlink(path)


def _committed_asset_metadata(
    db: Session, storage_paths: set[str]
) -> dict[str, set[tuple[str, int]]]:
    committed: dict[str, set[tuple[str, int]]] = {}
    ordered = sorted(storage_paths)
    for offset in range(0, len(ordered), 500):
        batch = ordered[offset : offset + 500]
        for storage_path, sha256, byte_size in (
            db.query(CareerAsset.storage_path, CareerAsset.sha256, CareerAsset.byte_size)
            .filter(CareerAsset.storage_path.in_(batch))
            .all()
        ):
            committed.setdefault(storage_path, set()).add((sha256, byte_size))
    return committed


def reconcile_asset_publication_journals(db: Session) -> int:
    """Reconcile crash-left journals while the caller holds SQLite's writer lock."""

    if db.get_bind().dialect.name != "sqlite" or not db.in_transaction():
        raise StorageWriteError("Asset publication recovery requires the SQLite writer lock")
    journals = all_asset_publication_journals()
    if not journals:
        return 0

    grouped: dict[str, list[AssetPublicationJournal]] = {}
    for journal in journals:
        grouped.setdefault(journal.storage_path, []).append(journal)
    expected: dict[str, tuple[str, int]] = {}
    for storage_path, claims in grouped.items():
        metadata = {(claim.sha256, claim.byte_size) for claim in claims}
        if len(metadata) != 1:
            raise StorageWriteError("Asset publication recovery claims conflict")
        expected[storage_path] = metadata.pop()
    if sum(byte_size for _sha256, byte_size in expected.values()) > _RECOVERY_FILE_BYTES_LIMIT:
        raise StorageWriteError("Pending asset publication recovery bytes exceed the safety limit")

    committed = _committed_asset_metadata(db, set(grouped))
    existing_files: set[str] = set()
    for storage_path, (sha256, byte_size) in expected.items():
        committed_metadata = committed.get(storage_path, set())
        if committed_metadata and committed_metadata != {(sha256, byte_size)}:
            raise StorageWriteError("Committed asset metadata conflicts with recovery metadata")
        absolute_path = resolve_data_path(storage_path, create_root=False)
        try:
            absolute_path.lstat()
        except FileNotFoundError:
            if committed_metadata:
                raise StorageWriteError("A committed asset is missing its durable bytes")
            continue
        try:
            read_verified(
                storage_path,
                sha256,
                expected_size=byte_size,
                maximum_size=settings.MAX_UPLOAD_FILE_SIZE,
            )
        except (OSError, ValueError) as exc:
            raise StorageWriteError("Asset publication recovery bytes failed validation") from exc
        existing_files.add(storage_path)

    for storage_path, claims in grouped.items():
        if storage_path not in committed and storage_path in existing_files:
            durable_unlink(resolve_data_path(storage_path, create_root=False))
        for claim in claims:
            remove_asset_publication_journal(claim.relative_path)
    return len(journals)


def begin_asset_publication_write(db: Session) -> int:
    """End any read snapshot, reserve SQLite's writer, and reconcile old claims."""

    if db.get_bind().dialect.name != "sqlite":
        raise StorageWriteError("Asset publication requires the local SQLite vault")
    db.rollback()
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        return reconcile_asset_publication_journals(db)
    except Exception:
        db.rollback()
        raise
