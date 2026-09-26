"""Authenticated, thin HTTP routes for legacy campaign workspaces."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_id
from backend.api.middleware import PRIVATE_NO_STORE_HEADERS
from backend.campaigns.api_service import (
    CampaignApiIntegrityError,
    CampaignApiNotFound,
    application_context,
    campaign_detail,
    download_artifact,
    list_campaigns,
)
from backend.campaigns.archive_policy import MAX_COMPRESSED_BYTES, ArchivePolicyError
from backend.campaigns.parser import parse_campaign_workspace
from backend.campaigns.preview import preview_from_parsed_campaign
from backend.campaigns.service import import_campaign
from backend.campaigns.service_helpers import CampaignImportError
from backend.campaigns.xlsx_security import XlsxReadError, XlsxSecurityError
from backend.career.models import CandidateProfile
from backend.db.base import get_db

router = APIRouter()
application_context_router = APIRouter()


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "not_found", "message": "Resource not found"})


def _safe_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _read_archive(file: UploadFile) -> bytes:
    try:
        data = await file.read(MAX_COMPRESSED_BYTES + 1)
    except Exception:
        raise _safe_error(400, "invalid_archive", "Campaign archive could not be read")
    if len(data) > MAX_COMPRESSED_BYTES:
        raise _safe_error(413, "archive_too_large", "Campaign archive exceeds the configured limit")
    return data


def _preview_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ArchivePolicyError) or isinstance(exc, XlsxSecurityError):
        return _safe_error(400, "invalid_archive", "Campaign archive validation failed")
    if isinstance(exc, XlsxReadError):
        return _safe_error(422, "invalid_workbook", "Campaign workbook could not be interpreted")
    return _safe_error(500, "preview_failed", "Campaign preview failed")


@router.post("/preview")
async def preview_campaign(
    archive: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    data = await _read_archive(archive)
    try:
        parsed = parse_campaign_workspace(data, archive.filename or "campaign.zip")
        has_profile = db.query(CandidateProfile.id).filter(CandidateProfile.user_id == user_id).first() is not None
        body = preview_from_parsed_campaign(parsed, user_has_profile=has_profile).model_dump(mode="json")
    except Exception as exc:
        raise _preview_error(exc) from None
    return JSONResponse(body, headers=PRIVATE_NO_STORE_HEADERS)


@router.post("/import")
async def import_campaign_route(
    archive: UploadFile = File(...),
    expected_fingerprint: str = Form(...),
    name: str | None = Form(default=None),
    profile_display_name: str | None = Form(default=None),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JSONResponse:
    data = await _read_archive(archive)
    try:
        result = import_campaign(
            db,
            user_id=user_id,
            archive_bytes=data,
            expected_fingerprint=expected_fingerprint,
            imported_at=datetime.now(timezone.utc),
            campaign_name=name,
            profile_display_name=profile_display_name,
        )
    except CampaignImportError as exc:
        status = exc.status_code if exc.status_code in {400, 409, 422} else 500
        code = "conflict" if status == 409 else "invalid_archive" if status == 400 else "import_failed"
        message = (
            "Campaign import conflicts with existing state"
            if status == 409
            else "Campaign archive validation failed"
            if status == 400
            else "Campaign import request is invalid"
            if status == 422
            else "Campaign import failed"
        )
        raise _safe_error(status, code, message) from None
    except Exception:
        raise _safe_error(500, "import_failed", "Campaign import failed") from None
    return JSONResponse(
        result.model_dump(mode="json"),
        status_code=201 if result.created else 200,
        headers=PRIVATE_NO_STORE_HEADERS,
    )


@router.get("")
def campaigns_list(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return list_campaigns(db, user_id)


@router.get("/{campaign_id}")
def campaign_detail_route(
    campaign_id: str,
    query: str | None = Query(default=None, max_length=200),
    stage: str | None = None,
    priority: str | None = None,
    review_decision: str | None = None,
    limit: int = Query(default=200, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    valid_stages = {
        "saved",
        "preparing",
        "applied",
        "screening",
        "interview",
        "offer",
        "accepted",
        "rejected",
        "withdrawn",
        "archived",
    }
    valid_priorities = {"Urgent", "High", "Medium", "Low"}
    if stage is not None and stage not in valid_stages:
        raise _safe_error(422, "invalid_filter", "Campaign filter is invalid")
    if priority is not None and priority not in valid_priorities:
        raise _safe_error(422, "invalid_filter", "Campaign filter is invalid")
    if review_decision is not None and review_decision not in {
        "none", "hold", "excluded", "cleared"
    }:
        raise _safe_error(422, "invalid_filter", "Campaign filter is invalid")
    try:
        return campaign_detail(
            db,
            user_id,
            campaign_id,
            query=query,
            stage=stage,
            priority=priority,
            review_decision=review_decision,
            limit=limit,
            offset=offset,
        )
    except CampaignApiNotFound:
        raise _not_found() from None


@application_context_router.get("/{application_id}/campaign-context")
def campaign_context_route(
    application_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return application_context(db, user_id, application_id)
    except CampaignApiNotFound:
        raise _not_found() from None


@router.get("/{campaign_id}/artifacts/{artifact_id}/download")
def campaign_artifact_download(
    campaign_id: str,
    artifact_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    try:
        content, media_type, digest, disposition = download_artifact(db, user_id, campaign_id, artifact_id)
    except CampaignApiNotFound:
        raise _not_found() from None
    except CampaignApiIntegrityError:
        raise _safe_error(409, "asset_integrity", "Campaign artifact failed integrity verification") from None
    return Response(
        content=content,
        media_type=media_type,
        headers={
            **PRIVATE_NO_STORE_HEADERS,
            "Content-Disposition": disposition,
            "Content-Length": str(len(content)),
            "X-Content-SHA256": digest,
            "X-Content-Type-Options": "nosniff",
        },
    )
