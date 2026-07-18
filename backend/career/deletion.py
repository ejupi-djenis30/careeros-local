import logging
import os
import shutil
import uuid
from pathlib import Path

from sqlalchemy import exists, text
from sqlalchemy.orm import Session

from backend.ai.models import AIExecution
from backend.applications.models import Application
from backend.career.models import CandidateProfile, CareerAsset
from backend.desktop.lifecycle import desktop_vault_lock
from backend.inference.managed_runtime import erase_managed_runtime_installation
from backend.models import Job, ScrapedJob, SearchProfile, User
from backend.resumes.models import ResumeArtifact, ResumeDraft, ResumeVersion
from backend.storage.atomic import data_root, resolve_data_path
from backend.workflows.models import WorkflowRun

logger = logging.getLogger(__name__)


class VaultDeletionError(RuntimeError):
    pass


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
    paths: set[str] = set()
    assets = db.query(CareerAsset).filter(CareerAsset.profile_id == profile_id).all()
    for asset in assets:
        shared = (
            db.query(CareerAsset.id)
            .filter(
                CareerAsset.storage_path == asset.storage_path,
                CareerAsset.profile_id != profile_id,
            )
            .first()
        )
        if shared is None:
            paths.add(asset.storage_path)

    artifacts = (
        db.query(ResumeArtifact)
        .join(ResumeVersion, ResumeArtifact.version_id == ResumeVersion.id)
        .join(ResumeDraft, ResumeVersion.draft_id == ResumeDraft.id)
        .filter(ResumeDraft.profile_id == profile_id)
        .all()
    )
    for artifact in artifacts:
        shared = (
            db.query(ResumeArtifact.id)
            .filter(
                ResumeArtifact.storage_path == artifact.storage_path,
                ResumeArtifact.id != artifact.id,
            )
            .first()
        )
        if shared is None:
            paths.add(artifact.storage_path)
    return paths


def _stage_files(relative_paths: set[str], operation_id: str) -> list[tuple[Path, Path]]:
    staged: list[tuple[Path, Path]] = []
    try:
        for relative_path in sorted(relative_paths):
            source = resolve_data_path(relative_path)
            if not source.exists():
                continue
            destination = resolve_data_path(Path(".trash") / operation_id / relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise VaultDeletionError("Deletion staging path already exists")
            os.replace(source, destination)
            staged.append((source, destination))
    except Exception:
        _restore_files(staged)
        raise
    return staged


def _restore_files(staged: list[tuple[Path, Path]]) -> None:
    for source, destination in reversed(staged):
        if not destination.exists():
            continue
        source.parent.mkdir(parents=True, exist_ok=True)
        os.replace(destination, source)


def delete_complete_vault(
    db: Session, user_id: int, *, erase_managed_runtime: bool = False
) -> dict[str, int]:
    with desktop_vault_lock():
        operation_id = str(uuid.uuid4())
        staged: list[tuple[Path, Path]] = []
        try:
            _enable_sqlite_secure_delete(db)
            profile = (
                db.query(CandidateProfile)
                .filter(CandidateProfile.user_id == user_id)
                .first()
            )
            user = db.get(User, user_id)
            paths = _exclusive_storage_paths(db, profile.id) if profile else set()
            scraped_job_ids = {
                scraped_job_id
                for (scraped_job_id,) in db.query(Job.scraped_job_id)
                .filter(Job.user_id == user_id)
                .distinct()
                .all()
            }
            exclusive_scraped_job_ids = (
                [
                    scraped_job_id
                    for (scraped_job_id,) in db.query(ScrapedJob.id)
                    .filter(
                        ScrapedJob.id.in_(scraped_job_ids),
                        ~exists().where(
                            Job.scraped_job_id == ScrapedJob.id,
                            Job.user_id != user_id,
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
                .filter(SearchProfile.user_id == user_id)
                .count(),
                "jobs": db.query(Job).filter(Job.user_id == user_id).count(),
                "scraped_jobs": len(exclusive_scraped_job_ids),
                "preference_signals": int(
                    user is not None
                    and (
                        user.preference_signals is not None
                        or user.preference_updated_at is not None
                    )
                ),
                "applications": db.query(Application)
                .filter(Application.user_id == user_id)
                .count(),
                "workflows": db.query(WorkflowRun)
                .filter(WorkflowRun.user_id == user_id)
                .count(),
                "ai_executions": db.query(AIExecution)
                .filter(AIExecution.user_id == user_id)
                .count(),
                "files": 0,
                "model_files": 0,
                "model_bytes": 0,
            }
            staged = _stage_files(paths, operation_id)
            counts["files"] = len(staged)

            db.query(AIExecution).filter(AIExecution.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(Application).filter(Application.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(WorkflowRun).filter(WorkflowRun.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(Job).filter(Job.user_id == user_id).delete(synchronize_session=False)
            db.query(SearchProfile).filter(SearchProfile.user_id == user_id).delete(
                synchronize_session=False
            )
            if exclusive_scraped_job_ids:
                db.query(ScrapedJob).filter(
                    ScrapedJob.id.in_(exclusive_scraped_job_ids)
                ).delete(synchronize_session=False)
            if user is not None:
                user.preference_signals = None
                user.preference_updated_at = None
            if profile is not None:
                db.delete(profile)
            db.commit()
        except Exception:
            db.rollback()
            _restore_files(staged)
            raise

        trash = data_root() / ".trash" / operation_id
        try:
            shutil.rmtree(trash, ignore_errors=False)
            trash_parent = trash.parent
            if trash_parent.exists() and not any(trash_parent.iterdir()):
                trash_parent.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.critical("Vault file cleanup failed for operation_id=%s", operation_id)
            raise VaultDeletionError(
                "Database rows were deleted but staged files could not be removed"
            ) from exc

        try:
            _sanitize_sqlite_storage(db)
        except VaultDeletionError:
            logger.critical("SQLite vault sanitization failed")
            raise

        if erase_managed_runtime:
            counts.update(erase_managed_runtime_installation())
        return counts
