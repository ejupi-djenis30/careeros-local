import logging
import os
import shutil
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from backend.ai.models import AIExecution
from backend.applications.models import Application
from backend.career.models import CandidateProfile, CareerAsset
from backend.desktop.lifecycle import desktop_vault_lock
from backend.inference.managed_runtime import erase_managed_runtime_installation
from backend.resumes.models import ResumeArtifact, ResumeDraft, ResumeVersion
from backend.storage.atomic import data_root, resolve_data_path
from backend.workflows.models import WorkflowRun

logger = logging.getLogger(__name__)


class VaultDeletionError(RuntimeError):
    pass


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
        profile = db.query(CandidateProfile).filter(CandidateProfile.user_id == user_id).first()
        operation_id = str(uuid.uuid4())
        paths = _exclusive_storage_paths(db, profile.id) if profile else set()
        staged = _stage_files(paths, operation_id)
        counts = {
            "profiles": 1 if profile else 0,
            "applications": db.query(Application).filter(Application.user_id == user_id).count(),
            "workflows": db.query(WorkflowRun).filter(WorkflowRun.user_id == user_id).count(),
            "ai_executions": db.query(AIExecution).filter(AIExecution.user_id == user_id).count(),
            "files": len(staged),
            "model_files": 0,
            "model_bytes": 0,
        }
        try:
            db.query(AIExecution).filter(AIExecution.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(Application).filter(Application.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(WorkflowRun).filter(WorkflowRun.user_id == user_id).delete(
                synchronize_session=False
            )
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

        if erase_managed_runtime:
            counts.update(erase_managed_runtime_installation())
        return counts
