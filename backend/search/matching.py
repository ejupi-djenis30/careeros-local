# ruff: noqa: F401

"""Focused domain slice of the local job-search pipeline."""

import asyncio
import inspect
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models import ScrapedJob, SearchProfile
from backend.providers.circuit_breaker import CircuitOpenError
from backend.providers.jobs.jobroom.client import JobRoomProvider
from backend.providers.jobs.swissdevjobs.client import SwissDevJobsProvider
from backend.repositories.job_repository import JobRepository
from backend.repositories.profile_repository import ProfileRepository
from backend.search.normalization.listings import (
    bootstrap_normalized_job_data,
    coerce_int,
    coerce_string_list,
    extract_company_name,
    extract_listing_description_text,
    extract_listing_location_string,
    extract_listing_workload_string,
    extract_salary_max_chf,
    listing_description_fingerprint,
    listing_fuzzy_key,
    listing_identity_key,
    listing_is_remote,
    listing_url_token,
    normalize_listing_identifier,
    parse_listing_publication_date,
)
from backend.services.llm_service import llm_service
from backend.services.search.matching_engine import SearchNormalizationFilterEngine
from backend.services.search.persistence import SearchPipelinePersistence
from backend.services.search.prompt_compaction import (
    build_profile_match_snapshot,
    build_profile_normalization_fingerprint,
    compact_prompt_text,
)
from backend.services.search.search_validator import build_search_request
from backend.services.utils import (
    geocode_location,
    haversine_distance,
)

try:
    from backend.providers.jobs.adecco.client import AdeccoProvider
except ImportError:
    AdeccoProvider = None
from backend.providers.jobs.jobroom.avam_mapper import avam_mapper
from backend.providers.jobs.localdb.client import LocalDbProvider
from backend.providers.jobs.models import (
    JobSearchRequest,
)
from backend.services.search.profile_preferences import get_profile_preference
from backend.services.search.query_contracts import (
    build_plan_cache_payload,
    compute_plan_input_fingerprint,
    exact_query_fingerprint,
    is_cached_plan_compatible,
    normalize_domain,
    normalize_language,
    normalize_search_item,
    route_provider_names,
    supported_request_language,
    unpack_plan_cache_payload,
)
from backend.services.search_status import (
    add_log,
    get_status,
    init_status,
    register_task,
    release_task,
    unregister_task,
    update_status,
)

logger = logging.getLogger(__name__)


STOP_STATES = {"stopped", "cancelled", "finished", "failed"}


# ─────────────────────── Domain Router ───────────────────────


def get_compatible_providers(
    query_domain: str,
    providers: Dict[str, Any],
    provider_infos: Dict[str, Any],
) -> List[str]:
    return route_provider_names({"domain": query_domain}, providers, provider_infos)


class MatchingMixin:
    @staticmethod
    def _estimate_analysis_metadata_chars(metadata: Dict[str, Any]) -> int:
        normalized_data = metadata.get("normalized_data") or {}
        languages = metadata.get("languages") or []

        def estimate_value_chars(value: Any) -> int:
            if value is None:
                return 0
            if isinstance(value, dict):
                return sum(
                    len(str(key)) + estimate_value_chars(item) for key, item in value.items()
                )
            if isinstance(value, list):
                return sum(estimate_value_chars(item) for item in value)
            return len(str(value))

        return (
            len(str(metadata.get("title") or ""))
            + len(str(metadata.get("description") or ""))
            + len(str(metadata.get("location") or ""))
            + len(str(metadata.get("workload") or ""))
            + len(str(metadata.get("education") or ""))
            + len(str(metadata.get("company") or ""))
            + sum(len(str(language)) for language in languages)
            + estimate_value_chars(normalized_data)
            + 96
        )

    @staticmethod
    def _pack_entries_by_prompt_budget(
        entries: List[Any],
        *,
        max_items: int,
        prompt_char_budget: int,
        estimate_chars,
    ) -> List[List[Any]]:
        if not entries:
            return []

        normalized_max_items = max(1, int(max_items or 1))
        normalized_budget = max(1, int(prompt_char_budget or 1))
        packed: List[List[Any]] = []
        current: List[Any] = []
        current_chars = 0

        for entry in entries:
            entry_chars = max(1, int(estimate_chars(entry)))
            if current and (
                len(current) >= normalized_max_items
                or current_chars + entry_chars > normalized_budget
            ):
                packed.append(current)
                current = []
                current_chars = 0

            current.append(entry)
            current_chars += entry_chars

        if current:
            packed.append(current)

        return packed

    async def _build_analysis_job_metadata(self, job: Any) -> Dict[str, Any]:
        desc_text = ""
        descs = getattr(job, "descriptions", [])
        if descs:
            desc_text = (
                descs[0].description
                if hasattr(descs[0], "description")
                else (descs[0].get("description", "") if isinstance(descs[0], dict) else "")
            )
        desc_text = desc_text if isinstance(desc_text, str) else str(desc_text or "")

        education_info = []
        for occ in getattr(job, "occupations", []):
            if getattr(occ, "education_code", None):
                education_info.append(f"Edu: {occ.education_code}")

        company_obj = getattr(job, "company", None)
        company_name = company_obj.name if hasattr(company_obj, "name") else "Unknown"
        raw_norm = getattr(job, "_normalized_job_data", None) or {}
        if not isinstance(raw_norm, dict):
            raw_norm = {}
        normalized_data = {
            "domain": raw_norm.get("domain"),
            "role_type": raw_norm.get("role_type") or raw_norm.get("normalized_role_type"),
            "industry_sector": raw_norm.get("industry_sector")
            or raw_norm.get("normalized_industry_sector"),
            "seniority": raw_norm.get("seniority"),
            "qualification_level": raw_norm.get("qualification_level"),
            "required_skills": raw_norm.get("required_skills"),
            "preferred_skills": raw_norm.get("preferred_skills"),
            "experience_min_years": raw_norm.get("experience_min_years"),
            "experience_max_years": raw_norm.get("experience_max_years"),
            "required_languages": raw_norm.get("required_languages"),
            "entry_barrier": raw_norm.get("entry_barrier"),
            "career_changer_friendly": raw_norm.get("career_changer_friendly"),
            "hard_blockers": raw_norm.get("hard_blockers"),
            "education_levels": raw_norm.get("education_levels"),
            "key_requirements": raw_norm.get("key_requirements"),
            "physical_requirements": raw_norm.get("physical_requirements"),
            "soft_skills": raw_norm.get("soft_skills"),
        }

        return {
            "title": getattr(job, "title", "Unknown"),
            "description": desc_text,
            "location": job.location.city if getattr(job, "location", None) else "Unknown",
            "workload": (
                f"{job.employment.workload_min}-{job.employment.workload_max}%"
                if getattr(job, "employment", None)
                else "Unknown"
            ),
            "languages": (
                [
                    f"{s.language_code} ({s.spoken_level})"
                    for s in getattr(job, "language_skills", [])
                ]
                if getattr(job, "language_skills", None)
                else []
            ),
            "education": ", ".join(education_info) if education_info else "None specified",
            "company": company_name,
            "normalized_data": normalized_data,
        }

    def _pack_analysis_batches(
        self, jobs: List[Any], jobs_metadata: List[Dict[str, Any]]
    ) -> List[Any]:
        paired_entries = list(zip(jobs, jobs_metadata))
        runtime_policy = llm_service.get_step_runtime_policy("match")
        packed = self._pack_entries_by_prompt_budget(
            paired_entries,
            max_items=int(runtime_policy.get("batch_size") or settings.ANALYSIS_BATCH_SIZE or 1),
            prompt_char_budget=int(
                runtime_policy.get("prompt_budget_chars")
                or getattr(settings, "MATCH_PROMPT_TARGET_CHARS", 7000)
                or 7000
            ),
            estimate_chars=lambda entry: self._estimate_analysis_metadata_chars(entry[1]),
        )
        return [
            ([job for job, _ in batch], [metadata for _, metadata in batch]) for batch in packed
        ]

    async def _analyze_and_save(
        self, profile_id: int, profile_dict: dict, unique_jobs: list
    ) -> tuple[int, int]:
        status_data = get_status(profile_id)
        if status_data.get("state") in STOP_STATES:
            return 0, len(unique_jobs)

        # Legacy helper path used mainly by older tests and compatibility shims.
        # The main runtime pipeline performs critique/rerank in _finalize_and_save.
        # Keep this helper deterministic and self-contained unless a caller opts in.
        # Persisted match rows carry one auditable job_match attestation. Legacy refinement
        # passes remain disabled until they can store and validate a complete provenance chain.
        enable_refinement_passes = False

        semaphore = asyncio.Semaphore(settings.ANALYSIS_CONCURRENCY)
        jobs_metadata = [await self._build_analysis_job_metadata(job) for job in unique_jobs]
        batches = self._pack_analysis_batches(unique_jobs, jobs_metadata)

        origin_coords = None
        if profile_dict.get("latitude") and profile_dict.get("longitude"):
            origin_coords = (profile_dict["latitude"], profile_dict["longitude"])

        async def analyze_batch(batch_jobs, batch_metadata):
            async with semaphore:
                status_data = get_status(profile_id)
                if status_data.get("state") in ["stopped", "cancelled", "finished", "failed"]:
                    return []

                try:
                    results = await llm_service.analyze_job_batch(
                        batch_metadata,
                        profile_dict,
                        audit_db=self.db,
                        audit_user_id=profile_dict.get("user_id"),
                    )
                    return list(zip(batch_jobs, results))
                except Exception as e:
                    self._increment_status_errors(profile_id)
                    logger.warning(
                        "Required local-model analysis failed; no substitute result persisted: %s",
                        type(e).__name__,
                    )
                    add_log(
                        profile_id,
                        "Required local-model analysis failed for this batch; no heuristic "
                        "result was saved.",
                    )
                    return []

        tasks = [
            analyze_batch(batch_jobs, batch_metadata) for batch_jobs, batch_metadata in batches
        ]
        results = await asyncio.gather(*tasks)

        # Re-check cancellation: a stop/cancel request arriving during gather should
        # prevent us from persisting analysis results that are now unwanted.
        post_gather_status = get_status(profile_id)
        if post_gather_status.get("state") in STOP_STATES:
            add_log(profile_id, "Search was stopped during analysis — discarding results.")
            return 0, len(unique_jobs)

        jobs_to_persist = [item for batch_result in results for item in batch_result]

        # ── Phase 3.2: Two-pass critique for borderline scores ─────────────
        critique_enabled = enable_refinement_passes and getattr(
            settings, "MATCH_CRITIQUE_ENABLED", False
        )
        critique_min = int(getattr(settings, "MATCH_CRITIQUE_SCORE_RANGE_MIN", 40))
        critique_max = int(getattr(settings, "MATCH_CRITIQUE_SCORE_RANGE_MAX", 80))
        if critique_enabled and jobs_to_persist:
            borderline = [
                (i, job, analysis)
                for i, (job, analysis) in enumerate(jobs_to_persist)
                if critique_min <= analysis.get("affinity_score", 0) <= critique_max
            ]
            if borderline:
                try:
                    borderline_indices = [idx for idx, _, _ in borderline]
                    borderline_jobs_meta = []
                    for _, job, _ in borderline:
                        desc_text = ""
                        descs = getattr(job, "descriptions", [])
                        if descs:
                            desc_text = (
                                descs[0].description
                                if hasattr(descs[0], "description")
                                else (
                                    descs[0].get("description", "")
                                    if isinstance(descs[0], dict)
                                    else ""
                                )
                            )
                        raw_norm = getattr(job, "_normalized_job_data", None) or {}
                        borderline_jobs_meta.append(
                            {
                                "title": getattr(job, "title", "Unknown"),
                                "company": extract_company_name(job),
                                "description": desc_text,
                                "normalized_data": raw_norm,
                            }
                        )
                    borderline_analyses = [analysis for _, _, analysis in borderline]
                    critiqued = await llm_service.critique_job_batch(
                        borderline_jobs_meta, borderline_analyses, profile_dict
                    )
                    for orig_idx, critiqued_analysis in zip(borderline_indices, critiqued):
                        jobs_to_persist[orig_idx] = (
                            jobs_to_persist[orig_idx][0],
                            critiqued_analysis,
                        )
                    add_log(profile_id, f"Critique pass refined {len(borderline)} borderline jobs.")
                except Exception as exc:
                    logger.warning("[CRITIQUE] Critique pass failed: %s", exc)

        # ── Phase 3.4: Comparative re-ranking of top-N jobs ────────────────
        rerank_enabled = enable_refinement_passes and getattr(
            settings, "MATCH_RERANK_ENABLED", False
        )
        rerank_top_n = int(getattr(settings, "MATCH_RERANK_TOP_N", 20))
        if rerank_enabled and len(jobs_to_persist) >= 3:
            try:
                scored_with_index = sorted(
                    enumerate(jobs_to_persist),
                    key=lambda x: x[1][1].get("affinity_score", 0),
                    reverse=True,
                )[:rerank_top_n]
                top_entries = []
                for orig_idx, (job, analysis) in scored_with_index:
                    desc_text = ""
                    descs = getattr(job, "descriptions", [])
                    if descs:
                        desc_text = (
                            descs[0].description
                            if hasattr(descs[0], "description")
                            else (
                                descs[0].get("description", "")
                                if isinstance(descs[0], dict)
                                else ""
                            )
                        )
                    raw_norm = getattr(job, "_normalized_job_data", None) or {}
                    top_entries.append(
                        {
                            "job_index": orig_idx,
                            "current_score": analysis.get("affinity_score", 0),
                            "job_metadata": {
                                "title": getattr(job, "title", "Unknown"),
                                "company": extract_company_name(job),
                                "description": desc_text,
                                "normalized_data": raw_norm,
                            },
                        }
                    )
                reranked = await llm_service.rerank_top_jobs(top_entries, profile_dict)
                for rerank_result in reranked:
                    orig_idx = rerank_result.get("job_index", -1)
                    final_score = rerank_result.get("final_score")
                    if (
                        orig_idx >= 0
                        and final_score is not None
                        and 0 <= orig_idx < len(jobs_to_persist)
                    ):
                        job, analysis = jobs_to_persist[orig_idx]
                        updated = dict(analysis)
                        updated["affinity_score"] = final_score
                        updated["worth_applying"] = (
                            bool(analysis.get("worth_applying", False)) and final_score >= 65
                        )
                        jobs_to_persist[orig_idx] = (job, updated)
                add_log(profile_id, f"Re-ranked top {len(reranked)} jobs for calibration.")
            except Exception as exc:
                logger.warning("[RERANK] Re-rank pass failed: %s", exc)

        saved_count = 0
        # ── Phase 3.3: Deterministic salary_below_market red flag injection ──
        if enable_refinement_passes and getattr(settings, "SALARY_BENCHMARK_ENABLED", False):
            try:
                from backend.services.preference_service import compute_salary_benchmark

                for idx, (job, analysis) in enumerate(jobs_to_persist):
                    job_norm_data = getattr(job, "_normalized_job_data", None) or {}
                    job_salary_max = job_norm_data.get("salary_max_chf")
                    if not job_salary_max:
                        continue
                    benchmark = compute_salary_benchmark(
                        domain=job_norm_data.get("domain"),
                        seniority=job_norm_data.get("seniority"),
                        db=self.db,
                    )
                    if benchmark and benchmark["p25"] and job_salary_max < benchmark["p25"]:
                        updated = dict(analysis)
                        flags = list(updated.get("red_flags") or [])
                        if "salary_below_market" not in flags:
                            flags.append("salary_below_market")
                            updated["red_flags"] = flags
                            jobs_to_persist[idx] = (job, updated)
            except Exception:
                logger.debug("salary_below_market check skipped (non-critical)")

        for job, analysis in jobs_to_persist:
            try:
                await self._save_single_job(job, analysis, profile_dict, origin_coords, commit=True)
                saved_count += 1
            except Exception as exc:
                logger.warning(
                    "Skipping job due to persistence error (profile %s): %s",
                    profile_dict.get("id"),
                    exc,
                )

        skipped_count = len(unique_jobs) - saved_count
        return saved_count, skipped_count

    async def _run_analysis_batches(self, profile_id: int, profile_dict: dict, jobs: list) -> list:
        """Run LLM match analysis on a list of jobs using concurrent internal batches.

        Returns a list of (job_listing, analysis_dict) pairs.
        Critique, reranking, and salary benchmark are *not* applied here —
        they are handled once across all batches by _finalize_and_save.
        """
        # Clamp concurrency to prevent mass LLM timeouts that trip the circuit breaker
        safe_concurrency = max(1, int(settings.ANALYSIS_CONCURRENCY))
        semaphore = asyncio.Semaphore(safe_concurrency)
        jobs_metadata = [await self._build_analysis_job_metadata(job) for job in jobs]
        batches = self._pack_analysis_batches(jobs, jobs_metadata)

        async def analyze_batch(batch_jobs, batch_metadata):
            async with semaphore:
                status_data = get_status(profile_id)
                if status_data.get("state") in STOP_STATES:
                    return []

                try:
                    results = await llm_service.analyze_job_batch(
                        batch_metadata,
                        profile_dict,
                        audit_db=self.db,
                        audit_user_id=profile_dict.get("user_id"),
                    )
                    return list(zip(batch_jobs, results))
                except CircuitOpenError as exc:
                    self._increment_status_errors(profile_id)
                    logger.warning(
                        "Required local-model analysis circuit is open for profile %s: %s",
                        profile_id,
                        type(exc).__name__,
                    )
                    add_log(
                        profile_id,
                        "Required local-model analysis is temporarily unavailable; no "
                        "heuristic result was saved.",
                    )
                    return []
                except Exception as e:
                    self._increment_status_errors(profile_id)
                    logger.warning(
                        "Required local-model analysis failed; no substitute result persisted: %s",
                        type(e).__name__,
                    )
                    add_log(
                        profile_id,
                        "Required local-model analysis failed for this batch; no heuristic "
                        "result was saved.",
                    )
                    return []

        tasks = [
            analyze_batch(batch_jobs, batch_metadata) for batch_jobs, batch_metadata in batches
        ]
        results = await asyncio.gather(*tasks)
        return [item for batch_result in results for item in batch_result]
