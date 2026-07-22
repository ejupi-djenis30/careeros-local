import hashlib
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_id, limiter
from backend.applications.schemas import (
    ApplicationCreate,
    ApplicationDossierCreate,
    ApplicationEventCreate,
    ApplicationPreparationUpdate,
    ApplicationReadinessReport,
    ApplicationResponse,
    ApplicationSummary,
    ApplicationTaskCreate,
    ApplicationTaskUpdate,
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
    application_id: UUID,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApplicationResponse:
    try:
        return ApplicationService(db).get(user_id, str(application_id))
    except ApplicationNotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/{application_id}/readiness", response_model=ApplicationReadinessReport)
def get_application_readiness(
    application_id: UUID,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApplicationReadinessReport:
    try:
        return ApplicationService(db).readiness(user_id, str(application_id))
    except ApplicationNotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/{application_id}/readiness/export")
def export_application_readiness(
    application_id: UUID,
    export_format: Literal["json", "markdown"] = Query(default="json", alias="format"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    try:
        exported = ApplicationService(db).export_readiness(
            user_id, str(application_id), export_format
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
    application_id: UUID,
    data: ApplicationPreparationUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApplicationResponse:
    try:
        return ApplicationService(db).update_preparation(user_id, str(application_id), data)
    except (ApplicationNotFoundError, ApplicationConflictError, ApplicationValidationError) as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/{application_id}/events", response_model=ApplicationResponse, status_code=201)
@limiter.limit("40/minute")
def append_application_event(
    request: Request,
    application_id: UUID,
    data: ApplicationEventCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApplicationResponse:
    try:
        return ApplicationService(db).append_event(user_id, str(application_id), data)
    except (ApplicationNotFoundError, ApplicationConflictError, ApplicationValidationError) as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/{application_id}/tasks", response_model=ApplicationResponse, status_code=201)
@limiter.limit("40/minute")
def create_application_task(
    request: Request,
    application_id: UUID,
    data: ApplicationTaskCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApplicationResponse:
    try:
        return ApplicationService(db).create_task(user_id, str(application_id), data)
    except (ApplicationNotFoundError, ApplicationConflictError, ApplicationValidationError) as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.patch(
    "/{application_id}/tasks/{task_id}", response_model=ApplicationResponse
)
@limiter.limit("40/minute")
def update_application_task(
    request: Request,
    application_id: UUID,
    task_id: UUID,
    data: ApplicationTaskUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApplicationResponse:
    try:
        return ApplicationService(db).update_task(
            user_id, str(application_id), str(task_id), data
        )
    except (ApplicationNotFoundError, ApplicationConflictError, ApplicationValidationError) as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.get("/{application_id}/tasks/calendar.ics")
def export_application_task_calendar(
    application_id: UUID,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    try:
        data = ApplicationService(db).task_calendar(user_id, str(application_id))
    except ApplicationNotFoundError as exc:
        raise _http_error(exc) from exc
    return Response(
        content=data,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": (
                f'attachment; filename="careeros-application-{application_id}-tasks.ics"'
            ),
            "X-Content-SHA256": hashlib.sha256(data).hexdigest(),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{application_id}/dossiers", response_model=ApplicationResponse, status_code=201)
@limiter.limit("10/minute")
def publish_application_dossier(
    request: Request,
    application_id: UUID,
    data: ApplicationDossierCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ApplicationResponse:
    try:
        return ApplicationService(db).publish_dossier(user_id, str(application_id), data)
    except (ApplicationNotFoundError, ApplicationConflictError, ApplicationValidationError) as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.get("/{application_id}/dossiers/{dossier_id}/download")
def download_application_dossier(
    application_id: UUID,
    dossier_id: UUID,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    try:
        bundle = ApplicationService(db).dossier_bundle(
            user_id, str(application_id), str(dossier_id)
        )
    except (ApplicationNotFoundError, ApplicationValidationError) as exc:
        raise _http_error(exc) from exc
    return Response(
        content=bundle.data,
        media_type="application/zip",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": (
                f'attachment; filename="careeros-dossier-{application_id}-{dossier_id}.zip"'
            ),
            "X-Content-SHA256": bundle.sha256,
            "X-Dossier-Manifest-SHA256": bundle.manifest_sha256,
            "X-Content-Type-Options": "nosniff",
        },
    )
