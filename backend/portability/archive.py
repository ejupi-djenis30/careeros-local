import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
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
from backend.models import Job, ScrapedJob, SearchProfile, User
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
    ("search_profiles", SearchProfile),
    ("scraped_jobs", ScrapedJob),
    ("jobs", Job),
    ("applications", Application),
    ("application_events", ApplicationEvent),
    ("coach_conversations", CoachConversation),
    ("coach_messages", CoachMessage),
    ("workflow_runs", WorkflowRun),
    ("ai_executions", AIExecution),
]
MODEL_BY_TABLE = dict(EXPORT_MODELS)

# A scraped listing is shared by every user who saved the same provider record.
# ``source_query`` describes how one user discovered that listing, so it must
# never leave the originating vault as part of the shared record.
SCRAPED_JOB_PRIVATE_FIELDS = frozenset({"source_query"})

# Locks and progress payloads describe an in-flight process, not durable search
# configuration. Excluding them also keeps a backup from retaining stale query
# progress that restore must never resume.
SEARCH_PROFILE_RUNTIME_FIELDS = frozenset(
    {
        "search_lock_token",
        "search_lock_state",
        "search_lock_acquired_at",
        "search_status_state",
        "search_status_payload",
        "search_status_started_at",
        "search_status_updated_at",
        "search_status_finished_at",
    }
)


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
    user = db.get(User, user_id)
    if user is None:
        raise ArchiveError("The local vault owner does not exist")
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
    search_profiles = db.query(SearchProfile).filter(SearchProfile.user_id == user_id).all()
    jobs = db.query(Job).filter(Job.user_id == user_id).all()
    scraped_job_ids = {job.scraped_job_id for job in jobs}
    scraped_jobs = (
        db.query(ScrapedJob).filter(ScrapedJob.id.in_(scraped_job_ids)).all()
        if scraped_job_ids
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
        "search_profiles": search_profiles,
        "scraped_jobs": scraped_jobs,
        "jobs": jobs,
        "applications": applications,
        "application_events": application_events,
        "coach_conversations": conversations,
        "coach_messages": messages,
        "workflow_runs": workflows,
        "ai_executions": executions,
        "preference_signals": [user],
    }


@contextmanager
def _consistent_export_snapshot(db: Session) -> Iterator[None]:
    """Run all archive reads against one committed database snapshot.

    Authentication may already have opened a SQLAlchemy transaction without
    opening a SQLite transaction at the driver level. Start the snapshot
    explicitly so later table reads cannot observe a concurrent commit. A
    repeatable-read transaction provides the equivalent guarantee for the
    non-SQLite development configuration.
    """

    if db.new or db.dirty or db.deleted:
        raise ArchiveError("Backup requires committed vault state")

    # End the request's read-only authentication transaction before selecting
    # the isolation level for the export snapshot.
    db.rollback()
    bind = db.get_bind()
    if bind.dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN")
    else:
        db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    try:
        yield
    finally:
        # Export is read-only. Rolling back releases the snapshot without
        # introducing a commit into the caller's session lifecycle.
        db.rollback()


def export_archive(db: Session, user_id: int) -> bytes:
    with desktop_vault_lock(), _consistent_export_snapshot(db):
        rows = _queries(db, user_id)
        if not rows["candidate_profiles"]:
            raise ArchiveError("There is no career vault data to export")

        tables: dict[str, list[dict[str, Any]]] = {}
        user_scoped = {
            "candidate_profiles",
            "search_profiles",
            "jobs",
            "applications",
            "workflow_runs",
            "ai_executions",
        }
        for table_name, _model in EXPORT_MODELS:
            omit = {"user_id"} if table_name in user_scoped else set()
            if table_name == "scraped_jobs":
                omit.update(SCRAPED_JOB_PRIVATE_FIELDS)
            elif table_name == "search_profiles":
                omit.update(SEARCH_PROFILE_RUNTIME_FIELDS)
            tables[table_name] = [_row(item, omit=omit) for item in rows[table_name]]
        owner = rows["preference_signals"][0]
        tables["preference_signals"] = [
            {
                "preference_signals": _json_value(owner.preference_signals),
                "preference_updated_at": _json_value(owner.preference_updated_at),
            }
        ]

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
