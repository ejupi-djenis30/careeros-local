from typing import List

from fastapi import APIRouter, Depends, Request

from backend.api.deps import get_current_user_id, limiter, profile_service_dep
from backend.schemas import ScheduleToggle, SearchProfile, SearchProfileCreate, SearchProfileUpdate
from backend.services.profile_service import ProfileService

router = APIRouter()

@router.get("/", response_model=List[SearchProfile])
def read_profiles(
    skip: int = 0,
    limit: int = 100,
    user_id: int = Depends(get_current_user_id),
    profile_service: ProfileService = Depends(profile_service_dep)
):
    return profile_service.get_profiles_by_user(user_id, skip=skip, limit=limit)

@router.post("/", response_model=SearchProfile)
@limiter.limit("20/minute")
def create_profile(
    request: Request,
    profile_in: SearchProfileCreate,
    user_id: int = Depends(get_current_user_id),
    profile_service: ProfileService = Depends(profile_service_dep)
):
    return profile_service.create_profile(user_id, profile_in)

@router.patch("/{profile_id}/schedule", response_model=SearchProfile)
@limiter.limit("30/minute")
def toggle_schedule(
    request: Request,
    profile_id: int,
    schedule: ScheduleToggle,
    user_id: int = Depends(get_current_user_id),
    profile_service: ProfileService = Depends(profile_service_dep)
):
    return profile_service.toggle_schedule(user_id, profile_id, schedule)

@router.patch("/{profile_id}", response_model=SearchProfile)
@limiter.limit("30/minute")
def update_profile(
    request: Request,
    profile_id: int,
    profile_in: SearchProfileUpdate,
    user_id: int = Depends(get_current_user_id),
    profile_service: ProfileService = Depends(profile_service_dep)
):
    return profile_service.update_profile(user_id, profile_id, profile_in)

@router.delete("/{profile_id}", status_code=204)
@limiter.limit("20/minute")
def delete_profile(
    request: Request,
    profile_id: int,
    user_id: int = Depends(get_current_user_id),
    profile_service: ProfileService = Depends(profile_service_dep)
):
    profile_service.delete_profile(user_id, profile_id)
