import asyncio
import hashlib
import logging
from datetime import datetime
from typing import cast

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_id, limiter, require_local_analysis_ready
from backend.career.service import CareerProfileService, CareerSearchSnapshotError
from backend.core.config import settings
from backend.core.diagnostics import (
    FailureCode,
    diagnose_failure,
    log_failure,
    public_status_message,
)
from backend.db.base import SessionLocal, get_db
from backend.repositories.profile_repository import ProfileRepository
from backend.schemas.profile import StartSearchRequest
from backend.schemas.search import CVUploadResponse, SearchStartResponse, SearchStopResponse
from backend.search.consent import load_job_source_consents, public_job_source_catalog
from backend.search.orchestrator import AdeccoProvider
from backend.services.search_service import get_search_service
from backend.services.search_status import (
    cancel_task,
    get_all_statuses,
    get_status,
    release_task,
    reserve_task,
    update_status,
)
from backend.services.utils import extract_text_from_file, safe_upload_filename

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


@router.get("/sources")
def job_sources(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    available = {"job_room", "swissdevjobs"}
    if AdeccoProvider is not None:
        available.add("adecco")
    return cast(
        list[dict[str, object]],
        public_job_source_catalog(
            load_job_source_consents(db, user_id),
            available=available,
        ),
    )


@router.post("/upload-cv", response_model=CVUploadResponse)
@limiter.limit("10/minute")
async def upload_cv(
    request: Request,
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    if file.size is not None and file.size > settings.MAX_UPLOAD_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File too large for local CV processing.",
        )

    text = await extract_text_from_file(file)
    return {"text": text, "filename": safe_upload_filename(file.filename, fallback="cv")}


@router.post("/start", response_model=SearchStartResponse)
@limiter.limit("5/minute")
async def start_search(
    request: Request,
    profile_request: StartSearchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    _analysis_ready: None = Depends(require_local_analysis_ready),
):
    if settings.OFFLINE_MODE is True:
        raise HTTPException(
            status_code=503,
            detail="Live job-source access is disabled while offline mode is active",
        )
    profile_repo = ProfileRepository(db)

    active_states = {"reserved", "generating", "searching", "analyzing"}
    user_statuses = get_all_statuses(user_id=user_id)
    user_active_count = sum(
        1 for status in user_statuses.values() if (status or {}).get("state") in active_states
    )
    if user_active_count >= settings.MAX_CONCURRENT_SEARCHES_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=(
                "Too many active searches. "
                f"Maximum allowed is {settings.MAX_CONCURRENT_SEARCHES_PER_USER}."
            ),
        )

    # A campaign captures its candidate evidence once. Reruns deliberately keep the saved
    # cv_content and source metadata, even if the Career Vault has changed in the meantime.
    _TRANSIENT_FIELDS = {
        "force_regenerate_cv_summary",
        "force_regenerate_queries",
        "profile_source",
    }
    request_data = profile_request.model_dump(exclude_unset=True)
    preference_data = {k: request_data.get(k) for k in _PREFERENCE_FIELDS if k in request_data}
    profile_data = {
        k: v
        for k, v in request_data.items()
        if k not in _TRANSIENT_FIELDS and k not in _PREFERENCE_FIELDS
    }
    numeric_fields = [
        "max_queries",
        "posted_within_days",
        "max_distance",
        "schedule_interval_hours",
    ]
    for field in numeric_fields:
        val = getattr(profile_request, field, None)
        if val == "":
            profile_data[field] = None

    profile_id = profile_data.get("id")

    if profile_id:
        profile = profile_repo.get(profile_id)
        if not profile or profile.user_id != user_id:
            raise HTTPException(status_code=403, detail="Unauthorized profile access")
        reservation_token = reserve_task(profile.id, return_token=True, user_id=user_id)
        if not reservation_token:
            raise HTTPException(
                status_code=409, detail="A search is already running for this profile"
            )
        profile = profile_repo.update(profile, {"is_stopped": False})
    else:
        profile_source = profile_request.profile_source
        supplied_cv = str(profile_data.get("cv_content") or "")
        if profile_source is None:
            profile_source = "uploaded_cv" if supplied_cv.strip() else "career_vault"

        source_metadata: dict[str, object]
        if profile_source == "career_vault":
            try:
                snapshot = CareerProfileService(db).search_snapshot(user_id)
            except CareerSearchSnapshotError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            profile_data["cv_content"] = snapshot.text
            source_metadata = {
                "profile_source": "career_vault",
                "career_profile_id": snapshot.profile_id,
                "career_profile_revision": snapshot.profile_revision,
                "career_fact_ids": list(snapshot.fact_ids),
                "source_snapshot_sha256": snapshot.sha256,
            }
        else:
            if not supplied_cv.strip():
                raise HTTPException(
                    status_code=422,
                    detail="Uploaded CV search requires non-empty cv_content.",
                )
            source_metadata = {
                "profile_source": "uploaded_cv",
                "source_snapshot_sha256": hashlib.sha256(supplied_cv.encode("utf-8")).hexdigest(),
            }

        profile_data["user_id"] = user_id
        profile_data["is_history"] = True
        advanced_preferences = {
            key: value for key, value in preference_data.items() if value is not None
        }
        advanced_preferences.update(source_metadata)
        profile_data["advanced_preferences"] = advanced_preferences
        if not profile_data.get("name") or profile_data["name"] in [
            "",
            "Default Profile",
            "My Profile",
        ]:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            profile_data["name"] = f"Search {timestamp}"

        profile_data["is_stopped"] = False
        profile = profile_repo.create(profile_data)

        reservation_token = reserve_task(profile.id, return_token=True, user_id=user_id)
        if not reservation_token:
            raise HTTPException(
                status_code=409, detail="A search is already running for this profile"
            )

    force_regen_cv = profile_request.force_regenerate_cv_summary
    force_regen_q = profile_request.force_regenerate_queries

    async def run_search_background(
        _profile_id: int,
        _force_cv: bool,
        _force_q: bool,
        _reservation_token: str,
    ):
        fresh_db = None
        try:
            fresh_db = SessionLocal()
            svc = get_search_service(fresh_db)
            await svc.run_search(
                _profile_id,
                force_regenerate_cv_summary=_force_cv,
                force_regenerate_queries=_force_q,
                reservation_token=_reservation_token,
            )
        except asyncio.CancelledError:
            release_task(_profile_id, _reservation_token)
            raise
        except Exception as error:
            release_task(_profile_id, _reservation_token)
            diagnostic = diagnose_failure(error, FailureCode.SEARCH_UNEXPECTED)
            log_failure(logger, diagnostic, level=logging.ERROR)
        finally:
            if fresh_db is not None:
                fresh_db.close()

    try:
        background_tasks.add_task(
            run_search_background,
            profile.id,
            force_regen_cv,
            force_regen_q,
            reservation_token,
        )
    except Exception:
        release_task(profile.id, reservation_token)
        raise

    stored_source = getattr(profile, "profile_source", None)
    resolved_source = (
        stored_source if stored_source in {"career_vault", "uploaded_cv"} else "uploaded_cv"
    )
    stored_sha256 = getattr(profile, "source_snapshot_sha256", None)
    resolved_sha256 = (
        stored_sha256
        if isinstance(stored_sha256, str)
        and len(stored_sha256) == 64
        and all(character in "0123456789abcdef" for character in stored_sha256)
        else hashlib.sha256(
            str(getattr(profile, "cv_content", "") or "").encode("utf-8")
        ).hexdigest()
    )
    return {
        "message": "Search started",
        "profile_id": profile.id,
        "profile_source": resolved_source,
        "source_snapshot_sha256": resolved_sha256,
    }


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
    update_status(
        profile_id,
        state="stopped",
        error=public_status_message(FailureCode.SEARCH_STOPPED),
    )

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
