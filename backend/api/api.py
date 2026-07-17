from fastapi import APIRouter

from backend.api.routes import (
    applications,
    auth,
    career_coach,
    career_profile,
    jobs,
    local_model,
    portability,
    profiles,
    resumes,
    schedules,
    search,
    workflows,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(applications.router, prefix="/applications", tags=["applications"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["schedules"])
api_router.include_router(local_model.router, prefix="/local-model", tags=["local-model"])
api_router.include_router(portability.router, prefix="/portability", tags=["portability"])
api_router.include_router(career_profile.router, prefix="/career-profile", tags=["career-profile"])
api_router.include_router(career_coach.router, prefix="/career-coach", tags=["career-coach"])
api_router.include_router(resumes.photo_router, prefix="/career-profile", tags=["career-profile"])
api_router.include_router(resumes.router, prefix="/resumes", tags=["resumes"])
api_router.include_router(resumes.artifact_router, prefix="/resume-artifacts", tags=["resumes"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
