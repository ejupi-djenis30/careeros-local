"""Authenticated management and explicit import of job-provider installations."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_id, limiter
from backend.core.config import settings
from backend.db.base import get_db
from backend.providers.configuration.network_policy import UnsafeProviderDestination
from backend.providers.configuration.packs import (
    ProviderPackError,
    bundled_provider_pack,
    bundled_provider_pack_summaries,
)
from backend.providers.configuration.schemas import (
    ProviderCatalogView,
    ProviderConfigurationCreate,
    ProviderConfigurationInput,
    ProviderConfigurationUpdate,
    ProviderConfigurationView,
    ProviderImportRequest,
    ProviderImportResultView,
    ProviderPackInstallRequest,
    ProviderStateUpdate,
    ProviderTestRequest,
    ProviderTestView,
    ProviderValidationView,
)
from backend.providers.configuration.service import (
    ProviderConfigurationError,
    ProviderConfigurationService,
)
from backend.providers.configuration.tester import test_provider_configuration
from backend.providers.jobs.exceptions import ProviderError

router = APIRouter()
NO_STORE_HEADERS = {"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"}
ProviderId = Annotated[
    str,
    Path(
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    ),
]
ProviderPackId = Annotated[
    str,
    Path(min_length=3, max_length=160, pattern=r"^[a-z][a-z0-9_.-]{2,159}$"),
]


def _private(response: Response) -> None:
    for name, value in NO_STORE_HEADERS.items():
        response.headers[name] = value


def _configuration_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProviderConfigurationError):
        code = exc.code
        status_code = {
            "provider_not_found": status.HTTP_404_NOT_FOUND,
            "revision_conflict": status.HTTP_409_CONFLICT,
            "provider_key_conflict": status.HTTP_409_CONFLICT,
            "provider_limit": status.HTTP_409_CONFLICT,
            "provider_import_too_large": status.HTTP_413_CONTENT_TOO_LARGE,
        }.get(code, status.HTTP_422_UNPROCESSABLE_CONTENT)
        return HTTPException(
            status_code=status_code,
            detail={"code": code, "message": str(exc)},
            headers=NO_STORE_HEADERS,
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={
            "code": "invalid_provider_configuration",
            "message": "Provider configuration is invalid",
        },
        headers=NO_STORE_HEADERS,
    )


@router.get("", response_model=ProviderCatalogView)
def list_job_providers(
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProviderCatalogView:
    _private(response)
    try:
        packs = bundled_provider_pack_summaries()
    except ProviderPackError:
        packs = []
    return ProviderCatalogView(
        installed=ProviderConfigurationService(db).list(user_id),
        available_packs=packs,
    )


@router.post(
    "/import",
    response_model=ProviderImportResultView,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
def import_job_provider_document(
    request: Request,
    payload: ProviderImportRequest,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProviderImportResultView:
    _private(response)
    try:
        return ProviderConfigurationService(db).import_document(
            user_id,
            payload.document,
            activate=payload.activate,
        )
    except (ProviderConfigurationError, UnsafeProviderDestination, ValueError) as exc:
        raise _configuration_error(exc) from exc


@router.post(
    "/packs/{pack_id}/import",
    response_model=ProviderImportResultView,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
def import_bundled_provider_pack(
    request: Request,
    pack_id: ProviderPackId,
    payload: ProviderPackInstallRequest,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProviderImportResultView:
    _private(response)
    try:
        pack = bundled_provider_pack(pack_id)
        return ProviderConfigurationService(db).import_document(
            user_id,
            pack,
            activate=payload.activate,
        )
    except ProviderPackError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "provider_pack_not_found", "message": str(exc)},
            headers=NO_STORE_HEADERS,
        ) from exc
    except (ProviderConfigurationError, UnsafeProviderDestination, ValueError) as exc:
        raise _configuration_error(exc) from exc


@router.post("/validate", response_model=ProviderValidationView)
def validate_job_provider(
    payload: ProviderConfigurationInput,
    response: Response,
    _user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProviderValidationView:
    _private(response)
    try:
        return ProviderConfigurationService(db).validate(payload)
    except (ProviderConfigurationError, UnsafeProviderDestination, ValueError) as exc:
        raise _configuration_error(exc) from exc


@router.post("", response_model=ProviderConfigurationView, status_code=status.HTTP_201_CREATED)
def create_job_provider(
    payload: ProviderConfigurationCreate,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProviderConfigurationView:
    _private(response)
    try:
        return ProviderConfigurationService(db).create(user_id, payload)
    except (ProviderConfigurationError, UnsafeProviderDestination, ValueError) as exc:
        raise _configuration_error(exc) from exc


@router.get("/{provider_id}", response_model=ProviderConfigurationView)
def get_job_provider(
    provider_id: ProviderId,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProviderConfigurationView:
    _private(response)
    try:
        return ProviderConfigurationService(db).get(user_id, provider_id)
    except ProviderConfigurationError as exc:
        raise _configuration_error(exc) from exc


@router.put("/{provider_id}", response_model=ProviderConfigurationView)
def update_job_provider(
    provider_id: ProviderId,
    payload: ProviderConfigurationUpdate,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProviderConfigurationView:
    _private(response)
    try:
        return ProviderConfigurationService(db).update(user_id, provider_id, payload)
    except (ProviderConfigurationError, UnsafeProviderDestination, ValueError) as exc:
        raise _configuration_error(exc) from exc


@router.patch("/{provider_id}/state", response_model=ProviderConfigurationView)
def set_job_provider_state(
    provider_id: ProviderId,
    payload: ProviderStateUpdate,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProviderConfigurationView:
    _private(response)
    try:
        return ProviderConfigurationService(db).set_enabled(user_id, provider_id, payload)
    except ProviderConfigurationError as exc:
        raise _configuration_error(exc) from exc


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job_provider(
    provider_id: ProviderId,
    response: Response,
    expected_revision: int = Query(ge=1),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    _private(response)
    try:
        ProviderConfigurationService(db).delete(
            user_id, provider_id, expected_revision=expected_revision
        )
    except ProviderConfigurationError as exc:
        raise _configuration_error(exc) from exc


@router.post("/{provider_id}/test", response_model=ProviderTestView)
@limiter.limit("5/minute")
async def test_job_provider(
    request: Request,
    provider_id: ProviderId,
    payload: ProviderTestRequest,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProviderTestView:
    _private(response)
    if settings.OFFLINE_MODE is True:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "offline_mode", "message": "Provider network access is disabled"},
            headers=NO_STORE_HEADERS,
        )
    try:
        return await test_provider_configuration(
            db,
            user_id=user_id,
            configuration_id=provider_id,
            request=payload,
        )
    except ProviderConfigurationError as exc:
        raise _configuration_error(exc) from exc
    except (ProviderError, UnsafeProviderDestination):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "provider_test_failed", "message": "The provider test failed safely"},
            headers=NO_STORE_HEADERS,
        ) from None
