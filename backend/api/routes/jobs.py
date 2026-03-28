from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.deps import get_current_user_id, job_service_dep
from backend.schemas import JobCreate, JobPaginationResponse, JobResponse, JobUpdate
from backend.services.job_service import JobService

router = APIRouter()


@router.get("/", response_model=JobPaginationResponse)
def read_jobs(
    # ── Filters ──
    search_profile_id: Optional[int] = None,
    applied: Optional[bool] = None,
    worth_applying: Optional[bool] = None,
    min_score: Optional[float] = Query(None, ge=0, le=100),
    max_score: Optional[float] = Query(None, ge=0, le=100),
    min_distance: Optional[float] = Query(None, ge=0),
    max_distance: Optional[float] = Query(None, ge=0),
    # ── Sorting ──
    sort_by: Literal["created_at", "affinity_score", "distance_km", "title", "publication_date"] = Query("created_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    # ── Pagination ──
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    # ── Auth & DI ──
    user_id: int = Depends(get_current_user_id),
    job_service: JobService = Depends(job_service_dep),
):
    filters = {
        "min_score": min_score,
        "max_score": max_score,
        "min_distance": min_distance,
        "max_distance": max_distance,
        "worth_applying": worth_applying,
        "applied": applied,
        "search_profile_id": search_profile_id,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }
    if min_score is not None and max_score is not None and min_score > max_score:
        raise HTTPException(status_code=422, detail="min_score cannot be greater than max_score")
    if min_distance is not None and max_distance is not None and min_distance > max_distance:
        raise HTTPException(status_code=422, detail="min_distance cannot be greater than max_distance")
    return job_service.get_jobs_by_user(user_id, page, page_size, filters)


@router.post("/", response_model=JobResponse)
def create_job(
    job_in: JobCreate,
    user_id: int = Depends(get_current_user_id),
    job_service: JobService = Depends(job_service_dep),
):
    return job_service.create_job(user_id, job_in)


@router.patch("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: int,
    updates: JobUpdate,
    user_id: int = Depends(get_current_user_id),
    job_service: JobService = Depends(job_service_dep),
):
    return job_service.update_job(user_id, job_id, updates)

@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: int,
    user_id: int = Depends(get_current_user_id),
    job_service: JobService = Depends(job_service_dep),
):
    job_service.delete_job(user_id, job_id)
