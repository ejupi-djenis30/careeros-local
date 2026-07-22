from typing import Dict, List, Optional, Sequence, Tuple, cast

from sqlalchemy import asc, case, desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import Job, ScrapedJob
from backend.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    def __init__(self, db: Session):
        super().__init__(Job, db)

    def get_user_job_identifiers(self, user_id: int) -> List[Tuple[str, str, str, str, str]]:
        """Returns lightweight tuples of (platform, platform_job_id, external_url, title, company) for all user jobs."""
        rows = (
            self.db.query(
                ScrapedJob.platform,
                ScrapedJob.platform_job_id,
                ScrapedJob.external_url,
                ScrapedJob.title,
                ScrapedJob.company,
            )
            .join(self.model.scraped_job)
            .filter(self.model.user_id == user_id)
            .all()
        )
        return [cast(Tuple[str, str, str, str, str], tuple(row)) for row in rows]

    def get_profile_job_identifiers(self, profile_id: int) -> List[Tuple[str, str, str, str, str]]:
        """Returns lightweight tuples of (platform, platform_job_id, external_url, title, company) for jobs in a specific profile."""
        rows = (
            self.db.query(
                ScrapedJob.platform,
                ScrapedJob.platform_job_id,
                ScrapedJob.external_url,
                ScrapedJob.title,
                ScrapedJob.company,
            )
            .join(self.model.scraped_job)
            .filter(self.model.search_profile_id == profile_id)
            .all()
        )
        return [cast(Tuple[str, str, str, str, str], tuple(row)) for row in rows]

    def get_applied_scraped_job_ids(self, user_id: int) -> set:
        """Return a set of scraped_job_id values where user has applied=True.

        Used by Feature 2 to populate the `applied_elsewhere` badge:
        any job whose ScrapedJob is in this set but whose own `applied` flag
        is False was applied in a different search profile.
        """
        rows = (
            self.db.query(self.model.scraped_job_id)
            .filter(
                self.model.user_id == user_id,
                self.model.applied.is_(True),
            )
            .all()
        )
        return {row[0] for row in rows}

    def get_scraped_job_by_platform_and_id(
        self, platform: str, platform_job_id: str
    ) -> Optional[ScrapedJob]:
        return (
            self.db.query(ScrapedJob)
            .filter(
                ScrapedJob.platform == platform,
                ScrapedJob.platform_job_id == platform_job_id,
            )
            .first()
        )

    def get_scraped_jobs_by_ids(self, scraped_job_ids: Sequence[int]) -> List[ScrapedJob]:
        if not scraped_job_ids:
            return []
        return self.db.query(ScrapedJob).filter(ScrapedJob.id.in_(scraped_job_ids)).all()

    def get_applied_scraped_pairs(
        self,
        platform_to_ids: Dict[str, Sequence[str]],
        applied_scraped_ids: set,
    ) -> Dict[Tuple[str, str], int]:
        if not platform_to_ids or not applied_scraped_ids:
            return {}

        out: Dict[Tuple[str, str], int] = {}
        for platform_name, platform_ids in platform_to_ids.items():
            if not platform_ids:
                continue
            rows = (
                self.db.query(ScrapedJob.id, ScrapedJob.platform, ScrapedJob.platform_job_id)
                .filter(
                    ScrapedJob.platform == platform_name,
                    ScrapedJob.platform_job_id.in_(platform_ids),
                )
                .all()
            )
            for sj_id, sj_platform, sj_platform_id in rows:
                if sj_id in applied_scraped_ids:
                    out[(sj_platform, sj_platform_id)] = sj_id
        return out

    def create_scraped_job_nested(self, scraped_job: ScrapedJob) -> bool:
        savepoint = self.db.begin_nested()
        try:
            self.db.add(scraped_job)
            savepoint.commit()
            return True
        except IntegrityError:
            savepoint.rollback()
            return False

    def get_job_by_user_scraped_profile(
        self,
        user_id: int,
        scraped_job_id: int,
        search_profile_id: Optional[int],
    ) -> Optional[Job]:
        return (
            self.db.query(Job)
            .filter(
                Job.user_id == user_id,
                Job.scraped_job_id == scraped_job_id,
                Job.search_profile_id == search_profile_id,
            )
            .first()
        )

    def get_jobs_with_scraped_job_for_user(self, user_id: int) -> List[Job]:
        return (
            self.db.query(self.model)
            .join(self.model.scraped_job)
            .filter(self.model.user_id == user_id)
            .all()
        )

    def get_salary_benchmark_values(
        self,
        domain: str,
        seniority: Optional[str] = None,
    ) -> List[int]:
        query = self.db.query(ScrapedJob.normalized_salary_max_chf).filter(
            ScrapedJob.normalized_salary_max_chf.isnot(None),
            ScrapedJob.normalized_domain == domain,
        )
        if seniority:
            query = query.filter(ScrapedJob.normalized_seniority == seniority)

        rows = query.all()
        return [row[0] for row in rows if row[0] and row[0] > 0]

    def create_job_nested(self, job: Job) -> bool:
        savepoint = self.db.begin_nested()
        try:
            self.db.add(job)
            savepoint.commit()
            return True
        except IntegrityError:
            savepoint.rollback()
            return False

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
        include_dismissed: Optional[bool] = None,
    ):
        q = self.db.query(self.model).filter(
            self.model.user_id == user_id,
        )

        if not include_dismissed:
            q = q.filter(self.model.dismissed.is_not(True))

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
        include_dismissed: Optional[bool] = None,
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
            include_dismissed=include_dismissed,
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

    def get_trust_candidates_by_user(
        self,
        user_id: int,
        *,
        min_distance: Optional[float] = None,
        max_distance: Optional[float] = None,
        applied: Optional[bool] = None,
        search_profile_id: Optional[int] = None,
        include_dismissed: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> List[Job]:
        """Return the full non-analysis-filtered scope for receipt-aware queries.

        Match scores and recommendations cannot be trusted in SQL alone: their receipt,
        current profile, listing evidence, and exact model row must all be validated in the
        service.  This query therefore applies only ordinary database-owned filters and never
        paginates before that validation has happened.
        """
        q = self._build_filter_query(
            user_id,
            min_distance=min_distance,
            max_distance=max_distance,
            applied=applied,
            search_profile_id=search_profile_id,
            include_dismissed=include_dismissed,
        )

        allowed_sort = {
            "created_at": self.model.created_at,
            "distance_km": self.model.distance_km,
        }
        # Affinity ordering is performed only after full receipt validation.  A stable,
        # non-analysis order here also determines the placement of untrusted rows at the end.
        effective_sort = "created_at" if sort_by == "affinity_score" else sort_by
        col = allowed_sort.get(effective_sort, self.model.created_at)
        if effective_sort in ["title", "publication_date"]:
            q = q.join(self.model.scraped_job)
            col = getattr(ScrapedJob, effective_sort)

        order_fn = desc if sort_order == "desc" else asc
        return q.order_by(order_fn(col), order_fn(self.model.id)).all()

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
        include_dismissed: Optional[bool] = None,
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
            include_dismissed=include_dismissed,
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
        include_dismissed: Optional[bool] = None,
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
            include_dismissed=include_dismissed,
        )

        stats = q.with_entities(
            func.sum(case((self.model.applied.is_(True), 1), else_=0)),
            func.avg(self.model.affinity_score),
        ).first()

        applied_count = stats[0] if stats and stats[0] else 0
        avg_score = stats[1] if stats and stats[1] else 0.0

        return {"total_applied": int(applied_count), "avg_score": float(avg_score)}

    def get_count_and_stats_by_user_filtered(
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
        include_dismissed: Optional[bool] = None,
    ) -> dict:
        """Return total count, total_applied, and avg_score in a single query."""
        q = self._build_filter_query(
            user_id,
            min_score=min_score,
            max_score=max_score,
            min_distance=min_distance,
            max_distance=max_distance,
            worth_applying=worth_applying,
            applied=applied,
            search_profile_id=search_profile_id,
            include_dismissed=include_dismissed,
        )

        row = q.with_entities(
            func.count(self.model.id),
            func.sum(case((self.model.applied.is_(True), 1), else_=0)),
            func.avg(self.model.affinity_score),
        ).first()

        total = int(row[0]) if row and row[0] else 0
        applied_count = int(row[1]) if row and row[1] else 0
        avg_score = float(row[2]) if row and row[2] else 0.0

        return {"total": total, "total_applied": applied_count, "avg_score": avg_score}
