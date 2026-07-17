import zipfile
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy.orm import Session

from backend.ai.models import AIExecution
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
from backend.desktop.lifecycle import desktop_vault_lock
from backend.portability.manifest import (
    ARCHIVE_FORMAT,
    CURRENT_ARCHIVE_VERSION,
    MANIFEST_MEMBER,
    PAYLOAD_MEMBER,
    canonical_json,
    sha256,
    validate_manifest_compatibility,
)
from backend.portability.schemas import ArchiveEntry, ArchiveManifest
from backend.resumes.models import ResumeArtifact, ResumeDraft, ResumeVersion
from backend.storage.atomic import StorageWriteError, read_verified
from backend.workflows.models import WorkflowRun


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
    ("ai_executions", AIExecution),
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
    executions = db.query(AIExecution).filter(AIExecution.user_id == user_id).all()
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
        "ai_executions": executions,
    }


def export_archive(db: Session, user_id: int) -> bytes:
    with desktop_vault_lock():
        rows = _queries(db, user_id)
        if not rows["candidate_profiles"]:
            raise ArchiveError("There is no career vault data to export")

        tables: dict[str, list[dict[str, Any]]] = {}
        user_scoped = {
            "candidate_profiles",
            "applications",
            "workflow_runs",
            "ai_executions",
        }
        for table_name, _model in EXPORT_MODELS:
            omit = {"user_id"} if table_name in user_scoped else set()
            tables[table_name] = [_row(item, omit=omit) for item in rows[table_name]]

        bindings: list[dict[str, str]] = []
        file_members: dict[str, bytes] = {}
        for table_name, directory, records in (
            ("career_assets", "career-assets", rows["career_assets"]),
            ("resume_artifacts", "resume-artifacts", rows["resume_artifacts"]),
        ):
            for record in records:
                suffix = f".{record.format}" if table_name == "resume_artifacts" else ""
                member = f"files/{directory}/{record.id}{suffix}"
                data = read_verified(record.storage_path, record.sha256)
                if len(data) != record.byte_size:
                    raise ArchiveError(f"{table_name} record {record.id} failed its size check")
                file_members[member] = data
                bindings.append(
                    {
                        "table": table_name,
                        "record_id": record.id,
                        "storage_path": record.storage_path,
                        "member": member,
                    }
                )

        payload = canonical_json({"tables": tables, "file_bindings": bindings})
        members = {PAYLOAD_MEMBER: payload, **file_members}
        entries = [
            ArchiveEntry(path=path, sha256=sha256(data), byte_size=len(data))
            for path, data in sorted(members.items())
        ]
        manifest = ArchiveManifest(
            format=ARCHIVE_FORMAT,
            format_version=CURRENT_ARCHIVE_VERSION,
            created_at=datetime.now(timezone.utc),
            owner_scope="career-vault",
            record_counts={name: len(items) for name, items in tables.items()},
            entries=entries,
        )
        manifest_data = canonical_json(manifest.model_dump(mode="json"))

        output = BytesIO()
        try:
            with zipfile.ZipFile(
                output, mode="w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr(MANIFEST_MEMBER, manifest_data)
                for path, data in sorted(members.items()):
                    archive.writestr(path, data)
            result = output.getvalue()
        except (OSError, MemoryError) as exc:
            raise StorageWriteError(
                "Backup creation could not finish; verify free disk space and retry."
            ) from exc
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
        try:
            validate_manifest_compatibility(manifest)
        except ValueError as exc:
            raise ArchiveError(str(exc)) from exc
        expected = {entry.path for entry in manifest.entries} | {MANIFEST_MEMBER}
        if expected != set(names):
            raise ArchiveError("Archive members do not match the manifest")
        members: dict[str, bytes] = {}
        for entry in manifest.entries:
            member = archive.read(entry.path)
            if len(member) != entry.byte_size or sha256(member) != entry.sha256:
                raise ArchiveError(f"Archive member failed integrity check: {entry.path}")
            members[entry.path] = member
        return manifest, members
