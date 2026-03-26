from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.api.deps import get_current_user_id, job_service_dep
from backend.services.job_service import JobService
from backend.schemas import JobResponse, JobCreate, JobUpdate, JobPaginationResponse

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
    sort_by: str = Query("created_at", pattern="^(created_at|affinity_score|distance_km|title|publication_date)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
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
