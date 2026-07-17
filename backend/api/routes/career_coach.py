from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_id, limiter
from backend.career.coach import (
    CareerCoachService,
    CoachNotFoundError,
    CoachUnavailableError,
    CoachValidationError,
)
from backend.career.coach_schemas import (
    CoachConversationResponse,
    CoachConversationSummary,
    CoachMessageCreate,
    CoachReply,
)
from backend.db.base import get_db
from backend.providers.llm.factory import get_provider_for_step

router = APIRouter()


def _service(db: Session) -> CareerCoachService:
    return CareerCoachService(db, inference_factory=get_provider_for_step)


@router.get("/conversations", response_model=list[CoachConversationSummary])
def list_conversations(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
) -> list[CoachConversationSummary]:
    try:
        return _service(db).list(user_id)
    except CoachValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/conversations/{conversation_id}", response_model=CoachConversationResponse)
def get_conversation(
    conversation_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> CoachConversationResponse:
    try:
        return _service(db).get(user_id, conversation_id)
    except CoachNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    try:
        _service(db).delete(user_id, conversation_id)
    except CoachNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/messages", response_model=CoachReply)
@limiter.limit("20/minute")
async def create_message(
    request: Request,
    data: CoachMessageCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> CoachReply:
    try:
        return await _service(db).reply(user_id, data)
    except CoachNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CoachValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CoachUnavailableError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
