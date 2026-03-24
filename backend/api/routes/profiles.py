from typing import List
from fastapi import APIRouter, Depends
from backend.api.deps import get_current_user_id, get_profile_service
from backend.services.profile_service import ProfileService
from backend.schemas import SearchProfile, SearchProfileCreate, SearchProfileUpdate, ScheduleToggle

router = APIRouter()

@router.get("/", response_model=List[SearchProfile])
def read_profiles(
    skip: int = 0,
    limit: int = 100,
    user_id: int = Depends(get_current_user_id),
    profile_service: ProfileService = Depends(get_profile_service)
):
    return profile_service.get_profiles_by_user(user_id, skip=skip, limit=limit)

@router.post("/", response_model=SearchProfile)
def create_profile(
    profile_in: SearchProfileCreate,
    user_id: int = Depends(get_current_user_id),
    profile_service: ProfileService = Depends(get_profile_service)
):
    return profile_service.create_profile(user_id, profile_in)

@router.patch("/{profile_id}/schedule", response_model=SearchProfile)
def toggle_schedule(
    profile_id: int,
    schedule: ScheduleToggle,
    user_id: int = Depends(get_current_user_id),
    profile_service: ProfileService = Depends(get_profile_service)
):
    return profile_service.toggle_schedule(user_id, profile_id, schedule)

@router.patch("/{profile_id}", response_model=SearchProfile)
def update_profile(
    profile_id: int,
    profile_in: SearchProfileUpdate,
    user_id: int = Depends(get_current_user_id),
    profile_service: ProfileService = Depends(get_profile_service)
):
    return profile_service.update_profile(user_id, profile_id, profile_in)
