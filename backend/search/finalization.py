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
from backend.core.diagnostics import (
    ActivityCode,
    FailureCode,
    diagnose_failure,
    log_failure,
    public_activity_message,
    public_status_message,
)
from backend.models import ScrapedJob, SearchProfile, User
from backend.models.user import VAULT_STATE_READY
from backend.providers.circuit_breaker import CircuitOpenError
from backend.providers.jobs.jobroom.client import JobRoomProvider
from backend.providers.jobs.swissdevjobs.client import SwissDevJobsProvider
from backend.repositories.job_repository import JobRepository
from backend.repositories.profile_repository import ProfileRepository
from backend.search.consent import (
    consent_audit_record,
)
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
from backend.providers.configuration.registry import configured_provider_registry
from backend.providers.configuration.service import ProviderConfigurationService
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
    add_failure_log,
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


class FinalizationMixin:
    async def run_search(
        self,
        profile_id: int,
        force_regenerate_cv_summary: bool = False,
        force_regenerate_queries: bool = False,
        reservation_token: str | None = None,
    ):
        """Run the full search workflow for a saved profile."""
        if settings.OFFLINE_MODE is True:
            logger.info("Skipping live job search because offline mode is active")
            release_task(profile_id, reservation_token)
            return
        if not self._activate_search_task(profile_id, reservation_token):
            logger.warning(
                "Aborting search startup for profile %d because task activation was rejected",
                profile_id,
            )
            release_task(profile_id, reservation_token)
            return

        base_providers = self.providers
        configured_providers = self.providers
        try:
            profile = self.profile_repo.get(profile_id)
            if profile is None:
                return
            owner = self.db.get(User, profile.user_id)
            if owner is None or owner.vault_lifecycle_state != VAULT_STATE_READY:
                logger.info("Search stopped because vault maintenance is pending")
                return
            try:
                readiness = await self.analysis_readiness_check()
            except Exception:
                readiness = None
            if readiness is None or not readiness.ready:
                init_status(profile_id, user_id=profile.user_id)
                add_log(
                    profile_id,
                    public_activity_message(ActivityCode.MODEL_READINESS_FAILED),
                )
                update_status(
                    profile_id,
                    state="error",
                    terminal_reason="local_model_required",
                    error=public_status_message(FailureCode.LOCAL_MODEL_REQUIRED),
                )
                return
            # Ensure fresh LLM providers (reload config).
            llm_service.clear_provider_cache()
            configured_providers, _installed_names = configured_provider_registry(
                self.db,
                profile.user_id,
                builtins=base_providers,
            )
            original_provider_names = set(base_providers) | {
                row.key for row in ProviderConfigurationService(self.db).rows(profile.user_id)
            }
            self.providers = configured_providers
            enabled_provider_names = set(self.providers)
            consent_audit = consent_audit_record(original_provider_names, enabled_provider_names)
            logger.info(
                "Job source consent gate enabled=%s disabled=%s",
                consent_audit["enabled"],
                consent_audit["disabled"],
            )
            await self._run_pipeline_with_timeout(
                profile_id,
                force_regenerate_cv_summary=force_regenerate_cv_summary,
                force_regenerate_queries=force_regenerate_queries,
            )
        except Exception as error:
            diagnostic = diagnose_failure(error, FailureCode.SEARCH_UNEXPECTED)
            log_failure(logger, diagnostic)
            add_failure_log(profile_id, diagnostic)
            update_status(
                profile_id,
                state="error",
                terminal_reason=FailureCode.SEARCH_UNEXPECTED.value,
                error=diagnostic.public_message,
            )
        finally:
            # Denied providers may still own sessions created during service
            # construction; close the complete configured set exactly once.
            self.providers = configured_providers
            await self._close_provider_resources()
            self.providers = base_providers
            if reservation_token is not None:
                release_task(profile_id, reservation_token)
            unregister_task(profile_id)

    def _activate_search_task(self, profile_id: int, reservation_token: str | None) -> bool:
        return bool(
            register_task(
                profile_id,
                asyncio.current_task(),
                reservation_token=reservation_token,
            )
        )

    async def _run_pipeline_with_timeout(
        self,
        profile_id: int,
        *,
        force_regenerate_cv_summary: bool,
        force_regenerate_queries: bool,
    ) -> None:
        try:
            await asyncio.wait_for(
                self._run_pipeline(
                    profile_id,
                    force_regenerate_cv_summary,
                    force_regenerate_queries,
                ),
                timeout=settings.SEARCH_PIPELINE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Pipeline timeout for profile %d after %d seconds",
                profile_id,
                settings.SEARCH_PIPELINE_TIMEOUT_SECONDS,
            )
            add_log(
                profile_id,
                public_activity_message(
                    ActivityCode.PIPELINE_TIMEOUT,
                    seconds=settings.SEARCH_PIPELINE_TIMEOUT_SECONDS,
                ),
            )
            update_status(
                profile_id,
                state="error",
                terminal_reason="pipeline_timeout",
                error=public_status_message(FailureCode.PIPELINE_TIMEOUT),
            )

    async def _run_pipeline(
        self,
        profile_id: int,
        force_regenerate_cv_summary: bool = False,
        force_regenerate_queries: bool = False,
    ) -> None:
        """Execute the core search pipeline steps (wrapped by run_search with timeout)."""
        profile = self.profile_repo.get(profile_id)
        if not profile:
            logger.error("Search profile not found profile_id=%d", profile_id)
            return

        profile_dict = {
            "id": profile.id,
            "user_id": profile.user_id,
            "cv_content": profile.cv_content or "",
            "role_description": profile.role_description or "",
            "search_strategy": profile.search_strategy or "",
            "latitude": profile.latitude,
            "longitude": profile.longitude,
            # Feature 3: force-regeneration flags (propagated from HTTP request)
            "force_regenerate_cv_summary": force_regenerate_cv_summary,
            "force_regenerate_queries": force_regenerate_queries,
        }
        profile_preferences = self._profile_preferences(profile)
        user_id = profile.user_id

        # ── Step 1: Initialize status immediately ──
        init_status(profile_id, user_id=user_id)
        add_log(
            profile_id,
            public_activity_message(ActivityCode.PLAN_GENERATING),
        )

        provider_infos = {name: p.get_provider_info() for name, p in self.providers.items() if p}

        searches = await self._generate_plan(profile_id, profile_dict, profile, provider_infos)
        if not searches:
            status_data = get_status(profile_id)
            terminal_reason = status_data.get("terminal_reason") or "no_explicit_queries"
            add_log(
                profile_id,
                public_activity_message(ActivityCode.NO_EXPLICIT_PLAN),
            )
            update_status(profile_id, state="done", terminal_reason=terminal_reason)
            return

        # ── CV Summary (with caching Feature 3) ──
        cv_summary = ""
        if profile_dict.get("cv_content"):
            force_regen_cv = profile_dict.get("force_regenerate_cv_summary", False)
            if profile.cached_cv_summary and not force_regen_cv:
                cv_summary = profile.cached_cv_summary
                add_log(
                    profile_id,
                    public_activity_message(ActivityCode.CV_SUMMARY_CACHE_HIT),
                )
            else:
                try:
                    cv_summary = await llm_service.summarize_cv(profile_dict["cv_content"])
                    add_log(
                        profile_id,
                        public_activity_message(ActivityCode.CV_SUMMARY_CREATED),
                    )
                    # Save to cache
                    self.profile_repo.update(profile, {"cached_cv_summary": cv_summary})
                except Exception as error:
                    diagnostic = diagnose_failure(error, FailureCode.CV_SUMMARY_FAILED)
                    log_failure(logger, diagnostic, level=logging.WARNING)
                    raw_cv = profile_dict["cv_content"]
                    # Guard against oversized fallback reaching the MATCH LLM
                    if len(raw_cv) > settings.MAX_DESCRIPTION_CHARS:
                        cv_summary = raw_cv[: settings.MAX_DESCRIPTION_CHARS]
                        logger.warning(
                            "CV content truncated to %d chars for profile %s (fallback path)",
                            settings.MAX_DESCRIPTION_CHARS,
                            profile_id,
                        )
                    else:
                        cv_summary = raw_cv
        profile_dict["cv_summary"] = cv_summary

        # ── Step 1.5: Normalize candidate profile for deterministic matching ──
        # Runs once per unique (cv, role_description, search_strategy) triplet.
        # Result is cached on the profile row; force_regenerate_cv_summary also forces
        # a re-extraction of the profile normalization since CV content drives it.
        force_regen_cv = profile_dict.get("force_regenerate_cv_summary", False)
        profile_normalization = await self._normalize_user_profile(
            profile_id, profile, profile_dict, force=force_regen_cv
        )
        profile_dict["profile_normalization"] = profile_normalization
        profile_dict["match_profile_snapshot"] = self._ensure_match_profile_snapshot(
            profile_id,
            profile,
            profile_dict,
            profile_normalization,
            force=force_regen_cv,
        )

        # ── Step 1.6: Load user preference signals for prescore gating ──
        try:
            from backend.services.preference_service import get_preference_signals

            profile_dict["preference_signals"] = get_preference_signals(user_id, self.db) or {}
        except Exception:
            profile_dict["preference_signals"] = {}

        # ── Steps 2-6: Streaming pipeline — search, normalize, filter, analyze, save ──
        # Each query's results flow through the full pipeline immediately after the
        # query completes, overlapping with still-ongoing searches.
        update_status(profile_id, state="searching")
        add_log(
            profile_id,
            public_activity_message(ActivityCode.PIPELINE_STREAMING),
        )

        # Pre-load profile job history for incremental deduplication inside the producer.
        profile_history = self._load_profile_dedup_history(profile_id, user_id)
        had_profile_history = bool(
            profile_history.get("existing_keys")
            or profile_history.get("existing_urls")
            or profile_history.get("existing_fuzzy_keys_strong")
        )

        # The producer streams unique-per-query batches; the consumer normalizes,
        # filters, analyzes, and immediately persists each batch as it arrives.
        job_queue: asyncio.Queue = asyncio.Queue()
        (producer_result, consumer_result) = await asyncio.gather(
            self._search_and_produce(
                profile_id, profile, searches, provider_infos, job_queue, profile_history
            ),
            self._processing_consumer(profile_id, profile_dict, profile_preferences, job_queue),
        )
        total_found, total_duplicates = producer_result
        duplicate_metrics = self._status_duplicate_metrics(profile_id)
        history_duplicates = duplicate_metrics["jobs_duplicates_history"]
        runtime_duplicates = duplicate_metrics["jobs_duplicates_runtime"]
        if total_duplicates > 0 and history_duplicates == 0 and runtime_duplicates == 0:
            if had_profile_history:
                history_duplicates = total_duplicates
            else:
                runtime_duplicates = total_duplicates
        if len(consumer_result) == 5:
            (
                total_filtered,
                analysis_failed,
                analyzed_pairs,
                consumer_saved,
                consumer_skipped,
            ) = consumer_result
            analysis_skipped = 0
        else:
            (
                total_filtered,
                analysis_failed,
                analyzed_pairs,
                consumer_saved,
                consumer_skipped,
                analysis_skipped,
            ) = consumer_result
        status_metrics = self._status_metrics(profile_id)

        if total_found == 0:
            if (
                status_metrics["provider_failures"] > 0
                and status_metrics["provider_successes"] == 0
            ):
                add_log(
                    profile_id,
                    public_activity_message(ActivityCode.PROVIDER_ALL_FAILED),
                )
                update_status(
                    profile_id,
                    state="error",
                    terminal_reason="search_execution_failed",
                    error=public_status_message(FailureCode.PROVIDER_ALL_FAILED),
                )
                return
            add_log(
                profile_id,
                public_activity_message(ActivityCode.NO_RESULTS),
            )
            update_status(profile_id, state="done", terminal_reason="no_results")
            return

        unique_total = total_found - total_duplicates
        if unique_total == 0:
            if history_duplicates == total_duplicates and total_duplicates > 0:
                add_log(
                    profile_id,
                    public_activity_message(ActivityCode.SEARCH_HISTORY_ONLY),
                )
                update_status(
                    profile_id,
                    state="done",
                    terminal_reason="all_duplicates",
                    jobs_found=total_found,
                    jobs_duplicates=total_duplicates,
                    jobs_unique=total_found - total_duplicates,
                )
            else:
                add_log(
                    profile_id,
                    public_activity_message(ActivityCode.SEARCH_RUNTIME_DEDUP_ONLY),
                )
                update_status(
                    profile_id,
                    state="done",
                    terminal_reason="no_jobs_after_dedup",
                    jobs_found=total_found,
                    jobs_duplicates=total_duplicates,
                    jobs_unique=total_found - total_duplicates,
                )
            return

        if not analyzed_pairs:
            if analysis_failed > 0:
                add_log(
                    profile_id,
                    public_activity_message(ActivityCode.LOCAL_ANALYSIS_FAILED),
                )
                update_status(
                    profile_id,
                    state="error",
                    terminal_reason="local_analysis_failed",
                    jobs_found=total_found,
                    jobs_duplicates=total_duplicates,
                    jobs_unique=total_found - total_duplicates,
                    jobs_skipped=total_filtered + analysis_failed,
                    error=public_status_message(FailureCode.LOCAL_ANALYSIS_FAILED),
                )
                return
            # Jobs are "explained" if they were filtered by structured rules OR if they
            # passed filters but were lost due to LLM analysis errors (already counted in
            # errors counter by _run_analysis_batches).  Only truly unexplained missing jobs
            # — where neither filtering nor analysis failure accounts for them — warrant a
            # pipeline_processing_failed terminal state.
            unexplained_unique = max(0, unique_total - total_filtered - analysis_failed)
            if status_metrics["errors"] > 0 and unexplained_unique > 0:
                add_log(
                    profile_id,
                    public_activity_message(ActivityCode.PIPELINE_PROCESSING_FAILED),
                )
                update_status(
                    profile_id,
                    state="error",
                    terminal_reason="pipeline_processing_failed",
                    jobs_found=total_found,
                    jobs_duplicates=total_duplicates,
                    jobs_unique=total_found - total_duplicates,
                    jobs_skipped=total_filtered + analysis_skipped,
                    error=public_status_message(FailureCode.PIPELINE_PROCESSING_FAILED),
                )
            else:
                add_log(
                    profile_id,
                    public_activity_message(ActivityCode.STRUCTURED_NO_RESULTS),
                )
                update_status(
                    profile_id,
                    state="done",
                    terminal_reason="no_jobs_after_structured_filters",
                    jobs_found=total_found,
                    jobs_duplicates=total_duplicates,
                    jobs_unique=total_found - total_duplicates,
                    jobs_skipped=total_filtered + analysis_skipped,
                )
            return

        if analysis_failed > 0:
            add_log(
                profile_id,
                public_activity_message(ActivityCode.LOCAL_ANALYSIS_FAILED),
            )
            update_status(
                profile_id,
                state="error",
                terminal_reason="local_analysis_failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                jobs_found=total_found,
                jobs_new=consumer_saved,
                jobs_duplicates=total_duplicates,
                jobs_unique=total_found - total_duplicates,
                jobs_skipped=total_filtered + consumer_skipped + analysis_failed,
                error=public_status_message(FailureCode.LOCAL_ANALYSIS_FAILED),
            )
            return

        # Jobs have already been saved progressively by the consumer.
        # Check whether any job made it through analysis but failed to persist.
        pre_finalize_errors = self._status_metrics(profile_id)["errors"]
        if consumer_saved == 0 and analyzed_pairs and pre_finalize_errors > 0:
            add_log(
                profile_id,
                public_activity_message(ActivityCode.JOBS_NOT_PERSISTED),
            )
            update_status(
                profile_id,
                state="error",
                terminal_reason="job_persistence_failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                jobs_found=total_found,
                jobs_duplicates=total_duplicates,
                jobs_unique=total_found - total_duplicates,
                jobs_skipped=total_filtered + consumer_skipped + analysis_skipped,
                error=public_status_message(FailureCode.NO_PERSISTED_JOBS),
            )
            return

        # ── Step 6b: Optional final passes (critique/rerank/salary) ──
        # These passes refine analysis on already-saved rows; they are LLM-heavy and run
        # only once across all batches after the search stream completes.
        # A saved row must remain byte-for-byte attributable to its validated job_match
        # contract. Refinement passes stay off until a provenance chain is persisted.
        needs_final_pass = False
        if needs_final_pass and analyzed_pairs:
            add_log(
                profile_id,
                public_activity_message(
                    ActivityCode.REFINEMENT_STARTED,
                    count=len(analyzed_pairs),
                ),
            )
            update_status(profile_id, state="analyzing")
            await self._finalize_and_save(profile_id, profile_dict, analyzed_pairs)

        saved_count = consumer_saved
        total_skipped = total_filtered + consumer_skipped + analysis_skipped
        add_log(
            profile_id,
            public_activity_message(
                ActivityCode.SEARCH_COMPLETE,
                saved=saved_count,
                skipped=total_skipped,
            ),
        )
        update_status(
            profile_id,
            state="done",
            terminal_reason="completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            jobs_found=total_found,
            jobs_new=saved_count,
            jobs_duplicates=total_duplicates,
            jobs_unique=total_found - total_duplicates,
            jobs_skipped=total_skipped,
        )

    async def _processing_consumer(
        self,
        profile_id: int,
        profile_dict: dict,
        profile_preferences: dict,
        job_queue: asyncio.Queue,
    ) -> tuple[int, int, list, int, int, int]:
        """Consume job batches from the queue; run normalize → filter → LLM analysis
        on each batch immediately as it arrives, overlapping with ongoing searches.
        Each analyzed batch is persisted to the Job table immediately — before the
        next batch is even started — so new jobs appear in the DB and in the UI
        while the search is still running.

        Returns (total_filtered_count, analysis_failed_count, analyzed_pairs, total_saved,
        total_save_skipped, total_analysis_skipped) where:
        - total_filtered_count: jobs dropped by structured filters
        - analysis_failed_count: jobs that passed filters but were lost due to LLM analysis errors
        - analyzed_pairs: list of (job_listing, analysis_dict) — kept for optional final passes
        - total_saved: jobs successfully persisted
        - total_save_skipped: jobs lost due to persistence errors
        - total_analysis_skipped: jobs intentionally skipped because MATCH analysis could not run
        """
        total_filtered = 0
        analysis_failed = 0
        analyzed_pairs: list = []
        cumulative_to_analyze = 0
        total_saved = 0
        total_save_skipped = 0
        total_analysis_skipped = 0
        cumulative_skipped = 0

        # Pre-compute origin_coords once so every batch save call can calculate distance.
        origin_coords = None
        if profile_dict.get("latitude") and profile_dict.get("longitude"):
            origin_coords = (profile_dict["latitude"], profile_dict["longitude"])

        while True:
            batch = await job_queue.get()
            if batch is None:
                # Sentinel: producer finished.
                break

            status_data = get_status(profile_id)
            if status_data.get("state") in STOP_STATES:
                break

            # ── Normalize ──
            # Normalization failure is a soft warning: the batch continues with provider-bootstrap
            # fields only.  We do NOT increment the errors counter here because normalization is
            # not a terminal failure — it does not cause job loss by itself.  The activity log
            # records the issue so the user can debug if needed.
            try:
                await self._normalize_persisted_jobs(profile_id, batch)
            except Exception as error:
                diagnostic = diagnose_failure(error, FailureCode.JOB_NORMALIZATION_FAILED)
                log_failure(logger, diagnostic, level=logging.WARNING)
                add_failure_log(profile_id, diagnostic)

            # ── Filter ──
            pre_filter = len(batch)
            filtered_batch = self._apply_structured_filters(
                profile_id, profile_dict, batch, profile_preferences
            )
            filtered_out = pre_filter - len(filtered_batch)
            total_filtered += filtered_out
            cumulative_skipped += filtered_out

            if filtered_out:
                update_status(profile_id, jobs_skipped=cumulative_skipped)

            if not filtered_batch:
                continue

            # ── Analyze ──
            # NOTE: we defer the status update until AFTER analysis completes so that the
            # frontend never sees a completed ratio (analyzed == total) for just the
            # first batch while more searches are still running.  Both counters are written
            # in a single update_status call to keep the ratio coherent.
            analysis_input_count = len(filtered_batch)
            if llm_service.is_analysis_circuit_open():
                self._increment_status_errors(profile_id)
                analysis_failed += analysis_input_count
                total_analysis_skipped += analysis_input_count
                cumulative_to_analyze += analysis_input_count
                cumulative_skipped += analysis_input_count
                add_log(
                    profile_id,
                    public_activity_message(
                        ActivityCode.LOCAL_ANALYSIS_UNAVAILABLE,
                        count=analysis_input_count,
                    ),
                )
                update_status(
                    profile_id,
                    jobs_analyze_total=cumulative_to_analyze,
                    jobs_analyzed=len(analyzed_pairs),
                    jobs_new=total_saved,
                    jobs_skipped=cumulative_skipped,
                )
                continue

            batch_pairs = await self._run_analysis_batches(profile_id, profile_dict, filtered_batch)
            # Track jobs that passed filters but were lost due to analysis errors.
            batch_analysis_failed = analysis_input_count - len(batch_pairs)
            analysis_failed += batch_analysis_failed
            total_analysis_skipped += batch_analysis_failed
            cumulative_to_analyze += analysis_input_count
            cumulative_skipped += batch_analysis_failed
            analyzed_pairs.extend(batch_pairs)

            # ── Save immediately (progressive persistence) ──
            # Jobs reaching this point are persisted without waiting for the search to finish.
            # _save_single_job is a conflict-safe upsert: if the same job was already saved
            # (e.g. by a concurrent coroutine or a previous run) its analysis fields are
            # updated in-place and user-action fields (applied, dismissed) are preserved.
            batch_saved = 0
            batch_skipped = 0
            for listing, analysis in batch_pairs:
                try:
                    save_outcome = await self._save_single_job(
                        listing, analysis, profile_dict, origin_coords, commit=True
                    )
                    if save_outcome == "stale_catalog":
                        stale_count = self._increment_stale_before_save(profile_id)
                        logger.info(
                            "Discarded stale catalog analysis for profile %s; total=%s",
                            profile_id,
                            stale_count,
                        )
                        if stale_count <= 3 or stale_count in {10, 25, 50, 100}:
                            add_log(
                                profile_id,
                                public_activity_message(ActivityCode.STALE_RESULT_SKIPPED),
                            )
                        batch_skipped += 1
                        continue
                    batch_saved += 1
                except Exception as error:
                    self._increment_status_errors(profile_id)
                    diagnostic = diagnose_failure(error, FailureCode.PROGRESSIVE_SAVE_FAILED)
                    log_failure(logger, diagnostic, level=logging.WARNING)
                    batch_skipped += 1

            total_saved += batch_saved
            total_save_skipped += batch_skipped
            cumulative_skipped += batch_skipped

            update_status(
                profile_id,
                jobs_analyze_total=cumulative_to_analyze,
                jobs_analyzed=len(analyzed_pairs),
                jobs_new=total_saved,
                jobs_skipped=cumulative_skipped,
            )

        return (
            total_filtered,
            analysis_failed,
            analyzed_pairs,
            total_saved,
            total_save_skipped,
            total_analysis_skipped,
        )

    async def _finalize_and_save(
        self,
        profile_id: int,
        profile_dict: dict,
        analyzed_pairs: list,
    ) -> None:
        """Keep persisted analysis identical to the validated ``job_match`` output.

        Refinement passes previously changed scores after contract validation without
        recording a second model invocation or evidence chain. They remain disabled
        until the persistence model can represent that complete provenance.
        """
        add_log(
            profile_id,
            public_activity_message(ActivityCode.ANALYSIS_REFINEMENT_SAVED),
        )
