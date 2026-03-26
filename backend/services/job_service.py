import hashlib
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
        self, user_id: int, page: int, page_size: int,
        filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        skip = (page - 1) * page_size

        items = self.repo.get_by_user_filtered(
            user_id, skip=skip, limit=page_size, **filters
        )

        # Feature 2: populate applied_elsewhere badge
        # Get all ScrapedJob IDs where this user has applied=True (across all profiles)
        applied_scraped_ids = set()
        if items:
            applied_scraped_ids = self.repo.get_applied_scraped_job_ids(user_id)

        # Attach applied_elsewhere as a Python attribute so Pydantic can read it
        for item in items:
            item.applied_elsewhere = (
                not item.applied
                and item.scraped_job_id in applied_scraped_ids
            )

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
            "avg_score": agg["avg_score"]
        }


    def create_job(self, user_id: int, job_in: JobCreate):
        from backend.models import ScrapedJob

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
            "platform_job_id": job_dict.get("platform_job_id", None) or self._stable_manual_platform_job_id(job_dict),
            "external_url": job_dict.get("external_url", None),
            "description": job_dict.get("description", None),
            "location": job_dict.get("location", None),
            "workload": job_dict.get("workload", None),
        }

        # Upsert or create ScrapedJob
        existing_scraped = (
            self.repo.db.query(ScrapedJob)
            .filter(
                ScrapedJob.platform == scraped_fields["platform"],
                ScrapedJob.platform_job_id == scraped_fields["platform_job_id"],
            )
            .first()
        )
        if not existing_scraped:
            scraped_job = ScrapedJob(**{k: v for k, v in scraped_fields.items() if v is not None})
            self.repo.db.add(scraped_job)
            self.repo.db.flush()
        else:
            scraped_job = existing_scraped

        # Create the user-specific Job record
        job_data = {
            "user_id": user_id,
            "scraped_job_id": scraped_job.id,
            "applied": job_dict.get("applied", False),
            "is_scraped": job_dict.get("is_scraped", False),
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
        return self.repo.update(job, updates)

    def delete_job(self, user_id: int, job_id: int):
        job = self.repo.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        self.repo.delete(job.id)


def get_job_service(db: Session) -> JobService:
    return JobService(db)
