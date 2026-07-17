import hashlib
import json
import zipfile
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, Final, Literal

from sqlalchemy import Date, DateTime
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from backend.applications.models import Application, ApplicationEvent
from backend.career.coach_models import CoachConversation, CoachMessage
from backend.career.models import (
    CandidateProfile,
    CareerAsset,
    CareerFact,
    CareerGoal,
    SourceDocument,
)
from backend.core.config import settings
from backend.portability.schemas import ArchiveEntry, ArchiveManifest, RestoreResponse
from backend.resumes.models import ResumeArtifact, ResumeDraft, ResumeVersion
from backend.storage.atomic import atomic_write, read_verified, resolve_data_path
from backend.workflows.models import WorkflowRun

ARCHIVE_FORMAT: Final[Literal["careeros-portable-archive"]] = "careeros-portable-archive"
ARCHIVE_VERSION: Final[Literal[1]] = 1
MANIFEST_MEMBER: Final = "manifest.json"
PAYLOAD_MEMBER: Final = "payload.json"


class ArchiveError(ValueError):
    pass


class ArchiveConflictError(RuntimeError):
    pass


# The archive intentionally traverses heterogeneous mapped classes. ``Any`` is
# limited to this registry boundary; row data is validated against table metadata
# before an ORM instance is constructed.
EXPORT_MODELS: list[tuple[str, type[Any]]] = [
    ("candidate_profiles", CandidateProfile),
    ("career_assets", CareerAsset),
    ("source_documents", SourceDocument),
    ("career_facts", CareerFact),
    ("career_goals", CareerGoal),
    ("resume_drafts", ResumeDraft),
    ("resume_versions", ResumeVersion),
    ("resume_artifacts", ResumeArtifact),
    ("applications", Application),
    ("application_events", ApplicationEvent),
    ("coach_conversations", CoachConversation),
    ("coach_messages", CoachMessage),
    ("workflow_runs", WorkflowRun),
]
MODEL_BY_TABLE = dict(EXPORT_MODELS)


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _row(instance: Any, *, omit: set[str] | None = None) -> dict[str, Any]:
    omitted = omit or set()
    return {
        column.name: _json_value(getattr(instance, column.name))
        for column in instance.__table__.columns
        if column.name not in omitted
    }


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _queries(db: Session, user_id: int) -> dict[str, list[Any]]:
    profile = db.query(CandidateProfile).filter(CandidateProfile.user_id == user_id).first()
    profile_id = profile.id if profile else None
    profile_rows = [profile] if profile else []
    assets = (
        db.query(CareerAsset).filter(CareerAsset.profile_id == profile_id).all()
        if profile_id
        else []
    )
    sources = (
        db.query(SourceDocument).filter(SourceDocument.profile_id == profile_id).all()
        if profile_id
        else []
    )
    facts = (
        db.query(CareerFact).filter(CareerFact.profile_id == profile_id).all()
        if profile_id
        else []
    )
    goals = (
        db.query(CareerGoal).filter(CareerGoal.profile_id == profile_id).all()
        if profile_id
        else []
    )
    drafts = (
        db.query(ResumeDraft).filter(ResumeDraft.profile_id == profile_id).all()
        if profile_id
        else []
    )
    versions = (
        db.query(ResumeVersion)
        .join(ResumeDraft, ResumeVersion.draft_id == ResumeDraft.id)
        .filter(ResumeDraft.profile_id == profile_id)
        .all()
        if profile_id
        else []
    )
    artifacts = (
        db.query(ResumeArtifact)
        .join(ResumeVersion, ResumeArtifact.version_id == ResumeVersion.id)
        .join(ResumeDraft, ResumeVersion.draft_id == ResumeDraft.id)
        .filter(ResumeDraft.profile_id == profile_id)
        .all()
        if profile_id
        else []
    )
    applications = db.query(Application).filter(Application.user_id == user_id).all()
    application_events = (
        db.query(ApplicationEvent)
        .join(Application, ApplicationEvent.application_id == Application.id)
        .filter(Application.user_id == user_id)
        .all()
        if applications
        else []
    )
    conversations = (
        db.query(CoachConversation).filter(CoachConversation.profile_id == profile_id).all()
        if profile_id
        else []
    )
    messages = (
        db.query(CoachMessage)
        .join(CoachConversation, CoachMessage.conversation_id == CoachConversation.id)
        .filter(CoachConversation.profile_id == profile_id)
        .all()
        if conversations
        else []
    )
    workflows = db.query(WorkflowRun).filter(WorkflowRun.user_id == user_id).all()
    return {
        "candidate_profiles": profile_rows,
        "career_assets": assets,
        "source_documents": sources,
        "career_facts": facts,
        "career_goals": goals,
        "resume_drafts": drafts,
        "resume_versions": versions,
        "resume_artifacts": artifacts,
        "applications": applications,
        "application_events": application_events,
        "coach_conversations": conversations,
        "coach_messages": messages,
        "workflow_runs": workflows,
    }


def export_archive(db: Session, user_id: int) -> bytes:
    rows = _queries(db, user_id)
    if not rows["candidate_profiles"]:
        raise ArchiveError("There is no career vault data to export")

    tables: dict[str, list[dict[str, Any]]] = {}
    for table_name, _model in EXPORT_MODELS:
        omit = {"user_id"} if table_name in {"candidate_profiles", "applications", "workflow_runs"} else set()
        tables[table_name] = [_row(item, omit=omit) for item in rows[table_name]]

    bindings: list[dict[str, str]] = []
    file_members: dict[str, bytes] = {}
    for asset in rows["career_assets"]:
        member = f"files/career-assets/{asset.id}"
        data = read_verified(asset.storage_path, asset.sha256)
        if len(data) != asset.byte_size:
            raise ArchiveError(f"Career asset {asset.id} failed its size check")
        file_members[member] = data
        bindings.append(
            {
                "table": "career_assets",
                "record_id": asset.id,
                "storage_path": asset.storage_path,
                "member": member,
            }
        )
    for artifact in rows["resume_artifacts"]:
        member = f"files/resume-artifacts/{artifact.id}.{artifact.format}"
        data = read_verified(artifact.storage_path, artifact.sha256)
        if len(data) != artifact.byte_size:
            raise ArchiveError(f"Resume artifact {artifact.id} failed its size check")
        file_members[member] = data
        bindings.append(
            {
                "table": "resume_artifacts",
                "record_id": artifact.id,
                "storage_path": artifact.storage_path,
                "member": member,
            }
        )

    payload = _canonical_json({"tables": tables, "file_bindings": bindings})
    members = {PAYLOAD_MEMBER: payload, **file_members}
    entries = [
        ArchiveEntry(path=path, sha256=_digest(data), byte_size=len(data))
        for path, data in sorted(members.items())
    ]
    manifest = ArchiveManifest(
        format=ARCHIVE_FORMAT,
        format_version=ARCHIVE_VERSION,
        created_at=datetime.now(timezone.utc),
        owner_scope="career-vault",
        record_counts={name: len(items) for name, items in tables.items()},
        entries=entries,
    )
    manifest_data = _canonical_json(manifest.model_dump(mode="json"))

    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_MEMBER, manifest_data)
        for path, data in sorted(members.items()):
            archive.writestr(path, data)
    result = output.getvalue()
    if len(result) > settings.PORTABLE_ARCHIVE_MAX_BYTES:
        raise ArchiveError("The portable archive exceeds the configured size limit")
    return result


def _safe_info(info: zipfile.ZipInfo) -> None:
    path = PurePosixPath(info.filename)
    if (
        info.filename.startswith(("/", "\\"))
        or "\\" in info.filename
        or ".." in path.parts
        or info.is_dir()
        or info.flag_bits & 0x1
    ):
        raise ArchiveError("The archive contains an unsafe member")


def _validated_members(data: bytes) -> tuple[ArchiveManifest, dict[str, bytes]]:
    if not data or len(data) > settings.PORTABLE_ARCHIVE_MAX_BYTES:
        raise ArchiveError("The portable archive is empty or exceeds the size limit")
    try:
        archive = zipfile.ZipFile(BytesIO(data), mode="r")
    except zipfile.BadZipFile as exc:
        raise ArchiveError("The uploaded file is not a valid ZIP archive") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > settings.PORTABLE_ARCHIVE_MAX_MEMBERS:
            raise ArchiveError("The archive contains too many members")
        names = [item.filename for item in infos]
        if len(names) != len(set(names)):
            raise ArchiveError("The archive contains duplicate member names")
        total_size = 0
        for info in infos:
            _safe_info(info)
            total_size += info.file_size
            if total_size > settings.PORTABLE_ARCHIVE_MAX_UNCOMPRESSED_BYTES:
                raise ArchiveError("The archive expands beyond the configured size limit")
        if MANIFEST_MEMBER not in names:
            raise ArchiveError("The archive manifest is missing")
        try:
            manifest = ArchiveManifest.model_validate_json(archive.read(MANIFEST_MEMBER))
        except Exception as exc:
            raise ArchiveError("The archive manifest is invalid") from exc
        expected = {entry.path for entry in manifest.entries} | {MANIFEST_MEMBER}
        if expected != set(names):
            raise ArchiveError("Archive members do not match the manifest")
        members: dict[str, bytes] = {}
        for entry in manifest.entries:
            member = archive.read(entry.path)
            if len(member) != entry.byte_size or _digest(member) != entry.sha256:
                raise ArchiveError(f"Archive member failed integrity check: {entry.path}")
            members[entry.path] = member
        return manifest, members


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
                raise ArchiveError(f"Invalid timestamp in {model.__tablename__}.{key}") from exc
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


def restore_archive(db: Session, user_id: int, data: bytes) -> RestoreResponse:
    manifest, members = _validated_members(data)
    try:
        payload = json.loads(members[PAYLOAD_MEMBER])
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ArchiveError("The archive payload is invalid") from exc
    tables = payload.get("tables")
    bindings = payload.get("file_bindings")
    if not isinstance(tables, dict) or not isinstance(bindings, list):
        raise ArchiveError("The archive payload structure is invalid")
    if set(tables) != set(MODEL_BY_TABLE):
        raise ArchiveError("The archive contains an unsupported table set")
    if set(manifest.record_counts) != set(MODEL_BY_TABLE):
        raise ArchiveError("The manifest contains an unsupported record count set")
    total_records = sum(len(value) for value in tables.values() if isinstance(value, list))
    if total_records > settings.PORTABLE_ARCHIVE_MAX_RECORDS:
        raise ArchiveError("The archive contains too many records")
    for name in MODEL_BY_TABLE:
        if not isinstance(tables[name], list) or len(tables[name]) != manifest.record_counts.get(name):
            raise ArchiveError(f"Archive record count mismatch for {name}")
    if len(tables["candidate_profiles"]) != 1:
        raise ArchiveError("A portable career archive must contain exactly one profile")
    if db.query(CandidateProfile).filter(CandidateProfile.user_id == user_id).first() is not None:
        raise ArchiveConflictError("Restore requires an empty career vault")
    if db.query(Application).filter(Application.user_id == user_id).first() is not None:
        raise ArchiveConflictError("Restore requires an empty application history")
    if db.query(WorkflowRun).filter(WorkflowRun.user_id == user_id).first() is not None:
        raise ArchiveConflictError("Restore requires an empty workflow history")

    decoded_tables: dict[str, list[dict[str, Any]]] = {}
    for table_name, model in EXPORT_MODELS:
        decoded_tables[table_name] = [_decode_row(model, row) for row in tables[table_name]]
        _assert_ids_available(db, model, decoded_tables[table_name])

    records_by_binding = {
        (table_name, str(row.get("id"))): row
        for table_name in {"career_assets", "resume_artifacts"}
        for row in decoded_tables[table_name]
    }
    expected_binding_keys = set(records_by_binding)
    actual_binding_keys: set[tuple[str, str]] = set()
    writes: list[tuple[str, bytes]] = []
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ArchiveError("Archive file binding is invalid")
        table_value = binding.get("table")
        record_value = binding.get("record_id")
        member_value = binding.get("member")
        if (
            not isinstance(table_value, str)
            or not isinstance(record_value, str)
            or not isinstance(member_value, str)
        ):
            raise ArchiveError("Archive file binding fields must be strings")
        table_name = table_value
        record_id = record_value
        key = (table_name, record_id)
        record = records_by_binding.get(key)
        if record is None or key in actual_binding_keys:
            raise ArchiveError("Archive file binding does not reference one unique record")
        if binding.get("storage_path") != record.get("storage_path"):
            raise ArchiveError("Archive storage path does not match its record")
        member = member_value
        if member not in members or member == PAYLOAD_MEMBER:
            raise ArchiveError("Archive file binding references a missing member")
        file_data = members[member]
        if _digest(file_data) != record.get("sha256") or len(file_data) != record.get("byte_size"):
            raise ArchiveError("Archived file does not match its database record")
        try:
            resolve_data_path(str(record["storage_path"]))
        except ValueError as exc:
            raise ArchiveError("Archive contains an unsafe storage path") from exc
        writes.append((str(record["storage_path"]), file_data))
        actual_binding_keys.add(key)
    if actual_binding_keys != expected_binding_keys:
        raise ArchiveError("Archive is missing one or more persisted file bindings")
    bound_members = {str(binding.get("member")) for binding in bindings}
    if set(members) != bound_members | {PAYLOAD_MEMBER}:
        raise ArchiveError("Archive contains unbound file members")

    created_paths: list[str] = []
    try:
        for relative_path, file_data in writes:
            _path, created = atomic_write(relative_path, file_data)
            if created:
                created_paths.append(relative_path)
        for table_name, model in EXPORT_MODELS:
            for row in decoded_tables[table_name]:
                if table_name in {"candidate_profiles", "applications", "workflow_runs"}:
                    row["user_id"] = user_id
                if table_name == "applications":
                    row["job_id"] = None
                if table_name == "workflow_runs":
                    row["lease_owner"] = None
                    row["lease_expires_at"] = None
                    if row.get("status") == "completed":
                        # Compatibility for early format-v1 archives written before the
                        # durable workflow state machine standardized on "succeeded".
                        row["status"] = "succeeded"
                    elif row.get("status") not in {"succeeded", "failed", "cancelled"}:
                        row["status"] = "cancelled"
                        row["error_code"] = "restored_without_execution"
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

    return RestoreResponse(
        format_version=manifest.format_version,
        archive_sha256=_digest(data),
        restored_records=manifest.record_counts,
        restored_files=len(writes),
    )
