import hashlib
from datetime import datetime, timezone
from functools import partial
from io import BytesIO

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.api.deps import (
    AuthFamilyAuthority,
    get_current_user_id,
    get_vault_maintenance_authority,
    limiter,
    require_vault_maintenance_operation,
)
from backend.api.routes.auth import clear_refresh_cookies
from backend.career.activity import vault_activity_gate
from backend.career.deletion import (
    VaultMaintenanceConflictError,
    begin_vault_maintenance,
    clear_vault_maintenance,
    delete_complete_vault,
)
from backend.career.maintenance import quiesce_user_vault_activity
from backend.core.config import settings
from backend.db.base import get_db
from backend.desktop.lifecycle import VaultLockTimeout
from backend.inference.managed_runtime import quiesce_managed_runtime_installation
from backend.models import User
from backend.models.user import (
    VAULT_STATE_ERASURE_PENDING,
    VAULT_STATE_RESTORE_PENDING,
)
from backend.portability.archive import (
    ArchiveConflictError,
    ArchiveError,
    export_archive,
)
from backend.portability.inspection import inspect_archive
from backend.portability.restore import RestoreRolledBackError, restore_archive
from backend.portability.schemas import ArchiveInspection, RestoreResponse
from backend.services.auth_sessions import issue_maintenance_access
from backend.storage.atomic import StorageWriteError

router = APIRouter()
ERASE_CONFIRMATION = "ERASE-LOCAL-CAREER-DATA"


async def _bounded_archive_bytes(file: UploadFile) -> bytes:
    data = await file.read(settings.PORTABLE_ARCHIVE_MAX_BYTES + 1)
    if len(data) > settings.PORTABLE_ARCHIVE_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "archive_too_large",
                "message": "The backup exceeds the configured size limit.",
            },
        )
    return data


@router.get("/export")
@limiter.limit("5/hour")
def export_portable_archive(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        data = export_archive(db, user_id)
    except VaultLockTimeout as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StorageWriteError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc
    except ArchiveError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return StreamingResponse(
        BytesIO(data),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="careeros-backup-{stamp}.zip"',
            "X-Content-SHA256": hashlib.sha256(data).hexdigest(),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/restore", response_model=RestoreResponse)
@limiter.limit("3/hour")
async def restore_portable_archive(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    authority: AuthFamilyAuthority = Depends(get_vault_maintenance_authority),
    db: Session = Depends(get_db),
) -> RestoreResponse | JSONResponse:
    require_vault_maintenance_operation(authority, VAULT_STATE_RESTORE_PENDING)
    data = await _bounded_archive_bytes(file)
    archive_fingerprint = hashlib.sha256(data).hexdigest()
    transitioned_from_ready = False
    try:
        async with vault_activity_gate.maintenance():
            try:
                transitioned_from_ready = begin_vault_maintenance(
                    db,
                    authority.user_id,
                    authority.session_id,
                    VAULT_STATE_RESTORE_PENDING,
                    token_purpose=authority.token_purpose,
                    maintenance_fingerprint=archive_fingerprint,
                )
                await quiesce_user_vault_activity(db, authority.user_id)
                async with vault_activity_gate.writer():
                    await quiesce_user_vault_activity(db, authority.user_id)
                    result = await run_in_threadpool(
                        restore_archive,
                        db,
                        authority.user_id,
                        data,
                    )
            except RestoreRolledBackError as exc:
                db.rollback()
                # The restore service raises this wrapper only after every
                # journal-owned byte and SQLite rollback remnant is cleaned.
                # That invariant also holds on a restart retry, so the durable
                # pending state can always converge back to ready here.
                clear_vault_maintenance(
                    db,
                    authority.user_id,
                    VAULT_STATE_RESTORE_PENDING,
                )
                raise exc.original
            except (ArchiveConflictError, StorageWriteError, ArchiveError):
                db.rollback()
                if transitioned_from_ready:
                    clear_vault_maintenance(
                        db,
                        authority.user_id,
                        VAULT_STATE_RESTORE_PENDING,
                    )
                raise
    except VaultMaintenanceConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "vault_maintenance_conflict",
                "message": str(exc),
            },
        ) from exc
    except ArchiveConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StorageWriteError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc
    except ArchiveError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        db.expire_all()
        user = db.get(User, authority.user_id)
        if user is not None and user.vault_lifecycle_state == VAULT_STATE_RESTORE_PENDING:
            try:
                retry_token = issue_maintenance_access(db, user).access_token
            except Exception:
                db.rollback()
                retry_token = None
            detail = {
                "code": "restore_cleanup_pending",
                "message": "Restore cleanup is incomplete. Retry with the same backup.",
                "session_state": VAULT_STATE_RESTORE_PENDING,
                "reauth_required": retry_token is None,
            }
            if retry_token is not None:
                detail["maintenance_access_token"] = retry_token
            failure = JSONResponse(
                status_code=500,
                content={"detail": detail},
            )
            clear_refresh_cookies(failure)
            return failure
        raise HTTPException(status_code=500, detail="Local backup restore failed") from exc
    clear_refresh_cookies(response)
    return result


@router.post("/inspect", response_model=ArchiveInspection)
@limiter.limit("6/hour")
async def inspect_portable_archive(
    request: Request,
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ArchiveInspection:
    data = await _bounded_archive_bytes(file)
    try:
        return inspect_archive(db, user_id, data)
    except ArchiveConflictError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "vault_busy",
                "message": "The local vault is busy. Try verification again.",
            },
        ) from exc
    except ArchiveError as exc:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail={
                "code": "archive_invalid",
                "message": "Backup verification failed.",
            },
        ) from exc


@router.delete("/erase", response_model=dict[str, int])
@limiter.limit("3/hour")
async def erase_local_career_data(
    request: Request,
    response: Response,
    confirmation: str | None = Header(default=None, alias="X-Confirm-Erase"),
    authority: AuthFamilyAuthority = Depends(get_vault_maintenance_authority),
    db: Session = Depends(get_db),
) -> dict[str, int] | JSONResponse:
    if confirmation != ERASE_CONFIRMATION:
        raise HTTPException(
            status_code=409,
            detail=f"Set X-Confirm-Erase to {ERASE_CONFIRMATION}",
        )
    require_vault_maintenance_operation(authority, VAULT_STATE_ERASURE_PENDING)
    try:
        async with vault_activity_gate.maintenance():
            begin_vault_maintenance(
                db,
                authority.user_id,
                authority.session_id,
                VAULT_STATE_ERASURE_PENDING,
                token_purpose=authority.token_purpose,
            )
            await quiesce_user_vault_activity(db, authority.user_id)
            async with vault_activity_gate.writer():
                await quiesce_managed_runtime_installation()
                await quiesce_user_vault_activity(db, authority.user_id)
                result = await run_in_threadpool(
                    partial(
                        delete_complete_vault,
                        db,
                        authority.user_id,
                        erase_managed_runtime=True,
                        erase_auth_sessions=True,
                        erasure_session_id=authority.session_id,
                    )
                )
    except VaultMaintenanceConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "vault_maintenance_conflict",
                "message": "Another local-data operation completed or is still pending.",
            },
        ) from exc
    except Exception as exc:
        db.rollback()
        db.expire_all()
        user = db.get(User, authority.user_id)
        if user is not None and user.vault_lifecycle_state == VAULT_STATE_ERASURE_PENDING:
            try:
                retry_token = issue_maintenance_access(db, user).access_token
            except Exception:
                db.rollback()
                retry_token = None
            detail = {
                "code": "erasure_cleanup_pending",
                "message": "Local data cleanup is incomplete. Retry erasure.",
                "session_state": VAULT_STATE_ERASURE_PENDING,
                "reauth_required": retry_token is None,
            }
            if retry_token is not None:
                detail["maintenance_access_token"] = retry_token
            failure = JSONResponse(
                status_code=500,
                content={"detail": detail},
            )
            clear_refresh_cookies(failure)
            return failure
        if isinstance(exc, VaultLockTimeout):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail="Local data erasure failed") from exc
    clear_refresh_cookies(response)
    return result
