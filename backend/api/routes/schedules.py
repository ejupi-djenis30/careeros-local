from fastapi import APIRouter, Depends
from typing import Dict, Any, List

from backend.api.deps import get_current_user_id
from backend.db.base import get_db
from sqlalchemy.orm import Session
from backend.services.scheduler import get_scheduler, get_all_schedules

router = APIRouter()


@router.get("/status", response_model=Dict[str, Any])
def get_scheduler_status(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Return the current scheduler status."""
    scheduler = get_scheduler()
    user_jobs = get_all_schedules(user_id=user_id, db=db)
    return {
        "running": scheduler.running if scheduler else False,
        "jobs_scheduled": len(user_jobs) if scheduler and scheduler.running else 0,
    }


@router.get("/", response_model=List[Dict[str, Any]])
def list_schedules(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """List all scheduled search jobs."""
    return get_all_schedules(user_id=user_id, db=db)
