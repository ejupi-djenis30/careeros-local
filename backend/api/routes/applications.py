from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_id, limiter
from backend.applications.schemas import (
    ApplicationCreate,
    ApplicationEventCreate,
    ApplicationPreparationUpdate,
    ApplicationReadinessReport,
    ApplicationResponse,
    ApplicationSummary,
)
from backend.applications.service import (
    ApplicationConflictError,
    ApplicationNotFoundError,
    ApplicationService,
    ApplicationValidationError,
)
from backend.db.base import get_db

router = APIRouter()


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ApplicationNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ApplicationConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.get("", response_model=list[ApplicationSummary])
def list_applications(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
) -> list[ApplicationSummary]:
    return ApplicationService(db).list(user_id, offset=offset, limit=limit)


@router.post("", response_model=ApplicationResponse, status_code=201)
@limiter.limit("20/minute")
def create_application(
    request: Request,
    data: ApplicationCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApplicationResponse:
    try:
        return ApplicationService(db).create(user_id, data)
    except (ApplicationValidationError, ApplicationConflictError) as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.get("/{application_id}", response_model=ApplicationResponse)
def get_application(
    application_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApplicationResponse:
    try:
        return ApplicationService(db).get(user_id, application_id)
    except ApplicationNotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/{application_id}/readiness", response_model=ApplicationReadinessReport)
def get_application_readiness(
    application_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApplicationReadinessReport:
    try:
        return ApplicationService(db).readiness(user_id, application_id)
    except ApplicationNotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/{application_id}/readiness/export")
def export_application_readiness(
    application_id: str,
    export_format: Literal["json", "markdown"] = Query(default="json", alias="format"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    try:
        exported = ApplicationService(db).export_readiness(
            user_id, application_id, export_format
        )
    except ApplicationNotFoundError as exc:
        raise _http_error(exc) from exc
    return Response(
        content=exported.data,
        media_type=exported.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="{exported.filename}"',
            "X-Content-SHA256": exported.sha256,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch("/{application_id}/preparation", response_model=ApplicationResponse)
@limiter.limit("20/minute")
def update_application_preparation(
    request: Request,
    application_id: str,
    data: ApplicationPreparationUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApplicationResponse:
    try:
        return ApplicationService(db).update_preparation(user_id, application_id, data)
    except (ApplicationNotFoundError, ApplicationConflictError, ApplicationValidationError) as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/{application_id}/events", response_model=ApplicationResponse, status_code=201)
@limiter.limit("40/minute")
def append_application_event(
    request: Request,
    application_id: str,
    data: ApplicationEventCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApplicationResponse:
    try:
        return ApplicationService(db).append_event(user_id, application_id, data)
    except (ApplicationNotFoundError, ApplicationConflictError, ApplicationValidationError) as exc:
        db.rollback()
        raise _http_error(exc) from exc
