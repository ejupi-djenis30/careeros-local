from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_id, limiter
from backend.career.deletion import VaultDeletionError, delete_complete_vault
from backend.career.repository import CareerProfileConflictError
from backend.career.schemas import (
    CareerProfileResponse,
    CareerProfileSummary,
    CareerProfileWrite,
    SourceDocumentResponse,
)
from backend.career.service import CareerProfileService
from backend.career.sources import SourceImportError, import_source_document
from backend.core.config import settings
from backend.db.base import get_db
from backend.desktop.lifecycle import VaultLockTimeout
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
def delete_profile(
    request: Request,
    confirmation: str | None = Header(default=None, alias="X-Confirm-Delete"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    if confirmation != DELETE_CONFIRMATION:
        raise HTTPException(
            status_code=409,
            detail=f"Set X-Confirm-Delete to {DELETE_CONFIRMATION}",
        )
    try:
        delete_complete_vault(db, user_id)
    except VaultLockTimeout as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except VaultDeletionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
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
        return import_source_document(
            db,
            user_id=user_id,
            filename=file.filename or "source",
            media_type=file.content_type or "application/octet-stream",
            data=data,
        )
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
