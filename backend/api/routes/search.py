import logging
from datetime import datetime

from fastapi import APIRouter, Depends, BackgroundTasks, UploadFile, File, HTTPException, Request
from sqlalchemy.orm import Session

from backend.db.base import get_db, SessionLocal
from backend.repositories.profile_repository import ProfileRepository
from backend.api.deps import get_current_user_id, limiter
from backend.services.search_status import get_status, cancel_task, update_status, get_all_statuses
from backend.services.utils import extract_text_from_file
from backend.schemas.profile import StartSearchRequest
from backend.services.search_service import get_search_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/upload-cv")
@limiter.limit("10/minute")
async def upload_cv(
    request: Request,
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")
        
    text = await extract_text_from_file(file)
    return {"text": text, "filename": file.filename}


@router.post("/start")
@limiter.limit("5/minute")
async def start_search(
    request: Request,
    profile_request: StartSearchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    profile_repo = ProfileRepository(db)

    # If it's a manual search from the form (no ID or explicit history flag)
    # create a new History entry.
    # Otherwise if it has an ID, use that (re-run).
    # Sanitize profile_data: convert empty strings to None for numeric fields
    # Exclude transient flags that don't map to DB columns
    _TRANSIENT_FIELDS = {"force_regenerate_cv_summary", "force_regenerate_queries"}
    profile_data = {k: v for k, v in profile_request.model_dump(exclude_unset=True).items() if k not in _TRANSIENT_FIELDS}
    numeric_fields = ["max_queries", "posted_within_days", "max_distance", "schedule_interval_hours"]
    for field in numeric_fields:
        val = getattr(profile_request, field, None)
        if val == "":
            profile_data[field] = None

    profile_id = profile_data.get("id")
    
    if profile_id:
        profile = profile_repo.get(profile_id)
        if not profile or profile.user_id != user_id:
            raise HTTPException(status_code=403, detail="Unauthorized profile access")
        # Update existing if needed (e.g. if settings changed before re-run)
        # Profile fields such as role, location, etc., are meant to be immutable.
        # Just reset the stopped flag so it can run again.
        profile = profile_repo.update(profile, {"is_stopped": False})
    else:
        # New manual search -> create history entry
        profile_data["user_id"] = user_id
        profile_data["is_history"] = True
        # If it doesn't have a name, give it a timestamped one
        if not profile_data.get("name") or profile_data["name"] in ["Default Profile", "My Profile"]:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            profile_data["name"] = f"Search {timestamp}"
            
        profile_data["is_stopped"] = False
        profile = profile_repo.create(profile_data)

    # Cancel any existing task for this profile before starting a new one
    cancel_task(profile.id)
    
    # Extract force-regeneration flags from the original request (not stored in DB)
    force_regen_cv = profile_request.force_regenerate_cv_summary
    force_regen_q = profile_request.force_regenerate_queries
    
    # The FastAPI dependency session `db` is closed as soon as this HTTP route returns,
    # so the background task needs its own fresh session to avoid DetachedInstanceError.
    async def run_search_background(_profile_id: int, _force_cv: bool, _force_q: bool):
        fresh_db = SessionLocal()
        try:
            svc = get_search_service(fresh_db)
            await svc.run_search(
                _profile_id,
                force_regenerate_cv_summary=_force_cv,
                force_regenerate_queries=_force_q,
            )
        finally:
            fresh_db.close()
            
    background_tasks.add_task(run_search_background, profile.id, force_regen_cv, force_regen_q)

    return {"message": "Search started", "profile_id": profile.id}


@router.post("/stop/{profile_id}")
async def stop_search(
    profile_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    profile_repo = ProfileRepository(db)
    profile = profile_repo.get(profile_id)
    
    if not profile or profile.user_id != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized profile access")
        
    profile.is_stopped = True
    profile_repo.update(profile, {"is_stopped": True})
    
    # Also update the in-memory status so frontend sees it immediately
    update_status(profile_id, state="stopped", error="Search stopped by user.")
    
    # Explicitly cancel the background task if it exists
    cancel_task(profile_id)
    
    return {"message": "Search stopped successfully"}


@router.get("/status/all")
def get_all_search_statuses(
    user_id: int = Depends(get_current_user_id),
):
    return get_all_statuses(user_id=user_id)

@router.get("/status/{profile_id}")
def get_search_status(
    profile_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get the current status of a background search for the given profile."""
    repo = ProfileRepository(db)
    profile = repo.get(profile_id)
    if not profile or profile.user_id != user_id:
        raise HTTPException(status_code=404, detail="Profile not found or unauthorized")
        
    return get_status(profile_id)
