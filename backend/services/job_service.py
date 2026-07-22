import hashlib
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.repositories.job_repository import JobRepository
from backend.repositories.profile_repository import ProfileRepository
from backend.schemas import JobCreate, JobUpdate


class JobService:
    def __init__(self, db: Session):
        self.repo = JobRepository(db)
        self.profile_repo = ProfileRepository(db)

    @staticmethod
    def _stable_manual_platform_job_id(user_id: int, job_dict: Dict[str, Any]) -> str:
        """Return a stable identifier in a server-owned, per-user namespace.

        Manual listings are private user input rather than shared provider data.  Including
        the authenticated user id in the one-way fingerprint prevents two users who save the
        same URL from being attached to the same mutable ``ScrapedJob`` row.  The caller must
        never use a client-supplied platform id for the ``manual`` platform.
        """
        fingerprint_parts = [
            f"user:{user_id}",
            "platform:manual",
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
        from backend.models import ScrapedJob

        job_dict = job_in.model_dump()
        profile_id = job_dict.get("search_profile_id")
        if profile_id is not None:
            profile = self.profile_repo.get_for_user(profile_id, user_id)
            if not profile:
                raise HTTPException(status_code=403, detail="Unauthorized profile access")

        # Split fields: scraped-job fields vs user-relationship fields
        platform = str(job_dict.get("platform") or "manual").strip().lower() or "manual"
        supplied_platform_job_id = str(job_dict.get("platform_job_id") or "").strip()
        if platform == "manual":
            # Manual ids are always derived server-side.  Ignoring a spoofed client id is
            # essential: otherwise a user could deliberately collide with another user's row.
            platform_job_id = self._stable_manual_platform_job_id(user_id, job_dict)
        else:
            platform_job_id = supplied_platform_job_id or self._stable_manual_platform_job_id(
                user_id, {**job_dict, "platform": "manual"}
            )

        scraped_fields = {
            "title": job_dict.get("title", ""),
            "company": job_dict.get("company", ""),
            "platform": platform,
            "platform_job_id": platform_job_id,
            "external_url": job_dict.get("external_url", None),
            "description": job_dict.get("description", None),
            "location": job_dict.get("location", None),
            "workload": job_dict.get("workload", None),
        }

        # Upsert or create ScrapedJob
        existing_scraped = self.repo.get_scraped_job_by_platform_and_id(
            scraped_fields["platform"],
            scraped_fields["platform_job_id"],
        )
        scraped_job = existing_scraped
        if not existing_scraped:
            scraped_job = ScrapedJob(**{k: v for k, v in scraped_fields.items() if v is not None})
            created_ok = self.repo.create_scraped_job_nested(scraped_job)
            if not created_ok:
                scraped_job = self.repo.get_scraped_job_by_platform_and_id(
                    scraped_fields["platform"],
                    scraped_fields["platform_job_id"],
                )
                if not scraped_job:
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to create shared scraped job record",
                    )

        if scraped_job is None:
            raise HTTPException(status_code=500, detail="Shared scraped job record is unavailable")

        # POSTing the same manual capture twice is a retry, not a request for a duplicate
        # relationship.  SQLite permits duplicate composite UNIQUE rows when the profile is
        # NULL, so enforce idempotency explicitly at the service boundary.
        existing_job = self.repo.get_job_by_user_scraped_profile(
            user_id,
            scraped_job.id,
            profile_id,
        )
        if existing_job is not None:
            return existing_job

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
