import hashlib
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.ai.attestation import MatchAttestationError, validate_match_attestation
from backend.ai.match_evidence import (
    candidate_evidence_document,
    job_evidence_document,
    match_input_fingerprint,
    match_quote_bindings,
)
from backend.ai.match_policy import DIMENSION_SCORE_FIELDS, materialize_match_citations
from backend.ai.models import AIExecution
from backend.repositories.job_repository import JobRepository
from backend.repositories.profile_repository import ProfileRepository
from backend.schemas import JobCreate, JobUpdate


class JobService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = JobRepository(db)
        self.profile_repo = ProfileRepository(db)

    @staticmethod
    def _analysis_is_verified(job: Any) -> bool:
        return getattr(job, "_analysis_receipt_verified", False) is True

    def _validate_and_mark_analysis_receipt(
        self,
        job: Any,
        user_id: int,
        execution: AIExecution | None,
    ) -> Any:
        try:
            profile = job.search_profile
            listing = job.scraped_job
            if profile is None or listing is None:
                raise MatchAttestationError("analysis source records are missing")
            row_index = job.analysis_execution_row_index
            if isinstance(row_index, bool) or not isinstance(row_index, int):
                raise MatchAttestationError("analysis row index is missing")
            candidate_evidence = candidate_evidence_document(
                {
                    "cv_content": profile.cv_content,
                    "role_description": profile.role_description,
                    "search_strategy": profile.search_strategy,
                }
            )
            job_evidence = job_evidence_document(
                {
                    "title": listing.title,
                    "company": listing.company,
                    "location": listing.location,
                    "workload": listing.workload,
                    "description": listing.description,
                },
                row_index,
                description_limit=1800,
            )
            expected_input_fingerprint = match_input_fingerprint(candidate_evidence, job_evidence)
            expected_citations = materialize_match_citations(
                candidate=candidate_evidence,
                job=job_evidence,
                dimension_scores={
                    dimension: (
                        int(value)
                        if isinstance((value := getattr(job, field, None)), (int, float))
                        and not isinstance(value, bool)
                        else 50
                    )
                    for dimension, field in DIMENSION_SCORE_FIELDS.items()
                },
            )
            validate_match_attestation(
                job,
                execution,
                expected_user_id=user_id,
                expected_input_fingerprint=expected_input_fingerprint,
                expected_quote_bindings=match_quote_bindings(candidate_evidence, job_evidence),
                expected_citations=expected_citations,
            )
            job._analysis_receipt_verified = True
        except MatchAttestationError:
            job._analysis_receipt_verified = False
        return job

    def _mark_analysis_receipt(self, job: Any, user_id: int) -> Any:
        execution_id = getattr(job, "analysis_execution_id", None)
        execution = self.db.get(AIExecution, execution_id) if execution_id else None
        return self._validate_and_mark_analysis_receipt(job, user_id, execution)

    def _mark_analysis_receipts(self, jobs: list[Any], user_id: int) -> None:
        execution_ids = {
            execution_id
            for job in jobs
            if isinstance((execution_id := getattr(job, "analysis_execution_id", None)), str)
            and execution_id
        }
        executions = (
            self.db.query(AIExecution).filter(AIExecution.id.in_(execution_ids)).all()
            if execution_ids
            else []
        )
        executions_by_id = {execution.id: execution for execution in executions}
        for job in jobs:
            execution_id = getattr(job, "analysis_execution_id", None)
            self._validate_and_mark_analysis_receipt(
                job,
                user_id,
                executions_by_id.get(execution_id) if isinstance(execution_id, str) else None,
            )

    @classmethod
    def _apply_trusted_analysis_filters(
        cls,
        jobs: list[Any],
        filters: Dict[str, Any],
    ) -> list[Any]:
        min_score = filters.get("min_score")
        max_score = filters.get("max_score")
        worth_applying = filters.get("worth_applying")
        analysis_filter_requested = any(
            value is not None for value in (min_score, max_score, worth_applying)
        )
        if not analysis_filter_requested:
            return jobs

        filtered: list[Any] = []
        for job in jobs:
            if not cls._analysis_is_verified(job):
                continue
            score = float(job.affinity_score)
            if min_score is not None and score < float(min_score):
                continue
            if max_score is not None and score > float(max_score):
                continue
            if worth_applying is not None and job.worth_applying is not worth_applying:
                continue
            filtered.append(job)
        return filtered

    @classmethod
    def _sort_by_trusted_affinity(
        cls,
        jobs: list[Any],
        sort_order: str,
    ) -> list[Any]:
        trusted = [job for job in jobs if cls._analysis_is_verified(job)]
        untrusted = [job for job in jobs if not cls._analysis_is_verified(job)]
        trusted.sort(
            key=lambda job: (float(job.affinity_score), int(job.id)),
            reverse=sort_order == "desc",
        )
        # Untrusted rows remain visible as unanalyzed jobs, but their raw score can never
        # move them ahead of a receipt-verified result or change their relative order.
        return [*trusted, *untrusted]

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
        candidates = self.repo.get_trust_candidates_by_user(
            user_id,
            min_distance=filters.get("min_distance"),
            max_distance=filters.get("max_distance"),
            applied=filters.get("applied"),
            search_profile_id=filters.get("search_profile_id"),
            include_dismissed=filters.get("include_dismissed"),
            sort_by=filters.get("sort_by", "created_at"),
            sort_order=filters.get("sort_order", "desc"),
        )
        self._mark_analysis_receipts(candidates, user_id)
        filtered = self._apply_trusted_analysis_filters(candidates, filters)
        if filters.get("sort_by") == "affinity_score":
            filtered = self._sort_by_trusted_affinity(
                filtered,
                filters.get("sort_order", "desc"),
            )

        trusted_scores = [
            float(item.affinity_score) for item in filtered if self._analysis_is_verified(item)
        ]
        total = len(filtered)
        total_applied = sum(1 for item in filtered if item.applied is True)
        avg_score = sum(trusted_scores) / len(trusted_scores) if trusted_scores else 0.0
        skip = (page - 1) * page_size
        items = filtered[skip : skip + page_size]

        # Feature 2: populate applied_elsewhere badge
        # Get all ScrapedJob IDs where this user has applied=True (across all profiles)
        applied_scraped_ids = set()
        if items:
            applied_scraped_ids = self.repo.get_applied_scraped_job_ids(user_id)

        # Attach applied_elsewhere as a Python attribute so Pydantic can read it
        for item in items:
            item.applied_elsewhere = not item.applied and item.scraped_job_id in applied_scraped_ids

        return {
            "items": items,
            "total": total,
            "page": page,
            "pages": (total + page_size - 1) // page_size,
            "total_applied": total_applied,
            "avg_score": avg_score,
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
            return self._mark_analysis_receipt(existing_job, user_id)

        # Create the user-specific Job record
        job_data = {
            "user_id": user_id,
            "scraped_job_id": scraped_job.id,
            "applied": job_dict.get("applied", False),
            "search_profile_id": profile_id,
            "source_query": job_dict.get("source_query"),
        }
        return self._mark_analysis_receipt(self.repo.create(job_data), user_id)

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

        return self._mark_analysis_receipt(result, user_id)

    def record_view(self, user_id: int, job_id: int):
        """Idempotently record the first time a user views a job's analysis."""
        job = self.repo.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        if job.viewed_at is None:
            self.repo.update(job, {"viewed_at": datetime.now(timezone.utc)})
        return self._mark_analysis_receipt(job, user_id)

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
