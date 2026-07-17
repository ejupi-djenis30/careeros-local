from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from backend.applications.models import Application
from backend.career.models import CandidateProfile
from backend.core.config import settings
from backend.desktop.lifecycle import VaultLockTimeout, desktop_vault_lock
from backend.portability.archive import (
    EXPORT_MODELS,
    ArchiveConflictError,
    ArchiveError,
    _validated_members,
)
from backend.portability.manifest import PAYLOAD_MEMBER, expected_tables, sha256
from backend.portability.schemas import ArchiveManifest, RestoreResponse
from backend.storage.atomic import atomic_write, resolve_data_path
from backend.workflows.models import WorkflowRun

FILE_TABLES = frozenset({"career_assets", "resume_artifacts"})
USER_SCOPED_TABLES = frozenset(
    {"candidate_profiles", "applications", "workflow_runs", "ai_executions"}
)


def _decode_row(model: type[Any], row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ArchiveError("Archive table rows must be objects")
    columns = {column.name: column for column in model.__table__.columns}
    unknown = set(row) - set(columns)
    if unknown:
        raise ArchiveError(f"Archive row contains unsupported fields: {sorted(unknown)}")
    decoded = dict(row)
    for key, value in list(decoded.items()):
        column_type = columns[key].type
        if value is None:
            continue
        if isinstance(column_type, DateTime) and isinstance(value, str):
            try:
                decoded[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ArchiveError(
                    f"Invalid timestamp in {model.__tablename__}.{key}"
                ) from exc
        elif isinstance(column_type, Date) and isinstance(value, str):
            try:
                decoded[key] = date.fromisoformat(value)
            except ValueError as exc:
                raise ArchiveError(f"Invalid date in {model.__tablename__}.{key}") from exc
    return decoded


def _assert_ids_available(
    db: Session, model: type[Any], rows: list[dict[str, Any]]
) -> None:
    ids = [str(row["id"]) for row in rows if row.get("id")]
    for start in range(0, len(ids), 400):
        if db.query(model).filter(model.id.in_(ids[start : start + 400])).first() is not None:
            raise ArchiveConflictError(f"Archive IDs already exist in {model.__tablename__}")


def _decode_payload(
    db: Session,
    manifest: ArchiveManifest,
    members: dict[str, bytes],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    try:
        payload = json.loads(members[PAYLOAD_MEMBER])
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ArchiveError("The archive payload is invalid") from exc
    tables = payload.get("tables")
    bindings = payload.get("file_bindings")
    if not isinstance(tables, dict) or not isinstance(bindings, list):
        raise ArchiveError("The archive payload structure is invalid")

    version_tables = expected_tables(manifest.format_version)
    if set(tables) != version_tables:
        raise ArchiveError("The archive contains an unsupported table set")
    total_records = sum(len(value) for value in tables.values() if isinstance(value, list))
    if total_records > settings.PORTABLE_ARCHIVE_MAX_RECORDS:
        raise ArchiveError("The archive contains too many records")
    for name in version_tables:
        if not isinstance(tables[name], list) or len(tables[name]) != manifest.record_counts[name]:
            raise ArchiveError(f"Archive record count mismatch for {name}")
    if len(tables["candidate_profiles"]) != 1:
        raise ArchiveError("A portable career archive must contain exactly one profile")

    decoded: dict[str, list[dict[str, Any]]] = {}
    for table_name, model in EXPORT_MODELS:
        decoded[table_name] = [
            _decode_row(model, row) for row in tables.get(table_name, [])
        ]
        _assert_ids_available(db, model, decoded[table_name])
    return decoded, bindings


def _assert_empty_vault(db: Session, user_id: int) -> None:
    checks = (
        (CandidateProfile, CandidateProfile.user_id, "career vault"),
        (Application, Application.user_id, "application history"),
        (WorkflowRun, WorkflowRun.user_id, "workflow history"),
    )
    for model, user_column, label in checks:
        if db.query(model).filter(user_column == user_id).first() is not None:
            raise ArchiveConflictError(f"Restore requires an empty {label}")


def _prepare_file_writes(
    decoded: dict[str, list[dict[str, Any]]],
    bindings: list[dict[str, Any]],
    members: dict[str, bytes],
) -> list[tuple[str, bytes]]:
    records = {
        (table_name, str(row.get("id"))): row
        for table_name in FILE_TABLES
        for row in decoded[table_name]
    }
    actual_keys: set[tuple[str, str]] = set()
    writes: list[tuple[str, bytes]] = []
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ArchiveError("Archive file binding is invalid")
        table_value = binding.get("table")
        record_value = binding.get("record_id")
        member_value = binding.get("member")
        if not all(
            isinstance(value, str) for value in (table_value, record_value, member_value)
        ):
            raise ArchiveError("Archive file binding fields must be strings")
        assert isinstance(table_value, str)
        assert isinstance(record_value, str)
        assert isinstance(member_value, str)
        table_name, record_id, member = table_value, record_value, member_value
        key = (table_name, record_id)
        record = records.get(key)
        if record is None or key in actual_keys:
            raise ArchiveError("Archive file binding does not reference one unique record")
        if binding.get("storage_path") != record.get("storage_path"):
            raise ArchiveError("Archive storage path does not match its record")
        if member not in members or member == PAYLOAD_MEMBER:
            raise ArchiveError("Archive file binding references a missing member")
        file_data = members[member]
        if sha256(file_data) != record.get("sha256") or len(file_data) != record.get(
            "byte_size"
        ):
            raise ArchiveError("Archived file does not match its database record")
        try:
            resolve_data_path(str(record["storage_path"]))
        except ValueError as exc:
            raise ArchiveError("Archive contains an unsafe storage path") from exc
        writes.append((str(record["storage_path"]), file_data))
        actual_keys.add(key)

    if actual_keys != set(records):
        raise ArchiveError("Archive is missing one or more persisted file bindings")
    if set(members) != {str(binding.get("member")) for binding in bindings} | {
        PAYLOAD_MEMBER
    }:
        raise ArchiveError("Archive contains unbound file members")
    return writes


def _prepare_row(table_name: str, row: dict[str, Any], user_id: int) -> None:
    if table_name in USER_SCOPED_TABLES:
        row["user_id"] = user_id
    if table_name == "applications":
        row["job_id"] = None
    if table_name == "workflow_runs":
        row["lease_owner"] = None
        row["lease_expires_at"] = None
        if row.get("status") == "completed":
            row["status"] = "succeeded"
        elif row.get("status") not in {"succeeded", "failed", "cancelled"}:
            row["status"] = "cancelled"
            row["error_code"] = "restored_without_execution"


def _restore_transaction(
    db: Session,
    user_id: int,
    decoded: dict[str, list[dict[str, Any]]],
    writes: list[tuple[str, bytes]],
) -> None:
    created_paths: list[str] = []
    try:
        for relative_path, file_data in writes:
            _path, created = atomic_write(relative_path, file_data)
            if created:
                created_paths.append(relative_path)
        for table_name, model in EXPORT_MODELS:
            for row in decoded[table_name]:
                _prepare_row(table_name, row, user_id)
                db.add(model(**row))
            db.flush()
        db.commit()
    except (IntegrityError, StatementError) as exc:
        db.rollback()
        for relative_path in created_paths:
            resolve_data_path(relative_path).unlink(missing_ok=True)
        raise ArchiveError("Archive records failed relational validation") from exc
    except Exception:
        db.rollback()
        for relative_path in created_paths:
            resolve_data_path(relative_path).unlink(missing_ok=True)
        raise


def restore_archive(db: Session, user_id: int, data: bytes) -> RestoreResponse:
    try:
        with desktop_vault_lock():
            manifest, members = _validated_members(data)
            _assert_empty_vault(db, user_id)
            decoded, bindings = _decode_payload(db, manifest, members)
            writes = _prepare_file_writes(decoded, bindings, members)
            _restore_transaction(db, user_id, decoded, writes)
    except VaultLockTimeout as exc:
        raise ArchiveConflictError(str(exc)) from exc

    restored_records = dict(manifest.record_counts)
    if manifest.format_version == 1:
        restored_records["ai_executions"] = 0
    return RestoreResponse(
        format_version=manifest.format_version,
        archive_sha256=sha256(data),
        restored_records=restored_records,
        restored_files=len(writes),
    )
