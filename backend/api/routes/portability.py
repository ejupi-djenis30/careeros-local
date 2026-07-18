import hashlib
from datetime import datetime, timezone
from io import BytesIO

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_id, limiter
from backend.career.deletion import VaultDeletionError, delete_complete_vault
from backend.core.config import settings
from backend.db.base import get_db
from backend.desktop.lifecycle import VaultLockTimeout
from backend.portability.archive import (
    ArchiveConflictError,
    ArchiveError,
    export_archive,
)
from backend.portability.restore import restore_archive
from backend.portability.schemas import RestoreResponse
from backend.storage.atomic import StorageWriteError

router = APIRouter()
ERASE_CONFIRMATION = "ERASE-LOCAL-CAREER-DATA"


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
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> RestoreResponse:
    data = await file.read(settings.PORTABLE_ARCHIVE_MAX_BYTES + 1)
    if len(data) > settings.PORTABLE_ARCHIVE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Archive exceeds the configured size limit")
    try:
        return restore_archive(db, user_id, data)
    except ArchiveConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StorageWriteError as exc:
        db.rollback()
        raise HTTPException(status_code=507, detail=str(exc)) from exc
    except ArchiveError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/erase", response_model=dict[str, int])
@limiter.limit("3/hour")
def erase_local_career_data(
    request: Request,
    confirmation: str | None = Header(default=None, alias="X-Confirm-Erase"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    if confirmation != ERASE_CONFIRMATION:
        raise HTTPException(
            status_code=409,
            detail=f"Set X-Confirm-Erase to {ERASE_CONFIRMATION}",
        )
    try:
        return delete_complete_vault(db, user_id, erase_managed_runtime=True)
    except VaultLockTimeout as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except VaultDeletionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
