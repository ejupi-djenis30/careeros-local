from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.ai.evaluation import (
    EvaluationRunSummary,
    list_reports,
    persist_report,
    run_live_evaluation,
    validate_offline_dataset,
)
from backend.api.deps import get_current_user_id
from backend.db.base import get_db
from backend.providers.llm.factory import get_provider_for_step

router = APIRouter()


class EvaluationRunRequest(BaseModel):
    mode: Literal["offline", "live"] = "offline"


@router.get("", response_model=list[EvaluationRunSummary])
def evaluations(
    _user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[EvaluationRunSummary]:
    return list_reports(db)


@router.post("/run", response_model=EvaluationRunSummary)
async def run_evaluation(
    payload: EvaluationRunRequest,
    _user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> EvaluationRunSummary:
    try:
        report = (
            validate_offline_dataset()
            if payload.mode == "offline"
            else await run_live_evaluation(get_provider_for_step("default"))
        )
        return persist_report(db, report)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail=f"Local evaluation could not run ({type(exc).__name__})",
        ) from exc
