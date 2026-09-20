"""Grant-authenticated fixed bridge routes for external MCP clients."""

from __future__ import annotations

import ipaddress
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy.orm import Session

from backend.agent_work.guards import require_work_live
from backend.agent_work.http_boundary import PrivateAgentRoute
from backend.agent_work.models import AgentWorkRequest
from backend.agent_work.proposal_service import ProposalService
from backend.agent_work.schemas import (
    UUID_PATTERN,
    AgentBridgeListView,
    AgentBridgeStatusView,
    AgentWorkMetadataView,
    ProposalReceiptView,
    ProposalSubmissionRequest,
    ResumeTemplateView,
    WorkContextPayload,
)
from backend.agent_work.service import AgentWorkError, AgentWorkService
from backend.automation.grants import (
    AutomationGrantError,
    AutomationPrincipal,
    authenticate_grant,
)
from backend.career.activity import vault_activity_gate
from backend.db.base import get_db
from backend.resumes.templates import list_template_presets

router = APIRouter(route_class=PrivateAgentRoute)
RequestId = Annotated[str, Path(pattern=UUID_PATTERN)]

NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}


def _mark_private(response: Response) -> None:
    for name, value in NO_STORE_HEADERS.items():
        response.headers[name] = value


async def get_bridge_principal(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    db: Session = Depends(get_db),
) -> AsyncIterator[AutomationPrincipal]:
    try:
        peer_local = (
            request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
        )
        host = urlsplit("http://" + request.headers.get("host", "")).hostname
        host_local = host is not None and ipaddress.ip_address(host).is_loopback
    except ValueError:
        peer_local = host_local = False
    if not peer_local or not host_local or "origin" in request.headers:
        raise HTTPException(
            status_code=403,
            detail={"code": "scope_denied", "message": "Bridge transport authorization failed"},
            headers=NO_STORE_HEADERS,
        )
    if len(request.headers.getlist("authorization")) != 1:
        authorization = None
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "grant_required", "message": "Bearer grant token is required"},
            headers=NO_STORE_HEADERS,
        )
    token = authorization[7:].strip()
    async with vault_activity_gate.reader():
        try:
            principal = authenticate_grant(db, token)
        except AutomationGrantError as exc:
            status_code = (
                status.HTTP_403_FORBIDDEN
                if exc.code in ("revoked_grant", "vault_maintenance_pending")
                else status.HTTP_401_UNAUTHORIZED
            )
            raise HTTPException(
                status_code=status_code,
                detail={
                    "code": {
                        "invalid_grant": "grant_required",
                        "revoked_grant": "grant_revoked",
                        "expired_grant": "grant_expired",
                        "vault_maintenance_pending": "vault_unavailable",
                    }.get(exc.code, "grant_required"),
                    "message": "The automation grant is unavailable",
                },
                headers=NO_STORE_HEADERS,
            ) from exc
        yield principal


def require_context_read(
    principal: AutomationPrincipal = Depends(get_bridge_principal),
) -> AutomationPrincipal:
    if not principal.allows("context:read"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "scope_denied", "message": "Grant lacks 'context:read' scope"},
            headers=NO_STORE_HEADERS,
        )
    return principal


def require_proposals_write(
    principal: AutomationPrincipal = Depends(get_bridge_principal),
) -> AutomationPrincipal:
    if not principal.allows("proposals:write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "scope_denied", "message": "Grant lacks 'proposals:write' scope"},
            headers=NO_STORE_HEADERS,
        )
    return principal


def _bridge_error(exc: AgentWorkError) -> HTTPException:
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


@router.get("/status", response_model=AgentBridgeStatusView)
def get_agent_status(
    response: Response,
    principal: AutomationPrincipal = Depends(get_bridge_principal),
    db: Session = Depends(get_db),
) -> AgentBridgeStatusView:
    _mark_private(response)
    queued_count = (
        db.query(AgentWorkRequest)
        .filter(
            AgentWorkRequest.user_id == principal.user_id,
            AgentWorkRequest.bound_grant_id == principal.grant_id,
            AgentWorkRequest.state == "queued",
            AgentWorkRequest.expires_at > datetime.now(UTC),
        )
        .count()
    )
    returned_count = (
        db.query(AgentWorkRequest)
        .filter(
            AgentWorkRequest.user_id == principal.user_id,
            AgentWorkRequest.bound_grant_id == principal.grant_id,
            AgentWorkRequest.state == "returned",
            AgentWorkRequest.expires_at > datetime.now(UTC),
        )
        .count()
    )
    return AgentBridgeStatusView(
        schema_version="1.0",
        contract_version=1,
        granted_scopes=sorted(list(principal.scopes)),
        queue_counts={"queued": queued_count, "returned": returned_count},
    )


@router.get("/work-requests", response_model=AgentBridgeListView)
def list_bridge_work_requests(
    response: Response,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=50),
    principal: AutomationPrincipal = Depends(get_bridge_principal),
    db: Session = Depends(get_db),
) -> AgentBridgeListView:
    _mark_private(response)
    service = AgentWorkService(db)
    items, total = service.list_work_requests(
        principal.user_id,
        offset=offset,
        limit=limit,
        grant_id=principal.grant_id,
    )
    return AgentBridgeListView(
        items=[
            AgentWorkMetadataView.model_validate(item.model_dump(), extra="ignore")
            for item in items
        ],
        offset=offset,
        limit=limit,
        returned_count=len(items),
    )


@router.get("/work-requests/{request_id}/context", response_model=WorkContextPayload)
def get_bridge_work_context(
    request_id: RequestId,
    response: Response,
    principal: AutomationPrincipal = Depends(require_context_read),
    db: Session = Depends(get_db),
) -> WorkContextPayload:
    _mark_private(response)
    req = (
        db.query(AgentWorkRequest)
        .filter(
            AgentWorkRequest.id == request_id,
            AgentWorkRequest.user_id == principal.user_id,
            AgentWorkRequest.bound_grant_id == principal.grant_id,
        )
        .first()
    )
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "work_not_found", "message": "Work request not found"},
            headers=NO_STORE_HEADERS,
        )
    try:
        require_work_live(req)
    except AgentWorkError as exc:
        raise _bridge_error(exc) from exc
    if req.state not in {"queued", "returned"}:
        raise _bridge_error(
            AgentWorkError("revision_conflict", "The request no longer exposes context")
        )
    return WorkContextPayload.model_validate(req.context_snapshot)


@router.post("/work-requests/{request_id}/result", response_model=ProposalReceiptView)
def submit_bridge_work_result(
    request_id: RequestId,
    payload: ProposalSubmissionRequest,
    response: Response,
    principal: AutomationPrincipal = Depends(require_proposals_write),
    db: Session = Depends(get_db),
) -> ProposalReceiptView:
    _mark_private(response)
    if payload.request_id != request_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_result",
                "message": "Path request_id does not match body request_id",
            },
            headers=NO_STORE_HEADERS,
        )
    try:
        service = ProposalService(db)
        return service.submit_proposal(
            grant_id=principal.grant_id,
            request_id=request_id,
            submission=payload,
        )
    except AgentWorkError as exc:
        raise _bridge_error(exc) from exc


@router.get("/work-requests/{request_id}/result", response_model=ProposalReceiptView)
def get_bridge_work_result(
    request_id: RequestId,
    response: Response,
    principal: AutomationPrincipal = Depends(get_bridge_principal),
    db: Session = Depends(get_db),
) -> ProposalReceiptView:
    _mark_private(response)
    try:
        service = ProposalService(db)
        return service.get_work_result(
            grant_id=principal.grant_id,
            request_id=request_id,
        )
    except AgentWorkError as exc:
        raise _bridge_error(exc) from exc


@router.get("/resume-templates", response_model=list[ResumeTemplateView])
def list_bridge_resume_templates(
    response: Response,
    principal: AutomationPrincipal = Depends(get_bridge_principal),
) -> list[ResumeTemplateView]:
    _mark_private(response)
    return [
        ResumeTemplateView(
            id=p.id, name=p.name, version=p.version, locale=p.locale, layout=p.layout
        )
        for p in list_template_presets()
    ]
