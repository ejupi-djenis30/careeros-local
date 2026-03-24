from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc, case, func
from backend.repositories.base import BaseRepository
from backend.models import Job, ScrapedJob


class JobRepository(BaseRepository[Job]):
    def __init__(self, db: Session):
        super().__init__(Job, db)

    def get_by_external_url(self, url: str) -> Optional[Job]:
        return self.db.query(self.model).join(self.model.scraped_job).filter(ScrapedJob.external_url == url).first()

    def get_by_platform_id(self, platform: str, platform_job_id: str) -> Optional[Job]:
        return (
            self.db.query(self.model)
            .join(self.model.scraped_job)
            .filter(ScrapedJob.platform == platform)
            .filter(ScrapedJob.platform_job_id == platform_job_id)
            .first()
        )

    def get_by_user(self, user_id: int, skip: int = 0, limit: int = 100) -> List[Job]:
        return (
            self.db.query(self.model)
            .filter(self.model.user_id == user_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_user_job_identifiers(self, user_id: int) -> List[Tuple[str, str, str, str, str]]:
        """Returns lightweight tuples of (platform, platform_job_id, external_url, title, company) for all user jobs."""
        return (
            self.db.query(
                ScrapedJob.platform,
                ScrapedJob.platform_job_id,
                ScrapedJob.external_url,
                ScrapedJob.title,
                ScrapedJob.company
            )
            .join(self.model.scraped_job)
            .filter(self.model.user_id == user_id)
            .all()
        )

    def get_profile_job_identifiers(self, profile_id: int) -> List[Tuple[str, str, str, str, str]]:
        """Returns lightweight tuples of (platform, platform_job_id, external_url, title, company) for jobs in a specific profile."""
        return (
            self.db.query(
                ScrapedJob.platform,
                ScrapedJob.platform_job_id,
                ScrapedJob.external_url,
                ScrapedJob.title,
                ScrapedJob.company
            )
            .join(self.model.scraped_job)
            .filter(self.model.search_profile_id == profile_id)
            .all()
        )

    def get_applied_scraped_job_ids(self, user_id: int) -> set:
        """Return a set of scrapped_job_id values where user has applied=True.
        
        Used by Feature 2 to populate the `applied_elsewhere` badge:
        any job whose ScrapedJob is in this set but whose own `applied` flag
        is False was applied in a different search profile.
        """
        rows = (
            self.db.query(self.model.scraped_job_id)
            .filter(
                self.model.user_id == user_id,
                self.model.applied == True,
            )
            .all()
        )
        return {row[0] for row in rows}

    def _build_filter_query(
        self,
        user_id: int,
        *,
        min_score: Optional[float] = None,
        max_score: Optional[float] = None,
        min_distance: Optional[float] = None,
        max_distance: Optional[float] = None,
        worth_applying: Optional[bool] = None,
        applied: Optional[bool] = None,
        search_profile_id: Optional[int] = None,
    ):
        q = self.db.query(self.model).filter(self.model.user_id == user_id)

        if search_profile_id is not None:
            q = q.filter(self.model.search_profile_id == search_profile_id)
        if min_score is not None:
            q = q.filter(self.model.affinity_score >= min_score)
        if max_score is not None:
            q = q.filter(self.model.affinity_score <= max_score)
        if min_distance is not None:
            q = q.filter(self.model.distance_km >= min_distance)
        if max_distance is not None:
            q = q.filter(self.model.distance_km <= max_distance)
        if worth_applying is not None:
            q = q.filter(self.model.worth_applying == worth_applying)
        if applied is not None:
            q = q.filter(self.model.applied == applied)
        return q

    def get_by_user_filtered(
        self,
        user_id: int,
        *,
        min_score: Optional[float] = None,
        max_score: Optional[float] = None,
        min_distance: Optional[float] = None,
        max_distance: Optional[float] = None,
        worth_applying: Optional[bool] = None,
        applied: Optional[bool] = None,
        search_profile_id: Optional[int] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 200,
    ) -> List[Job]:
        """Return jobs for a user with optional server-side filters."""
        q = self._build_filter_query(
            user_id,
            min_score=min_score,
            max_score=max_score,
            min_distance=min_distance,
            max_distance=max_distance,
            worth_applying=worth_applying,
            applied=applied,
            search_profile_id=search_profile_id,
        )

        # Sorting
        allowed_sort = {
            "created_at": self.model.created_at,
            "affinity_score": self.model.affinity_score,
            "distance_km": self.model.distance_km,
        }
        
        col = allowed_sort.get(sort_by, self.model.created_at)
        
        if sort_by in ["title", "publication_date"]:
            q = q.join(self.model.scraped_job)
            col = getattr(ScrapedJob, sort_by)

        order_fn = desc if sort_order == "desc" else asc
        q = q.order_by(order_fn(col))

        return q.offset(skip).limit(limit).all()

    def count_by_user_filtered(
        self,
        user_id: int,
        *,
        min_score: Optional[float] = None,
        max_score: Optional[float] = None,
        min_distance: Optional[float] = None,
        max_distance: Optional[float] = None,
        worth_applying: Optional[bool] = None,
        applied: Optional[bool] = None,
        search_profile_id: Optional[int] = None,
    ) -> int:
        q = self._build_filter_query(
            user_id,
            min_score=min_score,
            max_score=max_score,
            min_distance=min_distance,
            max_distance=max_distance,
            worth_applying=worth_applying,
            applied=applied,
            search_profile_id=search_profile_id,
        )
        return q.with_entities(func.count(self.model.id)).scalar()

    def get_stats_by_user_filtered(
        self,
        user_id: int,
        *,
        min_score: Optional[float] = None,
        max_score: Optional[float] = None,
        min_distance: Optional[float] = None,
        max_distance: Optional[float] = None,
        worth_applying: Optional[bool] = None,
        applied: Optional[bool] = None,
        search_profile_id: Optional[int] = None,
    ) -> dict:
        """Get aggregate stats for filtered jobs."""
        
        q = self._build_filter_query(
            user_id,
            min_score=min_score,
            max_score=max_score,
            min_distance=min_distance,
            max_distance=max_distance,
            worth_applying=worth_applying,
            applied=applied,
            search_profile_id=search_profile_id,
        )
        
        # Use case() to count applied jobs, which is universally supported by SQLAlchemy dialects
        stats = q.with_entities(
            func.sum(case((self.model.applied == True, 1), else_=0)),
            func.avg(self.model.affinity_score)
        ).first()
        
        applied_count = stats[0] if stats and stats[0] else 0
        avg_score = stats[1] if stats and stats[1] else 0.0
        
        return {
            "total_applied": int(applied_count),
            "avg_score": float(avg_score)
        }
