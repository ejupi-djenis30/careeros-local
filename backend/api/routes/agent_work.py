"""Owner queue, creation and review routes for agent work."""

from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from backend.agent_work.acceptance import accept_work_proposal
from backend.agent_work.http_boundary import PrivateAgentRoute
from backend.agent_work.schemas import (
    UUID_PATTERN,
    AgentWorkAcceptRequest,
    AgentWorkCASRequest,
    AgentWorkCreateRequest,
    AgentWorkDetailView,
    AgentWorkListView,
    AgentWorkView,
    WorkState,
)
from backend.agent_work.service import AgentWorkError, AgentWorkService
from backend.api.deps import get_current_user_id
from backend.db.base import get_db

desktop_session_header = APIKeyHeader(
    name="X-CareerOS-Session",
    scheme_name="desktopSession",
    auto_error=False,
)


router = APIRouter(dependencies=[Security(desktop_session_header)], route_class=PrivateAgentRoute)
RequestId = Annotated[str, Path(pattern=UUID_PATTERN)]

NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}


def _mark_private(response: Response) -> None:
    for name, value in NO_STORE_HEADERS.items():
        response.headers[name] = value


def _owner_error(exc: AgentWorkError) -> HTTPException:
    status_code = (
        status.HTTP_404_NOT_FOUND
        if exc.code == "work_not_found"
        else (
            status.HTTP_403_FORBIDDEN
            if exc.code in ("scope_denied", "grant_revoked")
            else (
                status.HTTP_409_CONFLICT
                if exc.code in ("revision_conflict", "result_conflict")
                else (
                    status.HTTP_503_SERVICE_UNAVAILABLE
                    if exc.code in ("vault_unavailable", "desktop_unavailable")
                    else status.HTTP_422_UNPROCESSABLE_CONTENT
                )
            )
        )
    )
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": str(exc)},
        headers=NO_STORE_HEADERS,
    )


@router.get("", response_model=AgentWorkListView)
def list_agent_work(
    response: Response,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=50),
    state: WorkState | None = Query(None),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AgentWorkListView:
    _mark_private(response)
    service = AgentWorkService(db)
    items, total = service.list_work_requests(
        user_id,
        offset=offset,
        limit=limit,
        state=state,
    )
    return AgentWorkListView(
        items=items,
        offset=offset,
        limit=limit,
        returned_count=len(items),
    )


@router.post("", response_model=AgentWorkView, status_code=status.HTTP_201_CREATED)
def create_agent_work(
    payload: AgentWorkCreateRequest,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AgentWorkView:
    _mark_private(response)
    try:
        service = AgentWorkService(db)
        return service.create_work_request(user_id, payload)
    except AgentWorkError as exc:
        raise _owner_error(exc) from exc


@router.get("/{request_id}", response_model=AgentWorkDetailView)
def get_agent_work_detail(
    request_id: RequestId,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AgentWorkDetailView:
    _mark_private(response)
    try:
        service = AgentWorkService(db)
        return service.get_work_request(user_id, request_id)
    except AgentWorkError as exc:
        raise _owner_error(exc) from exc


@router.post("/{request_id}/cancel", response_model=AgentWorkView)
def cancel_agent_work(
    request_id: RequestId,
    payload: AgentWorkCASRequest,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AgentWorkView:
    _mark_private(response)
    try:
        service = AgentWorkService(db)
        return service.cancel_work_request(
            user_id,
            request_id,
            expected_revision=payload.expected_revision,
        )
    except AgentWorkError as exc:
        raise _owner_error(exc) from exc


@router.post("/{request_id}/reject", response_model=AgentWorkView)
def reject_agent_work(
    request_id: RequestId,
    payload: AgentWorkCASRequest,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AgentWorkView:
    _mark_private(response)
    try:
        service = AgentWorkService(db)
        return service.reject_work_request(
            user_id,
            request_id,
            expected_revision=payload.expected_revision,
        )
    except AgentWorkError as exc:
        raise _owner_error(exc) from exc


@router.post("/{request_id}/accept")
def accept_agent_work(
    request_id: RequestId,
    payload: AgentWorkAcceptRequest,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _mark_private(response)
    try:
        return cast(
            dict[str, Any],
            accept_work_proposal(
                db,
                user_id=user_id,
                request_id=request_id,
                accept_in=payload,
            ),
        )
    except AgentWorkError as exc:
        raise _owner_error(exc) from exc
