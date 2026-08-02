import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import exists, text
from sqlalchemy.orm import Session

from backend.ai.models import AIExecution
from backend.applications.models import Application, ApplicationDossierDraft
from backend.automation.models import AutomationGrant
from backend.career.asset_publication import reconcile_asset_publication_journals
from backend.career.models import CandidateProfile, CareerAsset
from backend.core.diagnostics import FailureCode, diagnose_failure, log_failure
from backend.desktop.lifecycle import desktop_vault_lock
from backend.inference.managed_runtime import erase_managed_runtime_installation
from backend.models import Job, ScrapedJob, SearchProfile, User
from backend.models.auth_session import AuthSession
from backend.models.user import (
    VAULT_STATE_ERASURE_PENDING,
    VAULT_STATE_READY,
    VAULT_STATE_RESET_PENDING,
    VAULT_STATE_RESTORE_PENDING,
)
from backend.portability.journal import (
    RestoreJournalError,
    clear_restore_journal,
    restore_journal_paths,
)
from backend.providers.configuration.models import JobProviderConfiguration
from backend.resumes.models import ResumeArtifact, ResumeDraft, ResumeVersion
from backend.resumes.storage import all_resume_publication_journals
from backend.services.auth import (
    ACCESS_PURPOSE_SESSION,
    ACCESS_PURPOSE_VAULT_MAINTENANCE,
)
from backend.services.auth_sessions import (
    erasure_pending_digest,
    is_erasure_pending_session,
)
from backend.storage.atomic import (
    durable_mkdir,
    durable_replace,
    fsync_directory,
    resolve_data_path,
)
from backend.workflows.models import WorkflowRun

logger = logging.getLogger(__name__)


class VaultDeletionError(RuntimeError):
    pass


class VaultMaintenanceConflictError(VaultDeletionError):
    """A different durable vault operation owns the account guard."""


def _uses_sqlite(db: Session) -> bool:
    return db.get_bind().dialect.name == "sqlite"


def _enable_sqlite_secure_delete(db: Session) -> None:
    """Ensure rows deleted by this transaction are overwritten in SQLite pages."""
    if not _uses_sqlite(db):
        return
    try:
        enabled = db.execute(text("PRAGMA secure_delete=ON")).scalar_one()
    except Exception as exc:
        raise VaultDeletionError("Could not enable secure SQLite deletion") from exc
    if enabled != 1:
        raise VaultDeletionError("Could not enable secure SQLite deletion")


def _checkpoint(connection) -> None:
    result = connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)").one()
    if result[0] != 0:
        raise VaultDeletionError("SQLite vault sanitization was blocked by another connection")


def _sanitize_sqlite_storage(db: Session) -> None:
    """Remove deleted content from the database file and its WAL.

    This runs only after the deletion transaction committed. VACUUM cannot run
    inside a transaction and takes an exclusive SQLite lock, so use a dedicated
    autocommit connection while the desktop vault lock is still held.
    """
    if not _uses_sqlite(db):
        return

    bind = db.get_bind()
    engine = bind.engine
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            # Flush and truncate pre-VACUUM WAL frames, then truncate the WAL
            # produced by VACUUM itself.
            _checkpoint(connection)
            connection.exec_driver_sql("VACUUM")
            _checkpoint(connection)
    except VaultDeletionError:
        raise
    except Exception as exc:
        raise VaultDeletionError("SQLite vault sanitization failed") from exc


def _exclusive_storage_paths(db: Session, profile_id: str) -> set[str]:
    paths = {
        storage_path
        for (storage_path,) in db.query(CareerAsset.storage_path)
        .filter(CareerAsset.profile_id == profile_id)
        .all()
    }
    paths.update(
        storage_path
        for (storage_path,) in db.query(ResumeArtifact.storage_path)
        .join(ResumeVersion, ResumeArtifact.version_id == ResumeVersion.id)
        .join(ResumeDraft, ResumeVersion.draft_id == ResumeDraft.id)
        .filter(ResumeDraft.profile_id == profile_id)
        .all()
    )
    return paths - _foreign_profile_storage_paths(
        db,
        profile_id=profile_id,
        candidate_paths=paths,
    )


def _foreign_profile_storage_paths(
    db: Session,
    *,
    profile_id: str,
    candidate_paths: set[str],
) -> set[str]:
    """Find candidate paths that remain owned by another profile.

    Keep batches below conservative SQLite bind-parameter limits. Recovery is
    bounded to four paths per journal, but a full journal namespace can still
    contain tens of thousands of paths.
    """

    foreign: set[str] = set()
    ordered_paths = sorted(candidate_paths)
    for offset in range(0, len(ordered_paths), 500):
        batch = ordered_paths[offset : offset + 500]
        foreign.update(
            storage_path
            for (storage_path,) in db.query(CareerAsset.storage_path)
            .filter(
                CareerAsset.storage_path.in_(batch),
                CareerAsset.profile_id != profile_id,
            )
            .distinct()
            .all()
        )
        foreign.update(
            storage_path
            for (storage_path,) in db.query(ResumeArtifact.storage_path)
            .join(ResumeVersion, ResumeArtifact.version_id == ResumeVersion.id)
            .join(ResumeDraft, ResumeVersion.draft_id == ResumeDraft.id)
            .filter(
                ResumeArtifact.storage_path.in_(batch),
                ResumeDraft.profile_id != profile_id,
            )
            .distinct()
            .all()
        )
    return foreign


def _exclusive_resume_publication_journal_paths(
    db: Session,
    *,
    profile_id: str,
    draft_ids: set[str],
) -> tuple[set[str], set[str]]:
    """Return owned recovery paths and artifact claims made by other drafts."""

    journals = all_resume_publication_journals()
    owned_journals = [journal for journal in journals if journal.draft_id in draft_ids]
    foreign_journal_paths = {
        artifact_path
        for journal in journals
        if journal.draft_id not in draft_ids
        for artifact_path in journal.artifact_paths
    }
    if not owned_journals:
        return set(), foreign_journal_paths

    owned_artifact_paths = {
        artifact_path for journal in owned_journals for artifact_path in journal.artifact_paths
    }
    for artifact_path in owned_artifact_paths:
        parts = Path(artifact_path).parts
        if len(parts) != 4 or parts[1] != profile_id:
            raise VaultDeletionError(
                "Resume publication recovery metadata does not match its owning profile"
            )

    shared_paths = foreign_journal_paths | _foreign_profile_storage_paths(
        db,
        profile_id=profile_id,
        candidate_paths=owned_artifact_paths,
    )
    owned_paths = {journal.relative_path for journal in owned_journals}
    owned_paths.update(owned_artifact_paths - shared_paths)
    return owned_paths, foreign_journal_paths


def _exclusive_restore_journal_paths(db: Session, user_id: int) -> set[str]:
    """Return journaled restore paths not bound to a different local account."""

    exclusive: set[str] = set()
    for storage_path in restore_journal_paths(user_id):
        shared_asset = (
            db.query(CareerAsset.id)
            .join(CandidateProfile, CareerAsset.profile_id == CandidateProfile.id)
            .filter(
                CareerAsset.storage_path == storage_path,
                CandidateProfile.user_id != user_id,
            )
            .first()
        )
        shared_artifact = (
            db.query(ResumeArtifact.id)
            .join(ResumeVersion, ResumeArtifact.version_id == ResumeVersion.id)
            .join(ResumeDraft, ResumeVersion.draft_id == ResumeDraft.id)
            .join(CandidateProfile, ResumeDraft.profile_id == CandidateProfile.id)
            .filter(
                ResumeArtifact.storage_path == storage_path,
                CandidateProfile.user_id != user_id,
            )
            .first()
        )
        if shared_asset is None and shared_artifact is None:
            exclusive.add(storage_path)
    return exclusive


def _validated_user_id(user_id: int) -> int:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise VaultDeletionError("Invalid user identifier for vault deletion")
    return int(user_id)


def _user_trash_namespace(user_id: int) -> str:
    return f"user-{_validated_user_id(user_id):d}"


def _stage_files(relative_paths: set[str], operation_id: str) -> list[tuple[Path, Path]]:
    staged: list[tuple[Path, Path]] = []
    try:
        for relative_path in sorted(relative_paths):
            source = resolve_data_path(relative_path)
            if not source.exists():
                continue
            destination = resolve_data_path(f".trash/{operation_id}/{relative_path}")
            durable_mkdir(destination.parent)
            if destination.exists():
                raise VaultDeletionError("Deletion staging path already exists")
            durable_replace(source, destination)
            fsync_directory(destination.parent)
            fsync_directory(source.parent)
            staged.append((source, destination))
    except Exception:
        _restore_files(staged)
        raise
    return staged


def _restore_files(staged: list[tuple[Path, Path]]) -> None:
    for source, destination in reversed(staged):
        if not destination.exists():
            continue
        durable_mkdir(source.parent)
        durable_replace(destination, source)
        fsync_directory(source.parent)
        fsync_directory(destination.parent)


def _remove_staged_files_for_user(user_id: int) -> None:
    """Remove this user's committed trash, including leftovers from a failed retry.

    Staging is namespaced per user so retrying one account cannot remove another
    account's interrupted operation. The database transaction commits before this
    function runs; a failure therefore leaves the private files in the same
    discoverable namespace for the next complete-vault deletion attempt.
    """
    namespace = _user_trash_namespace(user_id)
    try:
        trash = resolve_data_path(f".trash/{namespace}")
        shutil.rmtree(trash, ignore_errors=False)
        fsync_directory(trash.parent)
    except FileNotFoundError:
        return
    except (OSError, ValueError) as exc:
        raise VaultDeletionError(
            "Staged private files could not be removed; retry complete vault deletion"
        ) from exc

    trash_parent = trash.parent
    try:
        if not any(trash_parent.iterdir()):
            trash_parent.rmdir()
    except OSError:
        # The user-scoped tree is already gone; an empty metadata directory is
        # not private residue and can be left for a later cleanup.
        pass


def _finish_committed_deletion(db: Session, user_id: int) -> None:
    """Attempt every post-commit privacy cleanup before reporting failure."""
    sanitization_error: Exception | None = None
    file_cleanup_error: Exception | None = None

    try:
        _sanitize_sqlite_storage(db)
    except Exception as exc:
        sanitization_error = exc
        diagnostic = diagnose_failure(exc, FailureCode.VAULT_SANITIZATION_FAILED)
        log_failure(logger, diagnostic, level=logging.CRITICAL)

    try:
        _remove_staged_files_for_user(user_id)
    except Exception as exc:
        file_cleanup_error = exc
        diagnostic = diagnose_failure(exc, FailureCode.VAULT_FILE_CLEANUP_FAILED)
        log_failure(logger, diagnostic, level=logging.CRITICAL)

    if sanitization_error is not None and file_cleanup_error is not None:
        raise VaultDeletionError(
            "Database rows were deleted, but SQLite sanitization and staged file "
            "cleanup are incomplete; retry complete vault deletion"
        ) from sanitization_error
    if sanitization_error is not None:
        raise VaultDeletionError(
            "Database rows were deleted, but SQLite sanitization is incomplete; "
            "retry complete vault deletion"
        ) from sanitization_error
    if file_cleanup_error is not None:
        raise VaultDeletionError(
            "Database rows were deleted and SQLite sanitization completed, but staged "
            "private files remain; retry complete vault deletion"
        ) from file_cleanup_error


def _remove_auth_sessions_after_cleanup(db: Session, user_id: int) -> int:
    """Finalize device erasure only after every retryable cleanup has succeeded.

    The current family must remain live while staged files or runtime bytes still
    need a user-authorized retry. A failed final commit rolls back, preserving that
    retry path; successful deletion makes all owned access bearers fail immediately.
    """

    removed = 0
    commit_attempted = False
    try:
        removed = (
            db.query(AuthSession)
            .filter(AuthSession.user_id == user_id)
            .delete(synchronize_session=False)
        )
        user = db.get(User, user_id)
        if user is None:
            raise VaultDeletionError("The local account no longer exists")
        user.vault_lifecycle_state = VAULT_STATE_READY
        user.vault_maintenance_fingerprint = None
        commit_attempted = True
        db.commit()
    except Exception as exc:
        db.rollback()
        if commit_attempted:
            try:
                if _auth_session_cleanup_was_published(db, user_id):
                    db.expire_all()
                    return int(removed)
            except Exception as verification_error:
                raise VaultDeletionError(
                    "Session finalization commit outcome could not be verified"
                ) from verification_error
        raise VaultDeletionError(
            "Private data cleanup completed, but session finalization failed; "
            "retry complete vault deletion"
        ) from exc
    return int(removed)


def _auth_session_cleanup_was_published(db: Session, user_id: int) -> bool:
    """Check final device-erasure authority state from a fresh locked snapshot."""

    bind = db.get_bind()
    with Session(bind=bind, expire_on_commit=False) as verification:
        if bind.dialect.name == "sqlite":
            verification.execute(text("BEGIN IMMEDIATE"))
        user_query = verification.query(User).filter(User.id == user_id)
        if bind.dialect.name != "sqlite":
            user_query = user_query.with_for_update()
        owner = user_query.one_or_none()
        published = (
            owner is not None
            and owner.vault_lifecycle_state == VAULT_STATE_READY
            and owner.vault_maintenance_fingerprint is None
            and verification.query(AuthSession.id).filter(AuthSession.user_id == user_id).first()
            is None
        )
        verification.rollback()
        return published


def _begin_erasure_pending(
    db: Session,
    user_id: int,
    session_id: str,
) -> int:
    """Block ordinary authority in the same commit that removes vault records."""

    sessions = db.query(AuthSession).filter(AuthSession.user_id == user_id).all()
    current = next((session for session in sessions if session.id == session_id), None)
    now = datetime.now(timezone.utc)
    if (
        current is None
        or (current.revoked_at is not None and not is_erasure_pending_session(current))
        or current.expires_at <= now
    ):
        raise VaultMaintenanceConflictError("The erasure authority is no longer valid")

    for session in sessions:
        if session.id != session_id and session.revoked_at is None:
            session.revoked_at = now
            session.updated_at = now
    current.refresh_jti_digest = erasure_pending_digest(session_id)
    current.revoked_at = current.revoked_at or now
    current.updated_at = now
    return len(sessions)


def _begin_live_maintenance_pending(
    db: Session,
    user_id: int,
    session_id: str,
) -> None:
    """Keep only the presented family live while reset/restore is unfinished."""

    sessions = db.query(AuthSession).filter(AuthSession.user_id == user_id).all()
    current = next((session for session in sessions if session.id == session_id), None)
    now = datetime.now(timezone.utc)
    if current is None or current.revoked_at is not None or current.expires_at <= now:
        raise VaultMaintenanceConflictError("The vault maintenance authority is no longer valid")
    for session in sessions:
        if session.id != session_id and session.revoked_at is None:
            session.revoked_at = now
            session.updated_at = now


def begin_vault_maintenance(
    db: Session,
    user_id: int,
    session_id: str,
    lifecycle_state: str,
    *,
    token_purpose: str,
    maintenance_fingerprint: str | None = None,
) -> bool:
    """Persist a restart-durable guard before destructive work begins."""

    if lifecycle_state not in {
        VAULT_STATE_RESET_PENDING,
        VAULT_STATE_RESTORE_PENDING,
        VAULT_STATE_ERASURE_PENDING,
    }:
        raise VaultDeletionError("Invalid vault maintenance state")
    if lifecycle_state == VAULT_STATE_RESTORE_PENDING:
        if (
            not isinstance(maintenance_fingerprint, str)
            or len(maintenance_fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in maintenance_fingerprint)
        ):
            raise VaultDeletionError("Restore maintenance requires an archive fingerprint")
    elif maintenance_fingerprint is not None:
        raise VaultDeletionError("Only restore maintenance accepts a fingerprint")
    try:
        if _uses_sqlite(db):
            db.commit()
            db.execute(text("BEGIN IMMEDIATE"))
        user = (
            db.query(User)
            .filter(User.id == _validated_user_id(user_id))
            .with_for_update()
            .populate_existing()
            .one_or_none()
        )
        if user is None:
            raise VaultMaintenanceConflictError("The local account no longer exists")
        allowed_current_states = {VAULT_STATE_READY, lifecycle_state}
        if lifecycle_state == VAULT_STATE_ERASURE_PENDING:
            allowed_current_states.update({VAULT_STATE_RESET_PENDING, VAULT_STATE_RESTORE_PENDING})
        if user.vault_lifecycle_state not in allowed_current_states:
            raise VaultMaintenanceConflictError("Another vault maintenance operation is pending")
        expected_purpose = (
            ACCESS_PURPOSE_SESSION
            if user.vault_lifecycle_state == VAULT_STATE_READY
            else ACCESS_PURPOSE_VAULT_MAINTENANCE
        )
        if token_purpose != expected_purpose:
            raise VaultMaintenanceConflictError("The vault maintenance authority is stale")
        transitioned_from_ready = user.vault_lifecycle_state == VAULT_STATE_READY
        if (
            lifecycle_state == VAULT_STATE_RESTORE_PENDING
            and user.vault_lifecycle_state == VAULT_STATE_RESTORE_PENDING
            and user.vault_maintenance_fingerprint != maintenance_fingerprint
        ):
            raise VaultMaintenanceConflictError("Retry restore with the same verified archive")
        if lifecycle_state == VAULT_STATE_ERASURE_PENDING:
            _begin_erasure_pending(db, user.id, session_id)
        else:
            _begin_live_maintenance_pending(db, user.id, session_id)
        user.vault_lifecycle_state = lifecycle_state
        user.vault_maintenance_fingerprint = maintenance_fingerprint
        db.commit()
        return transitioned_from_ready
    except Exception:
        db.rollback()
        raise


def clear_vault_maintenance(
    db: Session,
    user_id: int,
    expected_state: str,
) -> None:
    """Clear exactly one completed or fully rolled-back maintenance operation."""

    if expected_state not in {
        VAULT_STATE_RESET_PENDING,
        VAULT_STATE_RESTORE_PENDING,
    }:
        raise VaultDeletionError("Invalid clearable vault maintenance state")

    validated_user_id = _validated_user_id(user_id)
    try:
        # One conditional UPDATE is the state-ownership check. In particular, a
        # concurrent erasure that supersedes restore cannot be overwritten by a
        # stale ORM identity after restore cleanup has finished.
        cleared = (
            db.query(User)
            .filter(
                User.id == validated_user_id,
                User.vault_lifecycle_state == expected_state,
            )
            .update(
                {
                    User.vault_lifecycle_state: VAULT_STATE_READY,
                    User.vault_maintenance_fingerprint: None,
                },
                synchronize_session=False,
            )
        )
        if cleared == 0:
            db.expire_all()
            user = db.get(User, validated_user_id)
            if user is None:
                raise VaultDeletionError("The local account no longer exists")
            if user.vault_lifecycle_state != VAULT_STATE_READY:
                raise VaultMaintenanceConflictError(
                    "A different vault maintenance operation is pending"
                )
        db.commit()
    except Exception:
        db.rollback()
        raise


def _deletion_commit_was_published(
    db: Session,
    *,
    user_id: int,
    expected_state: str,
    exclusive_scraped_job_ids: list[int],
) -> bool:
    """Check the complete deletion postcondition from a fresh locked snapshot."""

    bind = db.get_bind()
    with Session(bind=bind, expire_on_commit=False) as verification:
        if bind.dialect.name == "sqlite":
            verification.execute(text("BEGIN IMMEDIATE"))
        user_query = verification.query(User).filter(User.id == user_id)
        if bind.dialect.name != "sqlite":
            user_query = user_query.with_for_update()
        owner = user_query.one_or_none()
        if owner is None or owner.vault_lifecycle_state != expected_state:
            raise VaultDeletionError("Vault deletion commit identity is inconsistent")

        remaining = any(
            query.first() is not None
            for query in (
                verification.query(CandidateProfile.id).filter(CandidateProfile.user_id == user_id),
                verification.query(JobProviderConfiguration.id).filter(
                    JobProviderConfiguration.user_id == user_id
                ),
                verification.query(SearchProfile.id).filter(SearchProfile.user_id == user_id),
                verification.query(Job.id).filter(Job.user_id == user_id),
                verification.query(Application.id).filter(Application.user_id == user_id),
                verification.query(WorkflowRun.id).filter(WorkflowRun.user_id == user_id),
                verification.query(AIExecution.id).filter(AIExecution.user_id == user_id),
                verification.query(AutomationGrant.id).filter(AutomationGrant.user_id == user_id),
            )
        )
        if exclusive_scraped_job_ids:
            remaining = remaining or (
                verification.query(ScrapedJob.id)
                .filter(ScrapedJob.id.in_(exclusive_scraped_job_ids))
                .first()
                is not None
            )
        remaining = remaining or (
            owner.preference_signals is not None or owner.preference_updated_at is not None
        )
        verification.rollback()
        return not remaining


def delete_complete_vault(
    db: Session,
    user_id: int,
    *,
    erase_managed_runtime: bool = False,
    erase_auth_sessions: bool = False,
    erasure_session_id: str | None = None,
    maintenance_session_id: str | None = None,
) -> dict[str, int]:
    validated_user_id = _validated_user_id(user_id)
    if erase_auth_sessions and not erasure_session_id:
        raise VaultDeletionError("Complete erasure requires a session-bound retry authority")
    if not erase_auth_sessions and not maintenance_session_id:
        raise VaultDeletionError("Vault reset requires a session-bound maintenance authority")
    expected_state = (
        VAULT_STATE_ERASURE_PENDING if erase_auth_sessions else VAULT_STATE_RESET_PENDING
    )
    with desktop_vault_lock():
        operation_id = f"{_user_trash_namespace(validated_user_id)}/{uuid.uuid4().hex}"
        staged: list[tuple[Path, Path]] = []
        commit_attempted = False
        exclusive_scraped_job_ids: list[int] = []
        try:
            if _uses_sqlite(db):
                # Reserve SQLite's only writer before inspecting recovery
                # journals. Publication also takes BEGIN IMMEDIATE, so it can
                # neither create a new owned journal after this scan nor commit
                # resume rows against a profile being erased.
                db.rollback()
                db.execute(text("BEGIN IMMEDIATE"))
            user_query = db.query(User).filter(User.id == validated_user_id)
            if not _uses_sqlite(db):
                user_query = user_query.with_for_update()
            user = user_query.populate_existing().one_or_none()
            if user is None or user.vault_lifecycle_state != expected_state:
                raise VaultDeletionError("Vault maintenance was not prepared")
            _enable_sqlite_secure_delete(db)
            profile_query = db.query(CandidateProfile).filter(
                CandidateProfile.user_id == validated_user_id
            )
            profile = profile_query.populate_existing().one_or_none()
            draft_ids: set[str] = set()
            if profile is not None:
                draft_query = db.query(ResumeDraft.id).filter(ResumeDraft.profile_id == profile.id)
                if not _uses_sqlite(db):
                    draft_query = draft_query.with_for_update()
                draft_ids = {draft_id for (draft_id,) in draft_query.all()}
                if not _uses_sqlite(db):
                    # Use the same draft-then-profile row-lock order as resume
                    # publication to avoid cross-database deadlocks.
                    profile = profile_query.with_for_update().populate_existing().one()
            if _uses_sqlite(db):
                # The writer reservation prevents a publisher from creating a
                # new claim while crash-left asset journals are resolved.
                reconcile_asset_publication_journals(db)
            paths = _exclusive_storage_paths(db, profile.id) if profile else set()
            if profile is not None:
                publication_paths, foreign_recovery_paths = (
                    _exclusive_resume_publication_journal_paths(
                        db, profile_id=profile.id, draft_ids=draft_ids
                    )
                )
                paths.difference_update(foreign_recovery_paths)
                paths.update(publication_paths)
            paths.update(_exclusive_restore_journal_paths(db, validated_user_id))
            scraped_job_ids = {
                scraped_job_id
                for (scraped_job_id,) in db.query(Job.scraped_job_id)
                .filter(Job.user_id == validated_user_id)
                .distinct()
                .all()
            }
            scraped_job_ids.update(
                scraped_job_id
                for (scraped_job_id,) in db.query(Application.scraped_job_id)
                .filter(
                    Application.user_id == validated_user_id,
                    Application.scraped_job_id.is_not(None),
                )
                .distinct()
                .all()
                if scraped_job_id is not None
            )
            exclusive_scraped_job_ids = (
                [
                    scraped_job_id
                    for (scraped_job_id,) in db.query(ScrapedJob.id)
                    .filter(
                        ScrapedJob.id.in_(scraped_job_ids),
                        ~exists().where(
                            Job.scraped_job_id == ScrapedJob.id,
                            Job.user_id != validated_user_id,
                        ),
                        ~exists().where(
                            Application.scraped_job_id == ScrapedJob.id,
                            Application.user_id != validated_user_id,
                        ),
                    )
                    .all()
                ]
                if scraped_job_ids
                else []
            )
            counts = {
                "profiles": 1 if profile else 0,
                "search_profiles": db.query(SearchProfile)
                .filter(SearchProfile.user_id == validated_user_id)
                .count(),
                "job_provider_configurations": db.query(JobProviderConfiguration)
                .filter(JobProviderConfiguration.user_id == validated_user_id)
                .count(),
                "jobs": db.query(Job).filter(Job.user_id == validated_user_id).count(),
                "scraped_jobs": len(exclusive_scraped_job_ids),
                "preference_signals": int(
                    user is not None
                    and (
                        user.preference_signals is not None
                        or user.preference_updated_at is not None
                    )
                ),
                "applications": db.query(Application)
                .filter(Application.user_id == validated_user_id)
                .count(),
                "dossier_drafts": db.query(ApplicationDossierDraft)
                .join(
                    Application,
                    ApplicationDossierDraft.application_id == Application.id,
                )
                .filter(Application.user_id == validated_user_id)
                .count(),
                "workflows": db.query(WorkflowRun)
                .filter(WorkflowRun.user_id == validated_user_id)
                .count(),
                "ai_executions": db.query(AIExecution)
                .filter(AIExecution.user_id == validated_user_id)
                .count(),
                "automation_grants": db.query(AutomationGrant)
                .filter(AutomationGrant.user_id == validated_user_id)
                .count(),
                "auth_sessions": 0,
                "files": 0,
                "model_files": 0,
                "model_bytes": 0,
            }
            staged = _stage_files(paths, operation_id)
            counts["files"] = len(staged)

            db.query(AutomationGrant).filter(AutomationGrant.user_id == validated_user_id).delete(
                synchronize_session=False
            )
            db.query(JobProviderConfiguration).filter(
                JobProviderConfiguration.user_id == validated_user_id
            ).delete(synchronize_session=False)
            db.query(AIExecution).filter(AIExecution.user_id == validated_user_id).delete(
                synchronize_session=False
            )
            db.query(Application).filter(Application.user_id == validated_user_id).delete(
                synchronize_session=False
            )
            db.query(WorkflowRun).filter(WorkflowRun.user_id == validated_user_id).delete(
                synchronize_session=False
            )
            db.query(Job).filter(Job.user_id == validated_user_id).delete(synchronize_session=False)
            db.query(SearchProfile).filter(SearchProfile.user_id == validated_user_id).delete(
                synchronize_session=False
            )
            if exclusive_scraped_job_ids:
                db.query(ScrapedJob).filter(ScrapedJob.id.in_(exclusive_scraped_job_ids)).delete(
                    synchronize_session=False
                )
            if user is not None:
                user.preference_signals = None
                user.preference_updated_at = None
            if profile is not None:
                db.delete(profile)
            commit_attempted = True
            db.commit()
        except Exception as original:
            db.rollback()
            committed = False
            if commit_attempted:
                try:
                    committed = _deletion_commit_was_published(
                        db,
                        user_id=validated_user_id,
                        expected_state=expected_state,
                        exclusive_scraped_job_ids=exclusive_scraped_job_ids,
                    )
                except Exception as verification_error:
                    raise VaultDeletionError(
                        "Vault deletion commit outcome could not be verified; retry complete "
                        "vault deletion"
                    ) from verification_error
            if not committed:
                _restore_files(staged)
                raise original
            db.expire_all()

        _finish_committed_deletion(db, validated_user_id)
        try:
            clear_restore_journal(validated_user_id)
        except RestoreJournalError as exc:
            raise VaultDeletionError(
                "Private data was removed, but restore recovery metadata remains; "
                "retry complete vault deletion"
            ) from exc

        if erase_managed_runtime:
            counts.update(erase_managed_runtime_installation())
        if erase_auth_sessions:
            finalized_sessions = _remove_auth_sessions_after_cleanup(db, validated_user_id)
            counts["auth_sessions"] = max(counts["auth_sessions"], finalized_sessions)
        else:
            assert maintenance_session_id is not None
            _begin_live_maintenance_pending(
                db,
                validated_user_id,
                maintenance_session_id,
            )
            clear_vault_maintenance(
                db,
                validated_user_id,
                VAULT_STATE_RESET_PENDING,
            )
        return counts
