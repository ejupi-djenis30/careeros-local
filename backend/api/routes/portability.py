import hashlib
from datetime import datetime, timezone
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_id, limiter
from backend.core.config import settings
from backend.db.base import get_db
from backend.portability.archive import (
    ArchiveConflictError,
    ArchiveError,
    export_archive,
    restore_archive,
)
from backend.portability.schemas import RestoreResponse

router = APIRouter()


@router.get("/export")
@limiter.limit("5/hour")
def export_portable_archive(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        data = export_archive(db, user_id)
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
    except ArchiveError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
