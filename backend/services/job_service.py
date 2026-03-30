import hashlib
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.models import SearchProfile
from backend.repositories.job_repository import JobRepository
from backend.schemas import JobCreate, JobUpdate


class JobService:
    def __init__(self, db: Session):
        self.repo = JobRepository(db)

    @staticmethod
    def _stable_manual_platform_job_id(job_dict: Dict[str, Any]) -> str:
        fingerprint_parts = [
            str(job_dict.get("platform") or "manual").strip().lower(),
            str(job_dict.get("title") or "").strip().lower(),
            str(job_dict.get("company") or "").strip().lower(),
            str(job_dict.get("external_url") or "").strip().lower(),
        ]
        digest = hashlib.sha256("|".join(fingerprint_parts).encode("utf-8")).hexdigest()
        return f"manual-{digest[:24]}"

    def get_jobs_by_user(
        self, user_id: int, page: int, page_size: int, filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        skip = (page - 1) * page_size

        items = self.repo.get_by_user_filtered(user_id, skip=skip, limit=page_size, **filters)

        # Feature 2: populate applied_elsewhere badge
        # Get all ScrapedJob IDs where this user has applied=True (across all profiles)
        applied_scraped_ids = set()
        if items:
            applied_scraped_ids = self.repo.get_applied_scraped_job_ids(user_id)

        # Attach applied_elsewhere as a Python attribute so Pydantic can read it
        for item in items:
            item.applied_elsewhere = not item.applied and item.scraped_job_id in applied_scraped_ids

        # Remove pagination/sorting params before passing to count/stats
        stats_filters = filters.copy()
        stats_filters.pop("sort_by", None)
        stats_filters.pop("sort_order", None)

        agg = self.repo.get_count_and_stats_by_user_filtered(user_id, **stats_filters)

        return {
            "items": items,
            "total": agg["total"],
            "page": page,
            "pages": (agg["total"] + page_size - 1) // page_size,
            "total_applied": agg["total_applied"],
            "avg_score": agg["avg_score"],
        }

    def create_job(self, user_id: int, job_in: JobCreate):
        job_dict = job_in.model_dump()
        profile_id = job_dict.get("search_profile_id")
        if profile_id is not None:
            profile = (
                self.repo.db.query(SearchProfile)
                .filter(SearchProfile.id == profile_id, SearchProfile.user_id == user_id)
                .first()
            )
            if not profile:
                raise HTTPException(status_code=403, detail="Unauthorized profile access")

        # Split fields: scraped-job fields vs user-relationship fields
        scraped_fields = {
            "title": job_dict.get("title", ""),
            "company": job_dict.get("company", ""),
            "platform": job_dict.get("platform") or "manual",
            "platform_job_id": job_dict.get("platform_job_id", None)
            or self._stable_manual_platform_job_id(job_dict),
            "external_url": job_dict.get("external_url", None),
            "description": job_dict.get("description", None),
            "location": job_dict.get("location", None),
            "workload": job_dict.get("workload", None),
        }

        # Upsert ScrapedJob via repository (never access DB directly from service)
        scraped_job = self.repo.get_or_create_scraped_job(scraped_fields)

        # Create the user-specific Job record
        job_data = {
            "user_id": user_id,
            "scraped_job_id": scraped_job.id,
            "applied": job_dict.get("applied", False),
            "affinity_score": job_dict.get("affinity_score", None),
            "search_profile_id": profile_id,
        }
        return self.repo.create(job_data)

    def update_job(self, user_id: int, job_id: int, updates: JobUpdate):
        job = self.repo.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        update_data = updates.model_dump(exclude_unset=True)

        # Auto-timestamp dismissed_at when dismissed flag is toggled
        if update_data.get("dismissed") is True and not job.dismissed:
            update_data["dismissed_at"] = datetime.now(timezone.utc)
        elif update_data.get("dismissed") is False:
            update_data["dismissed_at"] = None

        result = self.repo.update(job, update_data)

        # Recompute preference signals after any interaction that carries signal
        if "applied" in update_data or "dismissed" in update_data:
            from backend.services.preference_service import compute_and_save_preferences

            compute_and_save_preferences(user_id, self.repo.db)

        return result

    def record_view(self, user_id: int, job_id: int):
        """Idempotently record the first time a user views a job's analysis."""
        job = self.repo.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        if job.viewed_at is None:
            self.repo.update(job, {"viewed_at": datetime.now(timezone.utc)})
        return job

    def delete_job(self, user_id: int, job_id: int):
        """Soft-delete: mark dismissed instead of hard-deleting rows."""
        job = self.repo.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        self.repo.update(
            job,
            {
                "dismissed": True,
                "dismissed_at": datetime.now(timezone.utc),
            },
        )


def get_job_service(db: Session) -> JobService:
    return JobService(db)
