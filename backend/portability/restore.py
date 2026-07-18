from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, or_, update
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from backend.applications.models import Application
from backend.career.models import CandidateProfile
from backend.core.config import settings
from backend.desktop.lifecycle import VaultLockTimeout, desktop_vault_lock
from backend.models import Job, ScrapedJob, SearchProfile, User
from backend.portability.archive import (
    EXPORT_MODELS,
    SCRAPED_JOB_PRIVATE_FIELDS,
    SEARCH_PROFILE_RUNTIME_FIELDS,
    ArchiveConflictError,
    ArchiveError,
    _json_value,
    _validated_members,
)
from backend.portability.manifest import (
    CURRENT_ARCHIVE_VERSION,
    PAYLOAD_MEMBER,
    expected_tables,
    sha256,
)
from backend.portability.schemas import ArchiveManifest, RestoreResponse
from backend.storage.atomic import atomic_write, resolve_data_path
from backend.workflows.models import WorkflowRun

FILE_TABLES = frozenset({"career_assets", "resume_artifacts"})
USER_SCOPED_TABLES = frozenset(
    {
        "candidate_profiles",
        "search_profiles",
        "jobs",
        "applications",
        "workflow_runs",
        "ai_executions",
    }
)
REMAPPABLE_TABLES = frozenset({"search_profiles", "scraped_jobs", "jobs"})
PREFERENCE_FIELDS = frozenset({"preference_signals", "preference_updated_at"})


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


def _assert_unique_archive_ids(
    table_name: str, rows: list[dict[str, Any]]
) -> None:
    ids: list[Any] = []
    for row in rows:
        record_id = row.get("id")
        if record_id is None:
            raise ArchiveError(f"Archive {table_name} row is missing its ID")
        try:
            hash(record_id)
        except TypeError as exc:
            raise ArchiveError(f"Archive {table_name} row has an invalid ID") from exc
        ids.append(record_id)
    if len(ids) != len(set(ids)):
        raise ArchiveError(f"Archive {table_name} contains duplicate IDs")


def _decode_preference_state(
    format_version: int, tables: dict[str, Any]
) -> dict[str, Any] | None:
    if format_version < 3:
        return None
    rows = tables["preference_signals"]
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ArchiveError("A version 3 archive must contain one preference signal record")
    if set(rows[0]) != PREFERENCE_FIELDS:
        raise ArchiveError("The preference signal record contains unsupported fields")
    decoded = _decode_row(User, rows[0])
    if decoded["preference_signals"] is not None and not isinstance(
        decoded["preference_signals"], dict
    ):
        raise ArchiveError("Preference signals must be an object or null")
    if decoded["preference_updated_at"] is not None and not isinstance(
        decoded["preference_updated_at"], datetime
    ):
        raise ArchiveError("Preference signal timestamp must be an ISO timestamp or null")
    return decoded


def _integer_ids(table_name: str, rows: list[dict[str, Any]]) -> set[int]:
    ids: set[int] = set()
    for row in rows:
        record_id = row.get("id")
        if not isinstance(record_id, int) or isinstance(record_id, bool) or record_id <= 0:
            raise ArchiveError(f"Archive {table_name} row has an invalid integer ID")
        ids.add(record_id)
    return ids


def _validate_search_relationships(
    format_version: int, decoded: dict[str, list[dict[str, Any]]]
) -> None:
    if format_version < 3:
        return
    profile_ids = _integer_ids("search_profiles", decoded["search_profiles"])
    scraped_job_ids = _integer_ids("scraped_jobs", decoded["scraped_jobs"])
    job_ids = _integer_ids("jobs", decoded["jobs"])
    listing_keys: set[tuple[str, str]] = set()
    for row in decoded["scraped_jobs"]:
        platform = row.get("platform")
        platform_job_id = row.get("platform_job_id")
        if not isinstance(platform, str) or not platform or not isinstance(
            platform_job_id, str
        ) or not platform_job_id:
            raise ArchiveError("Archive scraped listing is missing its provider identity")
        key = (platform, platform_job_id)
        if key in listing_keys:
            raise ArchiveError("Archive contains duplicate scraped listing identities")
        listing_keys.add(key)
    for row in decoded["jobs"]:
        profile_id = row.get("search_profile_id")
        scraped_job_id = row.get("scraped_job_id")
        if profile_id is not None and profile_id not in profile_ids:
            raise ArchiveError("Archive job references a missing search profile")
        if scraped_job_id not in scraped_job_ids:
            raise ArchiveError("Archive job references a missing scraped listing")
    for row in decoded["applications"]:
        job_id = row.get("job_id")
        if job_id is not None and job_id not in job_ids:
            raise ArchiveError("Archive application references a missing job")


def _decode_payload(
    db: Session,
    manifest: ArchiveManifest,
    members: dict[str, bytes],
) -> tuple[
    dict[str, list[dict[str, Any]]],
    list[dict[str, Any]],
    dict[str, Any] | None,
]:
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
        if table_name == "scraped_jobs":
            # Version 3 archives created before the privacy hardening included
            # this shared-model field. Accept those archives, but never carry
            # their user-specific discovery query into the restored database.
            for row in decoded[table_name]:
                for field in SCRAPED_JOB_PRIVATE_FIELDS:
                    row.pop(field, None)
        _assert_unique_archive_ids(table_name, decoded[table_name])
        if table_name not in REMAPPABLE_TABLES:
            _assert_ids_available(db, model, decoded[table_name])
    preference_state = _decode_preference_state(manifest.format_version, tables)
    _validate_search_relationships(manifest.format_version, decoded)
    return decoded, bindings, preference_state


def _assert_empty_vault(db: Session, user_id: int, format_version: int) -> None:
    checks = (
        (CandidateProfile, CandidateProfile.user_id, "career vault"),
        (SearchProfile, SearchProfile.user_id, "search profile history"),
        (Job, Job.user_id, "job history"),
        (Application, Application.user_id, "application history"),
        (WorkflowRun, WorkflowRun.user_id, "workflow history"),
    )
    for model, user_column, label in checks:
        if db.query(model).filter(user_column == user_id).first() is not None:
            raise ArchiveConflictError(f"Restore requires an empty {label}")
    if format_version >= 3:
        owner = db.get(User, user_id)
        if owner is None:
            raise ArchiveError("The local vault owner does not exist")
        if owner.preference_signals is not None or owner.preference_updated_at is not None:
            raise ArchiveConflictError("Restore requires empty preference signals")


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


def _prepare_row(
    table_name: str,
    row: dict[str, Any],
    user_id: int,
    *,
    format_version: int,
    job_id_map: dict[int, int],
) -> None:
    if table_name in USER_SCOPED_TABLES:
        row["user_id"] = user_id
    if table_name == "applications":
        archived_job_id = row.get("job_id")
        row["job_id"] = (
            job_id_map[archived_job_id]
            if format_version >= 3 and archived_job_id is not None
            else None
        )
    if table_name == "workflow_runs":
        row["lease_owner"] = None
        row["lease_expires_at"] = None
        if row.get("status") == "completed":
            row["status"] = "succeeded"
        elif row.get("status") not in {"succeeded", "failed", "cancelled"}:
            row["status"] = "cancelled"
            row["error_code"] = "restored_without_execution"


def _add_remappable_row(
    db: Session, model: type[Any], row: dict[str, Any]
) -> Any:
    prepared = dict(row)
    archived_id = prepared["id"]
    if db.get(model, archived_id) is not None:
        prepared.pop("id")
    instance = model(**prepared)
    db.add(instance)
    db.flush()
    return instance


def _shared_listing_content(record: ScrapedJob | dict[str, Any]) -> dict[str, Any]:
    ignored = {"id", "created_at", "updated_at", *SCRAPED_JOB_PRIVATE_FIELDS}
    return {
        column.name: _json_value(
            record.get(column.name)
            if isinstance(record, dict)
            else getattr(record, column.name)
        )
        for column in ScrapedJob.__table__.columns
        if column.name not in ignored
    }


def _restore_search_records(
    db: Session,
    user_id: int,
    decoded: dict[str, list[dict[str, Any]]],
) -> dict[int, int]:
    profile_id_map: dict[int, int] = {}
    for row in decoded["search_profiles"]:
        prepared = dict(row)
        archived_id = prepared["id"]
        prepared["user_id"] = user_id
        for field in SEARCH_PROFILE_RUNTIME_FIELDS:
            prepared[field] = None
        restored = _add_remappable_row(db, SearchProfile, prepared)
        profile_id_map[archived_id] = restored.id

    scraped_job_id_map: dict[int, int] = {}
    for row in decoded["scraped_jobs"]:
        archived_id = row["id"]
        existing = (
            db.query(ScrapedJob)
            .filter(
                ScrapedJob.platform == row.get("platform"),
                ScrapedJob.platform_job_id == row.get("platform_job_id"),
            )
            .one_or_none()
        )
        if existing is not None:
            if (
                existing.source_query is not None
                or _shared_listing_content(existing) != _shared_listing_content(row)
            ):
                raise ArchiveConflictError(
                    "A shared scraped listing already exists with private or different content"
                )
            restored = existing
        else:
            restored = _add_remappable_row(db, ScrapedJob, row)
        scraped_job_id_map[archived_id] = restored.id

    job_id_map: dict[int, int] = {}
    for row in decoded["jobs"]:
        prepared = dict(row)
        archived_id = prepared["id"]
        prepared["user_id"] = user_id
        profile_id = prepared.get("search_profile_id")
        prepared["search_profile_id"] = (
            profile_id_map[profile_id] if profile_id is not None else None
        )
        prepared["scraped_job_id"] = scraped_job_id_map[prepared["scraped_job_id"]]
        restored = _add_remappable_row(db, Job, prepared)
        job_id_map[archived_id] = restored.id
    return job_id_map


def _restore_preference_state(
    db: Session, user_id: int, preference_state: dict[str, Any] | None
) -> None:
    if preference_state is None:
        return
    result = db.execute(
        update(User)
        .where(
            User.id == user_id,
            or_(
                User.preference_signals.is_(None),
                User.preference_signals == JSON.NULL,
            ),
            User.preference_updated_at.is_(None),
        )
        .values(
            preference_signals=preference_state["preference_signals"],
            preference_updated_at=preference_state["preference_updated_at"],
        )
        .execution_options(synchronize_session=False)
    )
    if getattr(result, "rowcount", 0) != 1:
        raise ArchiveConflictError("Restore requires empty preference signals")


def _restore_transaction(
    db: Session,
    user_id: int,
    format_version: int,
    decoded: dict[str, list[dict[str, Any]]],
    preference_state: dict[str, Any] | None,
    writes: list[tuple[str, bytes]],
) -> None:
    created_paths: list[str] = []
    try:
        for relative_path, file_data in writes:
            _path, created = atomic_write(relative_path, file_data)
            if created:
                created_paths.append(relative_path)
        job_id_map = _restore_search_records(db, user_id, decoded)
        for table_name, model in EXPORT_MODELS:
            if table_name in REMAPPABLE_TABLES:
                continue
            for row in decoded[table_name]:
                _prepare_row(
                    table_name,
                    row,
                    user_id,
                    format_version=format_version,
                    job_id_map=job_id_map,
                )
                db.add(model(**row))
            db.flush()
        _restore_preference_state(db, user_id, preference_state)
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
            _assert_empty_vault(db, user_id, manifest.format_version)
            decoded, bindings, preference_state = _decode_payload(db, manifest, members)
            writes = _prepare_file_writes(decoded, bindings, members)
            _restore_transaction(
                db,
                user_id,
                manifest.format_version,
                decoded,
                preference_state,
                writes,
            )
    except VaultLockTimeout as exc:
        raise ArchiveConflictError(str(exc)) from exc

    restored_records = {
        name: manifest.record_counts.get(name, 0)
        for name in expected_tables(CURRENT_ARCHIVE_VERSION)
    }
    return RestoreResponse(
        format_version=manifest.format_version,
        archive_sha256=sha256(data),
        restored_records=restored_records,
        restored_files=len(writes),
    )
