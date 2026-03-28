import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_id, limiter
from backend.core.config import settings
from backend.db.base import SessionLocal, get_db
from backend.repositories.profile_repository import ProfileRepository
from backend.schemas.profile import StartSearchRequest
from backend.schemas.search import CVUploadResponse, SearchStartResponse, SearchStopResponse
from backend.services.search_service import get_search_service
from backend.services.search_status import (
    cancel_task,
    get_all_statuses,
    get_status,
    release_task,
    reserve_task,
    update_status,
)
from backend.services.utils import extract_text_from_file

logger = logging.getLogger(__name__)

router = APIRouter()


_PREFERENCE_FIELDS = {
    "preferred_languages",
    "preferred_domains",
    "remote_only",
    "salary_min_chf",
    "workload_min",
    "workload_max",
    "hard_max_distance_km",
}


@router.post("/upload-cv", response_model=CVUploadResponse)
@limiter.limit("10/minute")
async def upload_cv(
    request: Request,
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    MAX_FILE_SIZE = settings.MAX_UPLOAD_FILE_SIZE
    # Reject early using Content-Length if the client provides it, to avoid
    # reading a potentially huge payload into memory before we can check it.
    if file.size is not None and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")
    # Rewind so extract_text_from_file can read it again
    await file.seek(0)

    text = await extract_text_from_file(file)
    return {"text": text, "filename": file.filename}


@router.post("/start", response_model=SearchStartResponse)
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
    request_data = profile_request.model_dump(exclude_unset=True)
    preference_data = {k: request_data.get(k) for k in _PREFERENCE_FIELDS if k in request_data}
    profile_data = {
        k: v
        for k, v in request_data.items()
        if k not in _TRANSIENT_FIELDS and k not in _PREFERENCE_FIELDS
    }
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
        # Reserve the task slot BEFORE modifying the profile to avoid leaving
        # the profile in an inconsistent state (is_stopped=False) if the slot
        # is already taken by a concurrent run.
        if not reserve_task(profile.id):
            raise HTTPException(status_code=409, detail="A search is already running for this profile")
        # Update existing if needed (e.g. if settings changed before re-run)
        # Profile fields such as role, location, etc., are meant to be immutable.
        # Just reset the stopped flag so it can run again.
        profile = profile_repo.update(profile, {"is_stopped": False})
    else:
        # New manual search -> create history entry
        profile_data["user_id"] = user_id
        profile_data["is_history"] = True
        # Keep advanced user preferences together for forward-compatible filtering
        profile_data["advanced_preferences"] = {
            key: value for key, value in preference_data.items() if value is not None
        } or None
        # If it doesn't have a name, give it a timestamped one
        if not profile_data.get("name") or profile_data["name"] in ["", "Default Profile", "My Profile"]:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            profile_data["name"] = f"Search {timestamp}"

        profile_data["is_stopped"] = False
        profile = profile_repo.create(profile_data)

        if not reserve_task(profile.id):
            raise HTTPException(status_code=409, detail="A search is already running for this profile")

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
        except Exception:
            # Safety net: if run_search never called register_task (e.g. get_search_service
            # raised), the reservation slot is still held. Release it so future searches
            # for this profile are not permanently blocked.
            # If register_task was already called, release_task is a no-op.
            release_task(_profile_id)
            logger.exception("Background search failed unexpectedly for profile %d", _profile_id)
        finally:
            fresh_db.close()

    try:
        background_tasks.add_task(run_search_background, profile.id, force_regen_cv, force_regen_q)
    except Exception:
        release_task(profile.id)
        raise

    return {"message": "Search started", "profile_id": profile.id}


@router.post("/stop/{profile_id}", response_model=SearchStopResponse)
async def stop_search(
    profile_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    profile_repo = ProfileRepository(db)
    profile = profile_repo.get(profile_id)

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.user_id != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized profile access")

    profile_repo.update(profile, {"is_stopped": True})

    # Also update the in-memory status so frontend sees it immediately
    update_status(profile_id, state="stopped", error="Search stopped by user.")

    # Explicitly cancel the background task if it exists
    cancel_task(profile_id)

    return {"message": "Search stopped successfully"}


@router.get("/status/all")
@limiter.limit("60/minute")
def get_all_search_statuses(
    request: Request,
    user_id: int = Depends(get_current_user_id),
):
    return get_all_statuses(user_id=user_id)

@router.get("/status/{profile_id}")
@limiter.limit("60/minute")
def get_search_status(
    request: Request,
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
