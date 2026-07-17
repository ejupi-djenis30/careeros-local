from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_id, limiter
from backend.core.config import settings
from backend.db.base import get_db
from backend.resumes.photos import load_profile_photo, store_profile_photo
from backend.resumes.renderers.photo import PhotoValidationError
from backend.resumes.schemas import (
    PhotoAssetResponse,
    ResumeClaimPromote,
    ResumeDraftCreate,
    ResumeDraftResponse,
    ResumeDraftUpdate,
    ResumeDuplicate,
    ResumeGenerate,
    ResumeSummary,
    ResumeSync,
    ResumeSyncResponse,
    ResumeVersionResponse,
)
from backend.resumes.service import (
    ResumeConflictError,
    ResumeNotFoundError,
    ResumeService,
    ResumeValidationError,
)

router = APIRouter()
artifact_router = APIRouter()
photo_router = APIRouter()


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ResumeNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ResumeConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.get("", response_model=list[ResumeSummary])
def list_resumes(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
) -> list[ResumeSummary]:
    return ResumeService(db).list_resumes(user_id)


@router.post("", response_model=ResumeDraftResponse, status_code=201)
@limiter.limit("20/minute")
def create_resume(
    request: Request,
    data: ResumeDraftCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ResumeDraftResponse:
    try:
        return ResumeService(db).create(user_id, data)
    except (ResumeValidationError, ResumeConflictError, ResumeNotFoundError) as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/generate", response_model=ResumeDraftResponse, status_code=201)
@limiter.limit("20/minute")
def generate_resume(
    request: Request,
    data: ResumeGenerate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ResumeDraftResponse:
    try:
        return ResumeService(db).generate(user_id, data)
    except (ResumeValidationError, ResumeConflictError, ResumeNotFoundError, ValueError) as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.get("/{resume_id}", response_model=ResumeDraftResponse)
def get_resume(
    resume_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ResumeDraftResponse:
    try:
        return ResumeService(db).get(user_id, resume_id)
    except ResumeNotFoundError as exc:
        raise _http_error(exc) from exc


@router.put("/{resume_id}", response_model=ResumeDraftResponse)
@limiter.limit("20/minute")
def update_resume(
    request: Request,
    resume_id: str,
    data: ResumeDraftUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ResumeDraftResponse:
    try:
        return ResumeService(db).update(user_id, resume_id, data)
    except (ResumeValidationError, ResumeConflictError, ResumeNotFoundError) as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/{resume_id}/duplicate", response_model=ResumeDraftResponse, status_code=201)
@limiter.limit("20/minute")
def duplicate_resume(
    request: Request,
    resume_id: str,
    data: ResumeDuplicate | None = None,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ResumeDraftResponse:
    try:
        return ResumeService(db).duplicate(user_id, resume_id, data or ResumeDuplicate())
    except (ResumeValidationError, ResumeConflictError, ResumeNotFoundError) as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/{resume_id}/claims/promote", response_model=ResumeDraftResponse)
@limiter.limit("20/minute")
def promote_resume_claim(
    request: Request,
    resume_id: str,
    data: ResumeClaimPromote,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ResumeDraftResponse:
    try:
        return ResumeService(db).promote_claim(user_id, resume_id, data)
    except (ResumeValidationError, ResumeConflictError, ResumeNotFoundError, ValueError) as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/{resume_id}/sync", response_model=ResumeSyncResponse)
@limiter.limit("20/minute")
def synchronize_resume(
    request: Request,
    resume_id: str,
    data: ResumeSync,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ResumeSyncResponse:
    try:
        return ResumeService(db).synchronize(user_id, resume_id, data)
    except (ResumeValidationError, ResumeConflictError, ResumeNotFoundError, ValueError) as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/{resume_id}/publish", response_model=ResumeVersionResponse, status_code=201)
@limiter.limit("10/minute")
def publish_resume(
    request: Request,
    resume_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ResumeVersionResponse:
    try:
        return ResumeService(db).publish(user_id, resume_id)
    except (ResumeValidationError, ResumeConflictError, ResumeNotFoundError, ValueError) as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.delete("/{resume_id}", status_code=204)
def delete_resume(
    resume_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    try:
        ResumeService(db).delete(user_id, resume_id)
    except ResumeNotFoundError as exc:
        raise _http_error(exc) from exc
    return Response(status_code=204)


@artifact_router.get("/{artifact_id}")
def download_artifact(
    artifact_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        artifact, data, filename = ResumeService(db).artifact(user_id, artifact_id)
    except (ResumeValidationError, ResumeNotFoundError) as exc:
        raise _http_error(exc) from exc
    return StreamingResponse(
        BytesIO(data),
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-SHA256": artifact.sha256,
            "X-Content-Type-Options": "nosniff",
        },
    )


@photo_router.post("/photo", response_model=PhotoAssetResponse, status_code=201)
@limiter.limit("10/minute")
async def upload_profile_photo(
    request: Request,
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> PhotoAssetResponse:
    data = await file.read(settings.MAX_UPLOAD_FILE_SIZE + 1)
    try:
        return store_profile_photo(
            db,
            user_id=user_id,
            filename=file.filename or "photo",
            data=data,
        )
    except PhotoValidationError as exc:
        db.rollback()
        status_code = 413 if "size limit" in str(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@photo_router.get("/photo/{asset_id}")
def get_profile_photo(
    asset_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        asset, data = load_profile_photo(db, user_id=user_id, asset_id=asset_id)
    except (ResumeValidationError, ResumeNotFoundError) as exc:
        raise _http_error(exc) from exc
    return StreamingResponse(
        BytesIO(data),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": 'inline; filename="profile-photo.jpg"',
            "X-Content-SHA256": asset.sha256,
            "X-Content-Type-Options": "nosniff",
        },
    )
