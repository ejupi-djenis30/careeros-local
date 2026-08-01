from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
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
    VaultDeletionError,
    VaultMaintenanceConflictError,
    begin_vault_maintenance,
    clear_vault_maintenance,
    delete_complete_vault,
)
from backend.career.maintenance import quiesce_user_vault_activity
from backend.career.repository import CareerProfileConflictError
from backend.career.schemas import (
    CareerProfileResponse,
    CareerProfileSummary,
    CareerProfileWrite,
    SourceDocumentResponse,
)
from backend.career.service import CareerProfileService
from backend.career.sources import (
    SourceImportError,
    persist_prepared_source_document,
    prepare_source_document,
)
from backend.core.config import settings
from backend.db.base import get_db
from backend.desktop.lifecycle import VaultLockTimeout
from backend.models import User
from backend.models.user import VAULT_STATE_RESET_PENDING
from backend.services.auth_sessions import issue_maintenance_access
from backend.storage.atomic import StorageWriteError

router = APIRouter()
DELETE_CONFIRMATION = "DELETE-MY-CAREER-VAULT"


@router.get("", response_model=CareerProfileResponse)
def get_profile(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
) -> CareerProfileResponse:
    profile = CareerProfileService(db).get(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Career profile not initialized")
    return profile


@router.get("/summary", response_model=CareerProfileSummary)
def get_profile_summary(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
) -> CareerProfileSummary:
    summary = CareerProfileService(db).summary(user_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Career profile not initialized")
    return summary


@router.put("", response_model=CareerProfileResponse)
@limiter.limit("20/minute")
def put_profile(
    request: Request,
    data: CareerProfileWrite,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> CareerProfileResponse:
    try:
        return CareerProfileService(db).save(user_id, data)
    except CareerProfileConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StorageWriteError as exc:
        db.rollback()
        raise HTTPException(status_code=507, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("", status_code=204)
@limiter.limit("3/hour")
async def delete_profile(
    request: Request,
    confirmation: str | None = Header(default=None, alias="X-Confirm-Delete"),
    authority: AuthFamilyAuthority = Depends(get_vault_maintenance_authority),
    db: Session = Depends(get_db),
) -> Response:
    if confirmation != DELETE_CONFIRMATION:
        raise HTTPException(
            status_code=409,
            detail=f"Set X-Confirm-Delete to {DELETE_CONFIRMATION}",
        )
    require_vault_maintenance_operation(authority, VAULT_STATE_RESET_PENDING)
    transitioned_from_ready = False
    try:
        async with vault_activity_gate.maintenance():
            try:
                transitioned_from_ready = begin_vault_maintenance(
                    db,
                    authority.user_id,
                    authority.session_id,
                    VAULT_STATE_RESET_PENDING,
                    token_purpose=authority.token_purpose,
                )
                await quiesce_user_vault_activity(db, authority.user_id)
                async with vault_activity_gate.writer():
                    await quiesce_user_vault_activity(db, authority.user_id)
                    await run_in_threadpool(
                        delete_complete_vault,
                        db,
                        authority.user_id,
                        maintenance_session_id=authority.session_id,
                    )
            except VaultLockTimeout:
                if transitioned_from_ready:
                    clear_vault_maintenance(
                        db,
                        authority.user_id,
                        VAULT_STATE_RESET_PENDING,
                    )
                raise
    except VaultMaintenanceConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "vault_maintenance_conflict",
                "message": "Another local-data operation completed or is still pending.",
            },
        ) from exc
    except VaultLockTimeout as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        db.expire_all()
        user = db.get(User, authority.user_id)
        if user is not None and user.vault_lifecycle_state == VAULT_STATE_RESET_PENDING:
            try:
                retry_token = issue_maintenance_access(db, user).access_token
            except Exception:
                db.rollback()
                retry_token = None
            detail = {
                "code": "reset_cleanup_pending",
                "message": "Local vault cleanup is incomplete. Retry reset.",
                "session_state": VAULT_STATE_RESET_PENDING,
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
        if isinstance(exc, VaultDeletionError):
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail="Local vault reset failed") from exc
    return Response(status_code=204)


@router.post("/sources", response_model=SourceDocumentResponse, status_code=201)
@limiter.limit("10/minute")
async def upload_source(
    request: Request,
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SourceDocumentResponse:
    data = await file.read(settings.MAX_UPLOAD_FILE_SIZE + 1)
    try:
        prepared = await run_in_threadpool(
            prepare_source_document,
            filename=file.filename or "source",
            media_type=file.content_type or "application/octet-stream",
            data=data,
        )
        return persist_prepared_source_document(db, user_id=user_id, prepared=prepared)
    except SourceImportError as exc:
        db.rollback()
        if "size limit" in str(exc):
            status_code = 413
        elif "Supported source formats" in str(exc):
            status_code = 415
        else:
            status_code = 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except StorageWriteError as exc:
        db.rollback()
        raise HTTPException(status_code=507, detail=str(exc)) from exc
