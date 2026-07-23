from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_id, limiter
from backend.db.base import get_db
from backend.workflows.schemas import WorkflowEnqueue, WorkflowRunResponse
from backend.workflows.service import (
    WorkflowConflictError,
    WorkflowNotFoundError,
    WorkflowService,
)

router = APIRouter()


@router.get("", response_model=list[WorkflowRunResponse])
def list_workflows(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
) -> list[WorkflowRunResponse]:
    return WorkflowService(db).list(user_id)


@router.post("", response_model=WorkflowRunResponse, status_code=202)
@limiter.limit("20/minute")
def enqueue_workflow(
    request: Request,
    data: WorkflowEnqueue,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WorkflowRunResponse:
    try:
        return WorkflowRunResponse.model_validate(WorkflowService(db).enqueue(user_id, data))
    except WorkflowConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{run_id}", response_model=WorkflowRunResponse)
def get_workflow(
    run_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WorkflowRunResponse:
    try:
        return WorkflowService(db).get(user_id, run_id)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{run_id}/cancel", response_model=WorkflowRunResponse)
def cancel_workflow(
    run_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WorkflowRunResponse:
    try:
        return WorkflowRunResponse.model_validate(
            WorkflowService(db).request_cancel(user_id, run_id)
        )
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{run_id}/retry", response_model=WorkflowRunResponse, status_code=202)
def retry_workflow(
    run_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WorkflowRunResponse:
    try:
        return WorkflowRunResponse.model_validate(WorkflowService(db).retry(user_id, run_id))
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
