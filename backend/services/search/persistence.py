from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Sequence

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models import Job, ScrapedJob
from backend.repositories.job_repository import JobRepository
from backend.services.search.listing_utils import (
    bootstrap_normalized_job_data,
    compute_posting_quality,
    extract_company_name,
    extract_listing_description_text,
    extract_listing_location_string,
    extract_listing_workload_string,
    parse_listing_publication_date,
)
from backend.services.utils import clean_html_tags, haversine_distance

logger = logging.getLogger(__name__)

NormalizeJobBatch = Callable[[List[Dict[str, Any]]], Awaitable[List[Dict[str, Any]]]]
UpsertScrapedJob = Callable[[Any], tuple[ScrapedJob, bool]]
GeocodeLocation = Callable[[str], Awaitable[Any]]
IncrementStatusErrors = Callable[[int, int], int]
BootstrapNormalizedJobData = Callable[..., Dict[str, Any]]
ExtractListingText = Callable[[Any], str]
ParseListingPublicationDate = Callable[[Any, str, str], Any]
ReportRefinedAnalysisProgress = Callable[[int, str], None]


@dataclass(frozen=True)
class CatalogPersistenceResult:
    created: int = 0
    updated: int = 0
    failed: int = 0
    conflict_recoveries: int = 0


class SearchPipelinePersistence:
    """Persistence collaborator for the search pipeline.

    SearchService keeps orchestration responsibilities while this class owns the
    catalog/user-job persistence and normalization mutation details.
    """

    def __init__(self, db: Session, job_repo: JobRepository):
        self.db = db
        self.job_repo = job_repo

    @staticmethod
    def _estimate_normalize_candidate_chars(candidate: Dict[str, Any]) -> int:
        return (
            len(str(candidate.get("title") or ""))
            + len(str(candidate.get("company") or ""))
            + len(str(candidate.get("location") or ""))
            + len(str(candidate.get("workload") or ""))
            + len(str(candidate.get("description") or ""))
            + 64
        )

    @classmethod
    def _pack_normalize_candidates(
        cls,
        candidates: Sequence[Dict[str, Any]],
    ) -> List[List[Dict[str, Any]]]:
        if not candidates:
            return []

        max_items = max(1, int(settings.NORMALIZE_BATCH_SIZE or 1))
        prompt_budget = max(1, int(settings.NORMALIZE_PROMPT_TARGET_CHARS or 1))
        packed: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        current_chars = 0

        for candidate in candidates:
            candidate_chars = max(1, cls._estimate_normalize_candidate_chars(candidate))
            if current and (
                len(current) >= max_items or current_chars + candidate_chars > prompt_budget
            ):
                packed.append(current)
                current = []
                current_chars = 0

            current.append(candidate)
            current_chars += candidate_chars

        if current:
            packed.append(current)

        return packed

    @staticmethod
    def _listing_application_field(listing: Any, field_name: str) -> Any:
        application = getattr(listing, "application", None)
        if application is None:
            return None
        if isinstance(application, dict):
            return application.get(field_name)
        return getattr(application, field_name, None)

    def upsert_scraped_job(
        self,
        listing: Any,
        *,
        bootstrap_normalized_job_data_fn: BootstrapNormalizedJobData = bootstrap_normalized_job_data,
        extract_listing_description_text_fn: ExtractListingText = extract_listing_description_text,
        extract_company_name_fn: ExtractListingText = extract_company_name,
        extract_listing_location_string_fn: ExtractListingText = extract_listing_location_string,
        extract_listing_workload_string_fn: ExtractListingText = extract_listing_workload_string,
        parse_listing_publication_date_fn: ParseListingPublicationDate = parse_listing_publication_date,
    ) -> tuple[ScrapedJob, bool]:
        platform = getattr(listing, "source", None) or getattr(listing, "platform", "unknown")
        platform_id = str(getattr(listing, "id", "") or getattr(listing, "platform_job_id", ""))

        existing_sj = self.job_repo.get_scraped_job_by_platform_and_id(platform, platform_id)

        desc_text = extract_listing_description_text_fn(listing)
        company_name = extract_company_name_fn(listing) or "Unknown"
        location_str = extract_listing_location_string_fn(listing)
        workload_str = extract_listing_workload_string_fn(listing)
        pub_date = parse_listing_publication_date_fn(listing, platform, platform_id)
        normalized_bootstrap = bootstrap_normalized_job_data_fn(
            listing,
            desc_text=desc_text,
            company_name=company_name,
            location_str=location_str,
        )
        application_url = self._listing_application_field(listing, "form_url")
        application_email = self._listing_application_field(listing, "email")

        created = False
        recovered_catalog_conflict = False
        if not existing_sj:
            new_sj = ScrapedJob(
                platform=platform,
                platform_job_id=platform_id,
                title=clean_html_tags(getattr(listing, "title", "Unknown")),
                company=company_name,
                description=clean_html_tags(desc_text) if desc_text else None,
                location=location_str,
                external_url=getattr(listing, "external_url", None)
                or getattr(listing, "url", None)
                or platform_id,
                application_url=application_url,
                application_email=application_email,
                workload=workload_str or None,
                publication_date=pub_date,
                source_query=getattr(listing, "_source_query", "Unknown"),
                **normalized_bootstrap,
            )
            created_ok = self.job_repo.create_scraped_job_nested(new_sj)
            if created_ok:
                existing_sj = new_sj
                created = True
            else:
                recovered_catalog_conflict = True
                existing_sj = self.job_repo.get_scraped_job_by_platform_and_id(
                    platform, platform_id
                )
        else:
            refresh_fields = {
                "description": clean_html_tags(desc_text) if desc_text else None,
                "location": location_str or None,
                "application_url": application_url,
                "application_email": application_email,
                "workload": workload_str or None,
                "publication_date": pub_date,
                "source_query": getattr(listing, "_source_query", None),
            }
            for field, value in refresh_fields.items():
                if getattr(existing_sj, field, None) is None and value is not None:
                    setattr(existing_sj, field, value)

            for field, value in normalized_bootstrap.items():
                if getattr(existing_sj, field, None) is None and value is not None:
                    setattr(existing_sj, field, value)
            if not existing_sj.normalization_status:
                existing_sj.normalization_status = "provider_bootstrap"

        setattr(listing, "_scraped_job_id", existing_sj.id)
        setattr(listing, "_normalized_job_data", existing_sj.normalized_job_data)
        setattr(listing, "_catalog_conflict_recovered", recovered_catalog_conflict)
        setattr(listing, "_catalog_persisted", True)
        setattr(listing, "_catalog_persist_error", None)
        return existing_sj, created

    def persist_scraped_job_catalog(
        self,
        jobs: Sequence[Any],
        *,
        upsert_scraped_job: UpsertScrapedJob,
    ) -> CatalogPersistenceResult:
        if not jobs:
            return CatalogPersistenceResult()

        created = 0
        updated = 0
        failed = 0
        conflict_recoveries = 0
        for listing in jobs:
            setattr(listing, "_catalog_persisted", False)
            setattr(listing, "_catalog_persist_error", None)

        try:
            for listing in jobs:
                savepoint = self.db.begin_nested()
                try:
                    _, was_created = upsert_scraped_job(listing)
                    savepoint.commit()
                    if getattr(listing, "_catalog_conflict_recovered", False):
                        conflict_recoveries += 1
                    if was_created:
                        created += 1
                    else:
                        updated += 1
                except Exception as exc:
                    failed += 1
                    savepoint.rollback()
                    setattr(listing, "_catalog_persisted", False)
                    setattr(listing, "_catalog_persist_error", str(exc))
                    logger.warning("Failed to persist scraped job catalog entry: %s", exc)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return CatalogPersistenceResult(
            created=created,
            updated=updated,
            failed=failed,
            conflict_recoveries=conflict_recoveries,
        )

    async def normalize_persisted_jobs(
        self,
        profile_id: int,
        jobs: Sequence[Any],
        *,
        normalize_job_batch: NormalizeJobBatch,
    ) -> int:
        if not jobs:
            return 0

        candidates: List[Dict[str, Any]] = []
        candidate_records: List[ScrapedJob] = []

        all_scraped_ids = [getattr(listing, "_scraped_job_id", None) for listing in jobs]
        all_scraped_ids = [sid for sid in all_scraped_ids if sid is not None]
        scraped_jobs_by_id: Dict[int, ScrapedJob] = {}
        if all_scraped_ids:
            batch = self.job_repo.get_scraped_jobs_by_ids(all_scraped_ids)
            scraped_jobs_by_id = {sj.id: sj for sj in batch}

        for listing in jobs:
            scraped_job_id = getattr(listing, "_scraped_job_id", None)
            if not scraped_job_id:
                continue
            scraped_job = scraped_jobs_by_id.get(scraped_job_id)
            if not scraped_job:
                continue
            if scraped_job.normalization_status not in {None, "", "pending", "provider_bootstrap"}:
                setattr(listing, "_normalized_job_data", scraped_job.normalized_job_data)
                continue

            candidates.append(
                {
                    "title": scraped_job.title,
                    "company": scraped_job.company,
                    "location": scraped_job.location,
                    "workload": scraped_job.workload,
                    "description": scraped_job.description,
                }
            )
            candidate_records.append(scraped_job)

        if not candidates:
            return 0

        normalized_rows: List[Dict[str, Any]] = []
        packed_chunks = self._pack_normalize_candidates(candidates)
        for chunk_index, chunk in enumerate(packed_chunks):
            chunk_start = sum(len(previous_chunk) for previous_chunk in packed_chunks[:chunk_index])
            try:
                chunk_result = await normalize_job_batch(chunk)
                normalized_rows.extend(chunk_result)
            except Exception as batch_err:
                logger.warning(
                    "[NORMALIZE] Batch %d-%d failed for profile %s, skipping chunk: %s",
                    chunk_start,
                    chunk_start + len(chunk) - 1,
                    profile_id,
                    batch_err,
                )
                normalized_rows.extend([{} for _ in chunk])

        upgraded = 0
        for scraped_job, normalized in zip(candidate_records, normalized_rows):
            if not normalized:
                scraped_job.normalization_status = "failed"
                fail_meta = scraped_job.normalized_metadata or {}
                fail_meta["normalization_failed_at"] = datetime.now(timezone.utc).isoformat()
                scraped_job.normalized_metadata = fail_meta
                continue
            scraped_job.normalization_status = "normalized"
            scraped_job.normalized_at = datetime.now(timezone.utc)
            scraped_job.normalization_source = "llm_normalizer"
            scraped_job.normalization_confidence = normalized.get("confidence")
            scraped_job.normalized_title = normalized.get("title")
            scraped_job.normalized_role_family = normalized.get("role_family")
            scraped_job.normalized_domain = normalized.get("domain")
            scraped_job.normalized_seniority = normalized.get("seniority")
            scraped_job.normalized_employment_mode = normalized.get("employment_mode")
            scraped_job.normalized_contract_type = normalized.get("contract_type")
            scraped_job.normalized_qualification_level = normalized.get("qualification_level")
            scraped_job.normalized_experience_min_years = normalized.get("experience_min_years")
            scraped_job.normalized_experience_max_years = normalized.get("experience_max_years")
            scraped_job.normalized_workload_min = normalized.get("workload_min")
            scraped_job.normalized_workload_max = normalized.get("workload_max")
            scraped_job.normalized_salary_min_chf = normalized.get("salary_min_chf")
            scraped_job.normalized_salary_max_chf = normalized.get("salary_max_chf")
            scraped_job.normalized_required_languages = normalized.get("required_languages") or None
            scraped_job.normalized_required_skills = normalized.get("required_skills") or None
            scraped_job.normalized_education_levels = normalized.get("education_levels") or None
            scraped_job.normalized_key_requirements = normalized.get("key_requirements") or None
            scraped_job.normalized_preferred_skills = normalized.get("preferred_skills") or None
            scraped_job.normalized_soft_skills = normalized.get("soft_skills") or None
            scraped_job.normalized_physical_requirements = (
                normalized.get("physical_requirements") or None
            )
            scraped_job.normalized_entry_barrier = normalized.get("entry_barrier")
            scraped_job.normalized_career_changer_friendly = normalized.get(
                "career_changer_friendly"
            )
            scraped_job.normalized_hard_blockers = normalized.get("hard_blockers") or None

            metadata = scraped_job.normalized_metadata or {}
            metadata.update({"llm_normalized": True, "source": "llm_normalizer"})
            scraped_job.normalized_metadata = metadata

            if scraped_job.posting_quality is None and scraped_job.description:
                try:
                    scraped_job.posting_quality = compute_posting_quality(scraped_job.description)
                except Exception:
                    pass

            upgraded += 1

        self.db.commit()

        for listing in jobs:
            scraped_job_id = getattr(listing, "_scraped_job_id", None)
            if not scraped_job_id:
                continue
            scraped_job = scraped_jobs_by_id.get(scraped_job_id)
            if scraped_job:
                setattr(listing, "_normalized_job_data", scraped_job.normalized_job_data)

        return upgraded

    async def save_single_job(
        self,
        listing: Any,
        analysis: Dict[str, Any],
        profile_dict: Dict[str, Any],
        origin_coords: tuple[float, float] | None,
        *,
        upsert_scraped_job: UpsertScrapedJob,
        geocode_location_fn: GeocodeLocation,
        commit: bool = True,
    ) -> None:
        platform = getattr(listing, "source", None) or getattr(listing, "platform", "unknown")
        platform_id = str(getattr(listing, "id", "") or getattr(listing, "platform_job_id", ""))

        existing_sj, _ = upsert_scraped_job(listing)

        location_str = extract_listing_location_string(listing)

        distance_km = None
        if origin_coords and getattr(listing, "location", None):
            coords = getattr(listing.location, "coordinates", None)
            if not coords and location_str:
                coords = await geocode_location_fn(location_str)
                if coords:
                    logger.info(
                        "Resolved missing coordinates for %s via geocoding fallback", location_str
                    )
                else:
                    logger.warning(
                        "Could not resolve coordinates for %s/%s with location %r",
                        platform,
                        platform_id,
                        location_str,
                    )

            if coords:
                distance_km = haversine_distance(
                    origin_coords[0], origin_coords[1], coords.lat, coords.lon
                )

        analysis_fields = {
            "affinity_score": analysis.get("affinity_score", 0),
            "affinity_analysis": analysis.get("affinity_analysis", ""),
            "worth_applying": analysis.get("worth_applying", False),
            "distance_km": distance_km,
            "skill_match_score": analysis.get("skill_match_score"),
            "experience_match_score": analysis.get("experience_match_score"),
            "intent_match_score": analysis.get("intent_match_score"),
            "language_match_score": analysis.get("language_match_score"),
            "location_match_score": analysis.get("location_match_score"),
            "transferability_score": analysis.get("transferability_score"),
            "qualification_gap_score": analysis.get("qualification_gap_score"),
            "analysis_structured": analysis.get("analysis_structured"),
            "red_flags": analysis.get("red_flags"),
        }
        existing_job = self.job_repo.get_job_by_user_scraped_profile(
            profile_dict["user_id"],
            existing_sj.id,
            profile_dict.get("id"),
        )
        if existing_job:
            for field, value in analysis_fields.items():
                setattr(existing_job, field, value)
        else:
            new_job = Job(
                user_id=profile_dict["user_id"],
                search_profile_id=profile_dict.get("id"),
                scraped_job_id=existing_sj.id,
                applied=False,
                **analysis_fields,
            )
            created_ok = self.job_repo.create_job_nested(new_job)
            if not created_ok:
                existing_job = self.job_repo.get_job_by_user_scraped_profile(
                    profile_dict["user_id"],
                    existing_sj.id,
                    profile_dict.get("id"),
                )
                if existing_job:
                    for field, value in analysis_fields.items():
                        setattr(existing_job, field, value)
                else:
                    raise
        if commit:
            try:
                self.db.commit()
            except Exception as exc:
                self.db.rollback()
                logger.error(
                    "Failed to persist job %s/%s for profile %s: %s",
                    platform,
                    platform_id,
                    profile_dict.get("id"),
                    exc,
                )
                raise

    def apply_refined_analysis_updates(
        self,
        profile_id: int,
        profile_dict: Dict[str, Any],
        jobs_to_refine: Sequence[tuple[Any, Dict[str, Any]]],
        *,
        increment_status_errors: IncrementStatusErrors,
        report_progress: ReportRefinedAnalysisProgress | None = None,
    ) -> int:
        updated_count = 0
        for current_index, (job, analysis) in enumerate(jobs_to_refine, start=1):
            if report_progress is not None:
                report_progress(current_index, getattr(job, "title", "Unknown"))
            scraped_job_id = getattr(job, "_scraped_job_id", None)
            if scraped_job_id is None:
                continue
            try:
                existing_job = self.job_repo.get_job_by_user_scraped_profile(
                    profile_dict["user_id"],
                    scraped_job_id,
                    profile_dict.get("id"),
                )
                if not existing_job:
                    continue
                existing_job.affinity_score = analysis.get(
                    "affinity_score", existing_job.affinity_score
                )
                existing_job.affinity_analysis = analysis.get(
                    "affinity_analysis", existing_job.affinity_analysis
                )
                existing_job.worth_applying = analysis.get(
                    "worth_applying", existing_job.worth_applying
                )
                existing_job.skill_match_score = analysis.get(
                    "skill_match_score", existing_job.skill_match_score
                )
                existing_job.experience_match_score = analysis.get(
                    "experience_match_score", existing_job.experience_match_score
                )
                existing_job.intent_match_score = analysis.get(
                    "intent_match_score", existing_job.intent_match_score
                )
                existing_job.language_match_score = analysis.get(
                    "language_match_score", existing_job.language_match_score
                )
                existing_job.location_match_score = analysis.get(
                    "location_match_score", existing_job.location_match_score
                )
                existing_job.transferability_score = analysis.get(
                    "transferability_score", existing_job.transferability_score
                )
                existing_job.qualification_gap_score = analysis.get(
                    "qualification_gap_score", existing_job.qualification_gap_score
                )
                existing_job.analysis_structured = analysis.get(
                    "analysis_structured", existing_job.analysis_structured
                )
                existing_job.red_flags = analysis.get("red_flags", existing_job.red_flags)
                self.db.commit()
                updated_count += 1
            except Exception as exc:
                self.db.rollback()
                increment_status_errors(profile_id, 1)
                logger.warning(
                    "Final-pass update failed for scraped_job_id %s (profile %s): %s",
                    scraped_job_id,
                    profile_dict.get("id"),
                    exc,
                )
        return updated_count
