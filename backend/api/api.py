from fastapi import APIRouter

from backend.api.routes import auth, jobs, profiles, schedules, search

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["schedules"])
