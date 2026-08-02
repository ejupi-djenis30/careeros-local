from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

from sqlalchemy import JSON, Date, DateTime, or_, text, update
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from backend.applications.models import Application
from backend.applications.schemas import ApplicationDossierDraftContent
from backend.applications.service import (
    ApplicationService,
    ApplicationValidationError,
)
from backend.applications.snapshots import sanitize_application_snapshot
from backend.automation.models import AutomationGrant
from backend.career.deletion import (
    _enable_sqlite_secure_delete,
    _exclusive_restore_journal_paths,
    _sanitize_sqlite_storage,
)
from backend.career.models import CandidateProfile, CareerAsset
from backend.core.config import settings
from backend.db.types import UTCDateTime, aware_utc
from backend.desktop.lifecycle import VaultLockTimeout, desktop_vault_lock
from backend.models import Job, ScrapedJob, SearchProfile, User
from backend.models.auth_session import AuthSession
from backend.models.user import VAULT_STATE_READY
from backend.portability.archive import (
    EXPORT_MODELS,
    SCRAPED_JOB_PRIVATE_FIELDS,
    SEARCH_PROFILE_RUNTIME_FIELDS,
    ArchiveConflictError,
    ArchiveError,
    _json_value,
    _validated_members,
)
from backend.portability.journal import (
    RestoreJournalError,
    atomic_restore_write,
    clear_restore_journal,
    prepare_restore_journal,
    read_restore_journal,
)
from backend.portability.manifest import (
    CURRENT_ARCHIVE_VERSION,
    PAYLOAD_MEMBER,
    expected_tables,
    sha256,
)
from backend.portability.schemas import ArchiveManifest, RestoreResponse
from backend.providers.configuration.html_extract import validate_selector
from backend.providers.configuration.models import JobProviderConfiguration
from backend.providers.configuration.native import validate_native_adapter_id
from backend.providers.configuration.network_policy import validate_destination_literal
from backend.providers.configuration.schemas import (
    ProviderCapabilitiesConfig,
    ProviderConfigurationInput,
    secret_header,
)
from backend.resumes.artifact_policy import MAX_RESUME_ARTIFACT_BYTES
from backend.resumes.models import ResumeArtifact, ResumeDraft, ResumeVersion
from backend.search.receipt import (
    SEARCH_RECEIPT_MAX_COUNTER,
    normalize_search_completion_summary,
)
from backend.storage.atomic import (
    durable_unlink,
    read_stable_bounded_file,
    resolve_data_path,
)
from backend.workflows.models import WorkflowRun

logger = logging.getLogger(__name__)

FILE_TABLES = frozenset({"career_assets", "resume_artifacts"})
USER_SCOPED_TABLES = frozenset(
    {
        "candidate_profiles",
        "job_provider_configurations",
        "search_profiles",
        "jobs",
        "applications",
        "workflow_runs",
        "ai_executions",
    }
)


class RestoreRolledBackError(RuntimeError):
    """A restore failed, but every durable side effect was removed and sanitized."""

    def __init__(self, original: Exception) -> None:
        super().__init__(str(original))
        self.original = original


class RestoreCleanupPendingError(RuntimeError):
    """A failed restore still owns durable bytes or recovery metadata."""


REMAPPABLE_TABLES = frozenset({"search_profiles", "scraped_jobs", "jobs"})
PREFERENCE_FIELDS = frozenset({"preference_signals", "preference_updated_at"})
APPLICATION_PROJECTION_FIELDS = frozenset(
    {
        "job_title",
        "job_company",
        "job_location",
        "latest_event_at",
        "next_action_task_id",
        "next_action_title",
        "next_action_at",
        "next_action_priority",
    }
)
UNVERIFIED_ANALYSIS_FIELDS = frozenset(
    {
        "affinity_score",
        "affinity_analysis",
        "skill_match_score",
        "experience_match_score",
        "intent_match_score",
        "language_match_score",
        "location_match_score",
        "transferability_score",
        "qualification_gap_score",
        "analysis_structured",
        "red_flags",
        "analysis_provenance",
        "analysis_model_id",
        "analysis_contract_version",
        "analysis_validated_at",
        "analysis_execution_id",
        "analysis_output_fingerprint",
        "analysis_execution_row_index",
        "analysis_row_fingerprint",
        "analysis_input_fingerprint",
        "worth_applying",
    }
)


def _quarantined_coach_metadata(value: object, *, reason: str) -> dict[str, Any]:
    """Preserve imported assistant audit data while making its trust state explicit."""
    source = _json_value(value) if isinstance(value, dict) else {"legacy_value": _json_value(value)}
    if (
        isinstance(source, dict)
        and source.get("provenance") == "quarantined"
        and isinstance(source.get("source_generation_metadata"), dict)
    ):
        source = source["source_generation_metadata"]
    return {
        "provenance": "quarantined",
        "quarantine_reason": reason,
        "source_generation_metadata": source,
    }


def _quarantine_unverified_analysis(
    row: dict[str, Any],
    *,
    format_version: int,
) -> None:
    has_analysis = bool(row.get("worth_applying")) or any(
        row.get(field) is not None
        for field in UNVERIFIED_ANALYSIS_FIELDS
        if field != "worth_applying"
    )
    if not has_analysis:
        return
    # Portable ZIPs are checksummed for corruption, not authenticated. An archive author can
    # forge both a match row and its AIExecution receipt, so imported analysis can never inherit
    # the local database's trusted-display bit. Preserve it in local quarantine for audit, but
    # require a fresh local-model run before any claim is rendered or exported.
    preserved = {
        field: _json_value(row.get(field))
        for field in UNVERIFIED_ANALYSIS_FIELDS
        if field in row and (row.get(field) is not None or field == "worth_applying")
    }
    prior_snapshot = row.get("analysis_legacy_snapshot")
    snapshot: dict[str, Any] = {
        "schema_version": "1.0",
        "reason": f"unsigned_v{format_version}_analysis_requires_revalidation",
        "analysis": preserved,
    }
    if prior_snapshot is not None:
        snapshot["previous_snapshot"] = _json_value(prior_snapshot)
    row["analysis_legacy_snapshot"] = snapshot
    for field in UNVERIFIED_ANALYSIS_FIELDS:
        if field in row:
            row[field] = False if field == "worth_applying" else None
    row["worth_applying"] = False


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
        if isinstance(column_type, (DateTime, UTCDateTime)) and isinstance(value, str):
            try:
                decoded[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ArchiveError(f"Invalid timestamp in {model.__tablename__}.{key}") from exc
        elif isinstance(column_type, Date) and isinstance(value, str):
            try:
                decoded[key] = date.fromisoformat(value)
            except ValueError as exc:
                raise ArchiveError(f"Invalid date in {model.__tablename__}.{key}") from exc
    return decoded


def _normalize_search_receipt_row(row: dict[str, Any]) -> None:
    state = row.get("last_search_state")
    summary = row.get("last_search_summary")
    run_count = row.get("search_run_count", 0)
    started_at = row.get("last_search_started_at")
    completed_at = row.get("last_search_completed_at")

    has_receipt = any(
        value is not None for value in (state, summary, started_at, completed_at)
    ) or run_count not in (None, 0)
    if not has_receipt:
        return
    if (
        state != "done"
        or isinstance(run_count, bool)
        or not isinstance(run_count, int)
        or not 1 <= run_count <= SEARCH_RECEIPT_MAX_COUNTER
        or not isinstance(started_at, datetime)
        or not isinstance(completed_at, datetime)
    ):
        raise ArchiveError("Archive search completion receipt is invalid")

    normalized = normalize_search_completion_summary(summary)
    if normalized is None:
        raise ArchiveError("Archive search completion summary is invalid")
    summary_started_at = datetime.fromisoformat(normalized["started_at"])
    summary_completed_at = datetime.fromisoformat(normalized["finished_at"])
    if aware_utc(started_at) != aware_utc(summary_started_at) or aware_utc(
        completed_at
    ) != aware_utc(summary_completed_at):
        raise ArchiveError("Archive search completion receipt timestamps do not match")
    row["last_search_summary"] = normalized


def _assert_ids_available(db: Session, model: type[Any], rows: list[dict[str, Any]]) -> None:
    ids = [str(row["id"]) for row in rows if row.get("id")]
    for start in range(0, len(ids), 400):
        if db.query(model).filter(model.id.in_(ids[start : start + 400])).first() is not None:
            raise ArchiveConflictError(f"Archive IDs already exist in {model.__tablename__}")


def _assert_unique_archive_ids(table_name: str, rows: list[dict[str, Any]]) -> None:
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


def _validate_canonical_string_primary_keys(
    table_name: str,
    model: type[Any],
    rows: list[dict[str, Any]],
) -> None:
    """Reject aliases and path/control characters in UUID-backed identities."""

    string_primary_keys = [
        column
        for column in model.__table__.primary_key.columns
        if getattr(column.type, "length", None) == 36
    ]
    for row in rows:
        for column in string_primary_keys:
            value = row.get(column.name)
            try:
                canonical = str(UUID(value)) if isinstance(value, str) else None
            except (ValueError, AttributeError, TypeError):
                canonical = None
            if canonical != value:
                raise ArchiveError(f"Archive {table_name}.{column.name} is not a canonical UUID")


def _decode_preference_state(format_version: int, tables: dict[str, Any]) -> dict[str, Any] | None:
    if format_version < 3:
        return None
    rows = tables["preference_signals"]
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ArchiveError("Archive versions 3 and 4 require one preference signal record")
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
        if (
            not isinstance(platform, str)
            or not platform
            or not isinstance(platform_job_id, str)
            or not platform_job_id
        ):
            raise ArchiveError("Archive scraped listing is missing its provider identity")
        key = (platform, platform_job_id)
        if key in listing_keys:
            raise ArchiveError("Archive contains duplicate scraped listing identities")
        listing_keys.add(key)
    job_scraped_job_ids: dict[int, int] = {}
    for row in decoded["jobs"]:
        job_id = row.get("id")
        profile_id = row.get("search_profile_id")
        scraped_job_id = row.get("scraped_job_id")
        if profile_id is not None and profile_id not in profile_ids:
            raise ArchiveError("Archive job references a missing search profile")
        if scraped_job_id not in scraped_job_ids:
            raise ArchiveError("Archive job references a missing scraped listing")
        if isinstance(job_id, int) and isinstance(scraped_job_id, int):
            job_scraped_job_ids[job_id] = scraped_job_id

    claimed_logical_ids: set[int] = set()
    for row in decoded["applications"]:
        job_id = row.get("job_id")
        if job_id is not None and job_id not in job_ids:
            raise ArchiveError("Archive application references a missing job")
        if format_version < 5:
            continue
        scraped_job_id = row.get("scraped_job_id")
        if scraped_job_id is None:
            continue
        if scraped_job_id not in scraped_job_ids:
            raise ArchiveError("Archive application references a missing scraped listing")
        if job_id is not None and job_scraped_job_ids.get(job_id) != scraped_job_id:
            raise ArchiveError("Archive application logical opportunity does not match its job")
        if scraped_job_id in claimed_logical_ids:
            raise ArchiveError("Archive contains duplicate application logical opportunities")
        claimed_logical_ids.add(scraped_job_id)


def _validate_portable_foreign_keys(
    format_version: int,
    decoded: dict[str, list[dict[str, Any]]],
) -> None:
    """Validate every archive-owned database relationship before restore writes."""

    archive_table_by_database_table = {
        model.__table__.name: table_name for table_name, model in EXPORT_MODELS
    }
    for table_name, model in EXPORT_MODELS:
        for column in model.__table__.columns:
            for foreign_key in column.foreign_keys:
                target_table = archive_table_by_database_table.get(foreign_key.column.table.name)
                if target_table is None:
                    if (
                        foreign_key.column.table.name == "users"
                        and column.name == "user_id"
                        and table_name in USER_SCOPED_TABLES
                    ):
                        # User ownership is rebound to the authenticated local user.
                        continue
                    raise ArchiveError(
                        f"Archive {table_name}.{column.name} has an unsupported "
                        "external relationship"
                    )
                if format_version < 3 and table_name == "applications" and column.name == "job_id":
                    # Versions 1 and 2 did not include the job tables. Their legacy
                    # application link is deliberately cleared during restore.
                    continue

                target_values = {row.get(foreign_key.column.name) for row in decoded[target_table]}
                for row in decoded[table_name]:
                    value = row.get(column.name)
                    if value is None:
                        continue
                    try:
                        available = value in target_values
                    except TypeError as exc:
                        raise ArchiveError(
                            f"Archive {table_name}.{column.name} relationship is invalid"
                        ) from exc
                    if not available:
                        raise ArchiveError(
                            f"Archive {table_name}.{column.name} references a missing "
                            f"{target_table}.{foreign_key.column.name}"
                        )


def _validate_application_dossier_drafts(
    decoded: dict[str, list[dict[str, Any]]],
) -> None:
    application_revisions = {str(row["id"]): row.get("revision") for row in decoded["applications"]}
    claimed_applications: set[str] = set()
    for row in decoded["application_dossier_drafts"]:
        required_ids = {
            field: row.get(field) for field in ("id", "application_id", "resume_version_id")
        }
        if any(not isinstance(value, str) or not value.strip() for value in required_ids.values()):
            raise ArchiveError("Archive dossier draft relationship is invalid")
        application_id = cast(str, required_ids["application_id"])
        if application_id in claimed_applications:
            raise ArchiveError("Archive contains duplicate dossier drafts for one application")
        claimed_applications.add(application_id)
        draft_revision = row.get("revision")
        application_revision = row.get("application_revision")
        current_application_revision = application_revisions.get(application_id)
        created_at = row.get("created_at")
        updated_at = row.get("updated_at")
        if (
            isinstance(draft_revision, bool)
            or not isinstance(draft_revision, int)
            or draft_revision < 1
            or isinstance(application_revision, bool)
            or not isinstance(application_revision, int)
            or application_revision < 1
            or isinstance(current_application_revision, bool)
            or not isinstance(current_application_revision, int)
            or application_revision > current_application_revision
        ):
            raise ArchiveError("Archive dossier draft revision is invalid")
        if (
            not isinstance(created_at, datetime)
            or not isinstance(updated_at, datetime)
            or cast(datetime, aware_utc(created_at)) > cast(datetime, aware_utc(updated_at))
        ):
            raise ArchiveError("Archive dossier draft timestamp is invalid")
        try:
            row["content"] = ApplicationDossierDraftContent.model_validate(
                row.get("content")
            ).model_dump(mode="json")
        except (TypeError, ValueError) as exc:
            raise ArchiveError("Archive dossier draft content is invalid") from exc


def _extract_application_projection_contract(
    format_version: int,
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Separate untrusted read-model fields from canonical archive records.

    Archive versions 1 and 2 predate application projections. Versions 3 and 4 use
    either historical projection-free or complete projection records. Current values
    are checked after the append-only events have been restored;
    every accepted archive is then rebuilt from its canonical snapshot and events.
    """

    expected: dict[str, dict[str, Any]] = {}
    for row in rows:
        application_id = str(row.get("id") or "")
        present = APPLICATION_PROJECTION_FIELDS.intersection(row)
        if format_version < 3 and present:
            raise ArchiveError(
                f"Archive version {format_version} application rows cannot contain projections"
            )
        if format_version >= 3 and present not in (
            frozenset(),
            APPLICATION_PROJECTION_FIELDS,
        ):
            raise ArchiveError("Archive application projections must be either absent or complete")
        if present == APPLICATION_PROJECTION_FIELDS:
            expected[application_id] = {
                field: row[field] for field in APPLICATION_PROJECTION_FIELDS
            }
        for field in APPLICATION_PROJECTION_FIELDS:
            row.pop(field, None)
    return expected


def _decode_payload(
    db: Session,
    manifest: ArchiveManifest,
    members: dict[str, bytes],
    *,
    enforce_destination_ids: bool = True,
) -> tuple[
    dict[str, list[dict[str, Any]]],
    list[dict[str, Any]],
    dict[str, Any] | None,
    dict[str, dict[str, Any]],
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
        raw_rows = tables.get(table_name, [])
        if table_name == "scraped_jobs":
            # Strip legacy private fields before strict model-column decoding. They are not
            # columns on the current shared catalog model and must never be propagated.
            raw_rows = [
                {key: value for key, value in row.items() if key not in SCRAPED_JOB_PRIVATE_FIELDS}
                if isinstance(row, dict)
                else row
                for row in raw_rows
            ]
        decoded[table_name] = [_decode_row(model, row) for row in raw_rows]
        _validate_canonical_string_primary_keys(table_name, model, decoded[table_name])
        _assert_unique_archive_ids(table_name, decoded[table_name])
        if enforce_destination_ids and table_name not in REMAPPABLE_TABLES:
            _assert_ids_available(db, model, decoded[table_name])
    for row in decoded["search_profiles"]:
        _normalize_search_receipt_row(row)
    for row in decoded["job_provider_configurations"]:
        try:
            if row.get("adapter_kind") == "native":
                raw_adapter_id = row.get("native_adapter_id")
                if not isinstance(raw_adapter_id, str):
                    raise ValueError("Native provider rows require an adapter identifier")
                native_adapter_id = validate_native_adapter_id(raw_adapter_id)
                if row.get("key") != native_adapter_id:
                    raise ValueError("Native provider keys must match the reviewed adapter ID")
                if row.get("request_config") is not None or row.get("extraction_config") is not None:
                    raise ValueError("Native provider rows cannot contain declarative configuration")
                ProviderCapabilitiesConfig.model_validate(row.get("capabilities_config"))
                # Restore never grants network consent, including for reviewed native adapters.
                row["enabled"] = False
                continue
            request_config = row.get("request_config")
            headers = request_config.get("headers", {}) if isinstance(request_config, dict) else {}
            if not isinstance(headers, dict) or any(
                isinstance(name, str) and secret_header(name) for name in headers
            ):
                raise ValueError("Portable provider configurations cannot contain secrets")
            declaration = ProviderConfigurationInput.model_validate(
                {
                    "key": row.get("key"),
                    "display_name": row.get("display_name"),
                    "description": row.get("description"),
                    "adapter_kind": row.get("adapter_kind"),
                    "enabled": row.get("enabled"),
                    "request": request_config,
                    "extraction": row.get("extraction_config"),
                    "capabilities": row.get("capabilities_config"),
                }
            )
            validate_destination_literal(declaration.request.base_url)
            if declaration.adapter_kind == "html":
                validate_selector(declaration.extraction.item_selector or "")
                for mapping in declaration.extraction.fields.values():
                    if mapping.source != ".":
                        validate_selector(mapping.source)
            # Portable archives are integrity checked, not authenticated. Requiring an explicit
            # re-enable prevents a crafted archive from silently granting network consent.
            row["enabled"] = False
        except (ValueError, TypeError) as exc:
            raise ArchiveError("Archive provider configuration is invalid") from exc
    for row in decoded["jobs"]:
        _quarantine_unverified_analysis(
            row,
            format_version=manifest.format_version,
        )
    for row in decoded["applications"]:
        snapshot = row.get("job_snapshot")
        if not isinstance(snapshot, dict):
            raise ArchiveError("Archive application snapshot must be an object")
        # Portable archives are integrity-checksummed, not authenticated. Even if the linked
        # Job and AIExecution were forged consistently, their embedded application projection
        # cannot cross the restore boundary as trusted analysis.
        row["job_snapshot"] = sanitize_application_snapshot(
            snapshot,
            quarantine_reason=(
                f"unsigned_v{manifest.format_version}_application_match_requires_revalidation"
            ),
        )
    # Archive checksums detect corruption, not authorship. Assistant messages and their execution
    # rows can be forged together, so imported advice cannot be displayed as current validated
    # output. Preserve it in explicit, non-rendered quarantine instead of deleting user history.
    for row in decoded["coach_messages"]:
        if row.get("role") == "assistant":
            row["generation_metadata"] = _quarantined_coach_metadata(
                row.get("generation_metadata"),
                reason=f"unsigned_v{manifest.format_version}_coach_output_requires_revalidation",
            )
    preference_state = _decode_preference_state(manifest.format_version, tables)
    _validate_search_relationships(manifest.format_version, decoded)
    _validate_portable_foreign_keys(manifest.format_version, decoded)
    _validate_application_dossier_drafts(decoded)
    projection_contract = _extract_application_projection_contract(
        manifest.format_version, decoded["applications"]
    )
    _validate_application_projection_contract(decoded, projection_contract)
    return decoded, bindings, preference_state, projection_contract


def _assert_decoded_ids_available(db: Session, decoded: dict[str, list[dict[str, Any]]]) -> None:
    """Apply destination-only ID checks after a content-only archive preflight."""

    for table_name, model in EXPORT_MODELS:
        if table_name not in REMAPPABLE_TABLES:
            _assert_ids_available(db, model, decoded[table_name])


def _assert_empty_vault(db: Session, user_id: int, format_version: int) -> None:
    checks = (
        (CandidateProfile, CandidateProfile.user_id, "career vault"),
        (
            JobProviderConfiguration,
            JobProviderConfiguration.user_id,
            "job provider configuration history",
        ),
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


def _canonical_file_storage_path(
    table_name: str,
    record: dict[str, Any],
    decoded: dict[str, list[dict[str, Any]]],
) -> str:
    """Derive storage ownership from trusted schema relationships, never archive paths."""

    digest = record.get("sha256")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ArchiveError("Archive file digest is invalid")

    if table_name == "career_assets":
        kind = record.get("kind")
        if kind == "source_document":
            if record.get("normalized") is not False:
                raise ArchiveError("Archive source document normalization state is invalid")
            return f"assets/{digest[:2]}/{digest}"
        if kind == "profile_photo":
            if record.get("normalized") is not True or record.get("media_type") != "image/jpeg":
                raise ArchiveError("Archive profile photo metadata is invalid")
            return f"assets/photos/{digest[:2]}/{digest}.jpg"
        raise ArchiveError("Archive contains an unsupported managed asset kind")

    if table_name == "resume_artifacts":
        artifact_format = record.get("format")
        media_types = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        if (
            artifact_format not in media_types
            or record.get("media_type") != media_types[artifact_format]
        ):
            raise ArchiveError("Archive resume artifact metadata is invalid")
        version = next(
            (
                row
                for row in decoded["resume_versions"]
                if row.get("id") == record.get("version_id")
            ),
            None,
        )
        draft = (
            next(
                (
                    row
                    for row in decoded["resume_drafts"]
                    if row.get("id") == version.get("draft_id")
                ),
                None,
            )
            if version is not None
            else None
        )
        if version is None or draft is None:
            raise ArchiveError("Archive resume artifact relationship is invalid")
        profile_id = draft.get("profile_id")
        version_id = version.get("id")
        if not isinstance(profile_id, str) or not isinstance(version_id, str):
            raise ArchiveError("Archive resume artifact relationship is invalid")
        return f"resumes/{profile_id}/{version_id}/{digest}.{artifact_format}"

    raise ArchiveError("Archive contains an unsupported managed file table")


def _prepare_file_writes(
    decoded: dict[str, list[dict[str, Any]]],
    bindings: list[dict[str, Any]],
    members: dict[str, bytes],
    *,
    create_data_root: bool = True,
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
        if not all(isinstance(value, str) for value in (table_value, record_value, member_value)):
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
        byte_size = record.get("byte_size")
        maximum_size = (
            settings.MAX_UPLOAD_FILE_SIZE
            if table_name == "career_assets"
            else MAX_RESUME_ARTIFACT_BYTES
        )
        if (
            isinstance(byte_size, bool)
            or not isinstance(byte_size, int)
            or byte_size <= 0
            or byte_size > maximum_size
        ):
            raise ArchiveError("Archive file size metadata is invalid")
        file_data = members[member]
        if sha256(file_data) != record.get("sha256") or len(file_data) != byte_size:
            raise ArchiveError("Archived file does not match its database record")
        canonical_path = _canonical_file_storage_path(table_name, record, decoded)
        if record.get("storage_path") != canonical_path:
            raise ArchiveError("Archive storage path is not canonical for its record")
        try:
            resolve_data_path(
                canonical_path,
                create_root=create_data_root,
            )
        except ValueError as exc:
            raise ArchiveError("Archive contains an unsafe storage path") from exc
        writes.append((canonical_path, file_data))
        actual_keys.add(key)

    if actual_keys != set(records):
        raise ArchiveError("Archive is missing one or more persisted file bindings")
    if set(members) != {str(binding.get("member")) for binding in bindings} | {PAYLOAD_MEMBER}:
        raise ArchiveError("Archive contains unbound file members")
    return writes


def _file_destinations_available(writes: list[tuple[str, bytes]]) -> bool:
    """Check restore destinations without creating directories or changing files."""

    for relative_path, file_data in writes:
        try:
            destination = resolve_data_path(relative_path, create_root=False)
            existing = read_stable_bounded_file(
                destination,
                expected_size=len(file_data),
                maximum_size=len(file_data),
            )
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            return False
        if sha256(existing) != sha256(file_data):
            return False
    return True


def _prepare_row(
    table_name: str,
    row: dict[str, Any],
    user_id: int,
    *,
    format_version: int,
    job_id_map: dict[int, int],
    application_logical_identity_map: dict[object, int | None],
) -> None:
    if table_name in USER_SCOPED_TABLES:
        row["user_id"] = user_id
    if table_name == "applications":
        archived_application_id = row["id"]
        archived_job_id = row.get("job_id")
        row["job_id"] = (
            job_id_map[archived_job_id]
            if format_version >= 3 and archived_job_id is not None
            else None
        )
        row["scraped_job_id"] = application_logical_identity_map[archived_application_id]
    if table_name == "workflow_runs":
        row["lease_owner"] = None
        row["lease_expires_at"] = None
        if row.get("status") == "completed":
            row["status"] = "succeeded"
        elif row.get("status") not in {"succeeded", "failed", "cancelled"}:
            row["status"] = "cancelled"
            row["error_code"] = "restored_without_execution"


def _add_remappable_row(db: Session, model: type[Any], row: dict[str, Any]) -> Any:
    prepared = dict(row)
    archived_id = prepared["id"]
    if db.get(model, archived_id) is not None:
        prepared.pop("id")
    instance = model(**prepared)
    db.add(instance)
    db.flush()
    return instance


def _shared_listing_content(record: ScrapedJob | dict[str, Any]) -> dict[str, Any]:
    ignored = {
        "id",
        "created_at",
        "updated_at",
        "first_seen_at",
        "last_seen_at",
        "last_changed_at",
        "content_revision",
        *SCRAPED_JOB_PRIVATE_FIELDS,
    }
    return {
        column.name: _json_value(
            record.get(column.name) if isinstance(record, dict) else getattr(record, column.name)
        )
        for column in ScrapedJob.__table__.columns
        if column.name not in ignored
    }


def _restore_search_records(
    db: Session,
    user_id: int,
    decoded: dict[str, list[dict[str, Any]]],
) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
    profile_id_map: dict[int, int] = {}
    for row in decoded["search_profiles"]:
        prepared = dict(row)
        archived_id = prepared["id"]
        prepared["user_id"] = user_id
        for field in SEARCH_PROFILE_RUNTIME_FIELDS:
            prepared[field] = None
        # A portable preference is not authority to restart an OS-local job.
        # Keep the chosen interval, but require an explicit post-restore opt-in.
        prepared["schedule_enabled"] = False
        prepared["last_scheduled_run"] = None
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
            if _shared_listing_content(existing) != _shared_listing_content(row):
                raise ArchiveConflictError(
                    "A shared scraped listing already exists with different public content"
                )
            restored = existing
        else:
            restored = _add_remappable_row(db, ScrapedJob, row)
        scraped_job_id_map[archived_id] = restored.id

    job_id_map: dict[int, int] = {}
    job_scraped_job_id_map: dict[int, int] = {}
    for row in decoded["jobs"]:
        prepared = dict(row)
        archived_id = prepared["id"]
        prepared["user_id"] = user_id
        profile_id = prepared.get("search_profile_id")
        prepared["search_profile_id"] = (
            profile_id_map[profile_id] if profile_id is not None else None
        )
        restored_scraped_job_id = scraped_job_id_map[prepared["scraped_job_id"]]
        prepared["scraped_job_id"] = restored_scraped_job_id
        restored = _add_remappable_row(db, Job, prepared)
        job_id_map[archived_id] = restored.id
        job_scraped_job_id_map[archived_id] = restored_scraped_job_id
    return job_id_map, job_scraped_job_id_map, scraped_job_id_map


def _application_logical_identity_map(
    decoded: dict[str, list[dict[str, Any]]],
    *,
    job_scraped_job_id_map: dict[int, int],
    scraped_job_id_map: dict[int, int],
) -> dict[object, int | None]:
    """Choose one portable application timeline per restored logical opportunity."""

    applications = decoded["applications"]
    logical_id_by_application: dict[object, int | None] = {row["id"]: None for row in applications}
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in applications:
        archived_scraped_job_id = row.get("scraped_job_id")
        logical_id: int | None
        if archived_scraped_job_id is not None:
            logical_id = scraped_job_id_map[archived_scraped_job_id]
        else:
            archived_job_id = row.get("job_id")
            logical_id = (
                job_scraped_job_id_map.get(archived_job_id) if archived_job_id is not None else None
            )
        if logical_id is not None:
            grouped.setdefault(logical_id, []).append(row)

    minimum_timestamp = datetime.min.replace(tzinfo=UTC)
    for logical_id, rows in grouped.items():
        # Preserve all legacy timelines. Stable sorting chooses the lowest id when
        # timestamps tie, while only the most recently updated row owns the unique key.
        rows.sort(key=lambda row: str(row["id"]))
        rows.sort(
            key=lambda row: aware_utc(row.get("updated_at")) or minimum_timestamp,
            reverse=True,
        )
        logical_id_by_application[rows[0]["id"]] = logical_id
    return logical_id_by_application


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


def _canonical_application_projection_parts(
    snapshot: object,
    events: list[object],
) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise ArchiveError("Archive application snapshot must be an object")
    if not events:
        raise ArchiveError("Archive application must contain at least one timeline event")
    event_times = [aware_utc(getattr(event, "occurred_at", None)) for event in events]
    if any(value is None for value in event_times):
        raise ArchiveError("Archive application event is missing its timestamp")
    try:
        application_view = cast(Application, SimpleNamespace(events=events))
        tasks = ApplicationService._task_snapshots(application_view)
    except ApplicationValidationError as exc:
        raise ArchiveError("Archive application task history is invalid") from exc
    next_action = ApplicationService._next_action(tasks)
    return {
        "job_title": str(snapshot.get("title") or "Untitled role")[:240],
        "job_company": str(snapshot.get("company") or "Unknown company")[:240],
        "job_location": (
            str(snapshot["location"])[:500] if snapshot.get("location") is not None else None
        ),
        "latest_event_at": max(value for value in event_times if value is not None),
        "next_action_task_id": next_action.id if next_action else None,
        "next_action_title": next_action.title if next_action else None,
        "next_action_at": next_action.due_at if next_action else None,
        "next_action_priority": next_action.priority if next_action else None,
    }


def _canonical_application_projection(application: Application) -> dict[str, Any]:
    return _canonical_application_projection_parts(
        application.job_snapshot,
        list(application.events),
    )


def _projection_value_matches(field: str, archived: Any, canonical: Any) -> bool:
    if field in {"latest_event_at", "next_action_at"}:
        return aware_utc(archived) == aware_utc(canonical)
    return bool(archived == canonical)


def _validate_application_projection_contract(
    decoded: dict[str, list[dict[str, Any]]],
    archived_contract: dict[str, dict[str, Any]],
) -> None:
    """Validate application timelines and projections without writing archive rows."""

    applications = {str(row["id"]): row for row in decoded["applications"]}
    events_by_application: dict[str, list[object]] = {
        application_id: [] for application_id in applications
    }
    for event in decoded["application_events"]:
        application_id = str(event.get("application_id") or "")
        if application_id not in applications:
            raise ArchiveError("Archive application event references a missing application")
        events_by_application[application_id].append(SimpleNamespace(**event))

    for application_id, row in applications.items():
        canonical = _canonical_application_projection_parts(
            row.get("job_snapshot"),
            events_by_application[application_id],
        )
        archived = archived_contract.get(application_id)
        if archived is None:
            continue
        mismatches = sorted(
            field
            for field, value in canonical.items()
            if not _projection_value_matches(field, archived[field], value)
        )
        if mismatches:
            raise ArchiveError(
                "Archive application projections are inconsistent with its snapshot or timeline"
            )


def _rebuild_application_projections(
    db: Session,
    user_id: int,
    archived_contract: dict[str, dict[str, Any]],
) -> None:
    """Validate current projections and rebuild every restored read model."""

    db.expire_all()
    applications = (
        db.query(Application)
        .filter(Application.user_id == user_id)
        .order_by(Application.id.asc())
        .all()
    )
    for application in applications:
        canonical = _canonical_application_projection(application)
        archived = archived_contract.get(application.id)
        if archived is not None:
            mismatches = sorted(
                field
                for field, value in canonical.items()
                if not _projection_value_matches(field, archived[field], value)
            )
            if mismatches:
                raise ArchiveError(
                    "Archive application projections are inconsistent with its "
                    f"snapshot or timeline: {', '.join(mismatches)}"
                )
        preserved_updated_at = application.updated_at
        db.execute(
            update(Application)
            .where(Application.id == application.id)
            .values(**canonical, updated_at=preserved_updated_at)
            .execution_options(synchronize_session=False)
        )
    db.flush()


def _restored_file_bindings(
    db: Session,
    *,
    user_id: int,
    storage_paths: set[str],
) -> dict[str, set[tuple[str, int]]]:
    """Read every same-owner binding without exceeding SQLite's bind limit."""

    bindings: dict[str, set[tuple[str, int]]] = {}
    ordered = sorted(storage_paths)
    for offset in range(0, len(ordered), 500):
        batch = ordered[offset : offset + 500]
        for storage_path, digest, byte_size in (
            db.query(CareerAsset.storage_path, CareerAsset.sha256, CareerAsset.byte_size)
            .join(CandidateProfile, CareerAsset.profile_id == CandidateProfile.id)
            .filter(
                CandidateProfile.user_id == user_id,
                CareerAsset.storage_path.in_(batch),
            )
            .all()
        ):
            bindings.setdefault(storage_path, set()).add((digest, byte_size))
        for storage_path, digest, byte_size in (
            db.query(
                ResumeArtifact.storage_path,
                ResumeArtifact.sha256,
                ResumeArtifact.byte_size,
            )
            .join(ResumeVersion, ResumeArtifact.version_id == ResumeVersion.id)
            .join(ResumeDraft, ResumeVersion.draft_id == ResumeDraft.id)
            .join(CandidateProfile, ResumeDraft.profile_id == CandidateProfile.id)
            .filter(
                CandidateProfile.user_id == user_id,
                ResumeArtifact.storage_path.in_(batch),
            )
            .all()
        ):
            bindings.setdefault(storage_path, set()).add((digest, byte_size))
    return bindings


def _restore_commit_was_published(
    db: Session,
    *,
    user_id: int,
    decoded: dict[str, list[dict[str, Any]]],
    writes: list[tuple[str, bytes]],
    archive_fingerprint: str,
) -> bool:
    """Resolve a lost commit acknowledgement from a fresh authoritative snapshot.

    Every valid archive contains exactly one destination-unique CandidateProfile.
    Its presence proves that SQLite committed the whole transaction; its absence
    proves rollback. Before accepting the committed outcome, also require the
    lifecycle transition, every same-user file binding, the durable bytes, and
    any surviving journal to agree with the verified archive.
    """

    profile_rows = decoded.get("candidate_profiles", [])
    if len(profile_rows) != 1 or not isinstance(profile_rows[0].get("id"), str):
        raise RestoreCleanupPendingError("Restore commit identity is unavailable")
    expected_profile_id = cast(str, profile_rows[0]["id"])
    bind = db.get_bind()
    with Session(bind=bind, expire_on_commit=False) as verification:
        if bind.dialect.name == "sqlite":
            verification.execute(text("BEGIN IMMEDIATE"))
        owner_query = verification.query(User).filter(User.id == user_id)
        profile_query = verification.query(CandidateProfile).filter(
            CandidateProfile.id == expected_profile_id
        )
        if bind.dialect.name != "sqlite":
            owner_query = owner_query.with_for_update()
            profile_query = profile_query.with_for_update()
        owner = owner_query.one_or_none()
        profile = profile_query.one_or_none()
        if profile is None:
            verification.rollback()
            return False
        if (
            owner is None
            or profile.user_id != user_id
            or owner.vault_lifecycle_state != VAULT_STATE_READY
            or owner.vault_maintenance_fingerprint is not None
        ):
            raise RestoreCleanupPendingError("Restore commit identity is inconsistent")

        expected_bindings: dict[str, tuple[str, int]] = {}
        for storage_path, file_data in writes:
            metadata = (sha256(file_data), len(file_data))
            previous = expected_bindings.setdefault(storage_path, metadata)
            if previous != metadata:
                raise RestoreCleanupPendingError("Restore file bindings conflict")
        actual_bindings = _restored_file_bindings(
            verification,
            user_id=user_id,
            storage_paths=set(expected_bindings),
        )
        if any(
            actual_bindings.get(storage_path) != {metadata}
            for storage_path, metadata in expected_bindings.items()
        ):
            raise RestoreCleanupPendingError("Restored database file bindings are incomplete")
        if not _file_destinations_available(writes):
            raise RestoreCleanupPendingError("Restored durable files are incomplete")

        journal = read_restore_journal(user_id)
        if journal is not None and (
            journal["archive_fingerprint"] != archive_fingerprint
            or not set(journal["paths"]).issubset(expected_bindings)
        ):
            raise RestoreCleanupPendingError("Restore recovery metadata disagrees with the commit")
        verification.rollback()
        return True


def _restore_transaction(
    db: Session,
    user_id: int,
    format_version: int,
    decoded: dict[str, list[dict[str, Any]]],
    preference_state: dict[str, Any] | None,
    application_projection_contract: dict[str, dict[str, Any]],
    writes: list[tuple[str, bytes]],
    archive_fingerprint: str,
) -> None:
    commit_attempted = False
    try:
        _enable_sqlite_secure_delete(db)
        prepare_restore_journal(
            user_id,
            archive_fingerprint,
            [relative_path for relative_path, _file_data in writes],
        )
        for relative_path, file_data in writes:
            try:
                _path, created = atomic_restore_write(user_id, relative_path, file_data)
            except ValueError as exc:
                raise ArchiveConflictError(
                    "Restore target contains a different managed file"
                ) from exc
            if created:
                logger.debug("Published one restore-owned managed file")
        (
            job_id_map,
            job_scraped_job_id_map,
            scraped_job_id_map,
        ) = _restore_search_records(db, user_id, decoded)
        application_logical_identity_map = _application_logical_identity_map(
            decoded,
            job_scraped_job_id_map=job_scraped_job_id_map,
            scraped_job_id_map=scraped_job_id_map,
        )
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
                    application_logical_identity_map=application_logical_identity_map,
                )
                db.add(model(**row))
            db.flush()
        _rebuild_application_projections(db, user_id, application_projection_contract)
        _restore_preference_state(db, user_id, preference_state)
        db.query(AutomationGrant).filter(
            AutomationGrant.user_id == user_id,
            AutomationGrant.revoked_at.is_(None),
        ).update(
            {AutomationGrant.revoked_at: datetime.now(UTC)},
            synchronize_session=False,
        )
        db.query(AuthSession).filter(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        ).update(
            {AuthSession.revoked_at: datetime.now(UTC)},
            synchronize_session=False,
        )
        user = db.get(User, user_id)
        if user is None:
            raise ArchiveError("Restore account no longer exists")
        user.vault_lifecycle_state = VAULT_STATE_READY
        user.vault_maintenance_fingerprint = None
        db.flush()
        commit_attempted = True
        db.commit()
        try:
            clear_restore_journal(user_id)
        except RestoreJournalError:
            # The journal contains paths only, never file content. A stale copy is
            # safe and complete erasure will remove it on the next cleanup pass.
            logger.warning("Committed restore journal could not be removed")
    except Exception as exc:
        original: Exception = (
            ArchiveError("Archive records failed relational validation")
            if isinstance(exc, (IntegrityError, StatementError))
            else exc
        )
        if commit_attempted:
            db.rollback()
            try:
                committed = _restore_commit_was_published(
                    db,
                    user_id=user_id,
                    decoded=decoded,
                    writes=writes,
                    archive_fingerprint=archive_fingerprint,
                )
            except Exception as verification_error:
                raise RestoreCleanupPendingError(
                    "Restore commit outcome could not be verified; retry the same archive"
                ) from verification_error
            if committed:
                db.expire_all()
                try:
                    clear_restore_journal(user_id)
                except RestoreJournalError:
                    logger.warning("Committed restore journal could not be removed")
                return
        _rollback_failed_restore(db, user_id, original)


def _rollback_failed_restore(db: Session, user_id: int, original: Exception) -> None:
    """Remove all journal-owned bytes before declaring a failed restore rolled back."""

    db.rollback()
    cleanup_errors: list[Exception] = []
    journal_paths: set[str] | None = None
    try:
        # A content-addressed file can gain a legitimate binding owned by a
        # different account after the crashed restore published it. Ownership
        # then transfers to that binding; rollback removes only still-exclusive
        # journal paths while clearing this user's recovery metadata.
        journal_paths = _exclusive_restore_journal_paths(db, user_id)
    except Exception as exc:
        cleanup_errors.append(exc)

    if journal_paths is not None:
        for relative_path in sorted(journal_paths):
            try:
                durable_unlink(resolve_data_path(relative_path))
            except Exception as exc:
                cleanup_errors.append(exc)
        if not cleanup_errors:
            try:
                clear_restore_journal(user_id)
            except Exception as exc:
                cleanup_errors.append(exc)

    try:
        _sanitize_sqlite_storage(db)
    except Exception as exc:
        cleanup_errors.append(exc)

    if cleanup_errors:
        raise RestoreCleanupPendingError(
            "Failed restore cleanup is incomplete; retry the same archive or erase local data"
        ) from cleanup_errors[0]
    raise RestoreRolledBackError(original) from original


def restore_archive(db: Session, user_id: int, data: bytes) -> RestoreResponse:
    try:
        with desktop_vault_lock():
            manifest, members = _validated_members(data)
            _assert_empty_vault(db, user_id, manifest.format_version)
            (
                decoded,
                bindings,
                preference_state,
                application_projection_contract,
            ) = _decode_payload(db, manifest, members)
            writes = _prepare_file_writes(decoded, bindings, members)
            _restore_transaction(
                db,
                user_id,
                manifest.format_version,
                decoded,
                preference_state,
                application_projection_contract,
                writes,
                sha256(data),
            )
    except VaultLockTimeout as exc:
        raise ArchiveConflictError(str(exc)) from exc

    restored_records = {
        name: len(decoded[name]) if name in decoded else manifest.record_counts.get(name, 0)
        for name in expected_tables(CURRENT_ARCHIVE_VERSION)
    }
    return RestoreResponse(
        format_version=manifest.format_version,
        archive_sha256=sha256(data),
        restored_records=restored_records,
        restored_files=len(writes),
    )
