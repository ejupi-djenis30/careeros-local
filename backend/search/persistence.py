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


class PersistenceMixin:
    def _upsert_scraped_job(self, listing) -> tuple[ScrapedJob, bool]:
        return self.search_persistence.upsert_scraped_job(
            listing,
            bootstrap_normalized_job_data_fn=bootstrap_normalized_job_data,
            extract_listing_description_text_fn=extract_listing_description_text,
            extract_company_name_fn=extract_company_name,
            extract_listing_location_string_fn=extract_listing_location_string,
            extract_listing_workload_string_fn=extract_listing_workload_string,
            parse_listing_publication_date_fn=parse_listing_publication_date,
        )

    async def _persist_scraped_job_catalog(self, profile_id: int, jobs: list) -> tuple[int, int]:
        """Persist jobs into the shared catalog before downstream normalization/analysis.

        Partial success is intentional: successfully persisted jobs continue through the
        pipeline in the current run, while failed jobs are tagged and excluded from the
        downstream queue so the catalog-first invariant is preserved.
        """
        result = self.search_persistence.persist_scraped_job_catalog(
            jobs,
            upsert_scraped_job=self._upsert_scraped_job,
        )

        if result.created == 0 and result.updated == 0 and result.failed > 0:
            raise RuntimeError(
                f"Failed to persist all {result.failed} scraped catalog job entries for profile {profile_id}"
            )

        if result.conflict_recoveries:
            self._increment_catalog_conflicts(profile_id, result.conflict_recoveries)

        add_log(
            profile_id,
            "Persisted shared job catalog entries before filtering: "
            f"{result.created} created, {result.updated} refreshed"
            + (f", {result.failed} failed" if result.failed else "")
            + (
                f", {result.conflict_recoveries} catalog conflicts recovered"
                if result.conflict_recoveries
                else ""
            ),
        )
        return result.created, result.updated

    def _deduplicate(self, profile, all_jobs: list) -> tuple[list, int]:
        profile_id = getattr(profile, "id", profile)

        dedup_state = self._new_run_dedup_state()
        duplicate_counts = self._new_duplicate_counts()
        unique_jobs: list = []

        existing_identifiers = self.job_repo.get_profile_job_identifiers(profile_id)
        profile_user_id = getattr(profile, "user_id", None)
        applied_scraped_ids = (
            self.job_repo.get_applied_scraped_job_ids(profile_user_id)
            if profile_user_id is not None
            else set()
        )

        profile_history = {
            "existing_keys": {
                listing_identity_key(row)
                for row in existing_identifiers
                if listing_identity_key(row)
            },
            "existing_urls": {
                listing_url_token(row) for row in existing_identifiers if listing_url_token(row)
            },
            "existing_fuzzy_keys": {
                listing_fuzzy_key(row) for row in existing_identifiers if listing_fuzzy_key(row)
            },
            "existing_fuzzy_keys_strong": {
                listing_fuzzy_key(row)
                for row in existing_identifiers
                if listing_fuzzy_key(row) and (listing_identity_key(row) or listing_url_token(row))
            },
        }

        # Batch-load existing ScrapedJob records for "applied elsewhere" check.
        # Groups by platform and uses a single IN query per provider, avoiding N+1 DB roundtrips.
        applied_scraped_id_by_pair: dict = {}
        if applied_scraped_ids:
            pairs_by_platform: dict = {}
            for job in all_jobs:
                p = getattr(job, "source", None) or getattr(job, "platform", "unknown")
                pid = str(getattr(job, "id", "") or getattr(job, "platform_job_id", ""))
                if p and pid:
                    pairs_by_platform.setdefault(p, []).append(pid)

            applied_scraped_id_by_pair = self.job_repo.get_applied_scraped_pairs(
                pairs_by_platform,
                applied_scraped_ids,
            )

        for listing in all_jobs:
            platform = getattr(listing, "source", None) or getattr(listing, "platform", "unknown")
            platform_id = normalize_listing_identifier(
                getattr(listing, "id", "") or getattr(listing, "platform_job_id", "")
            )

            key = listing_identity_key(listing)
            url = listing_url_token(listing)
            fuzzy_key = listing_fuzzy_key(listing)
            desc_fp = listing_description_fingerprint(listing)

            duplicate_reason = self._duplicate_reason(
                key=key,
                url=url,
                fuzzy=fuzzy_key,
                desc_fp=desc_fp,
                run_state=dedup_state,
                history=profile_history,
            )
            if duplicate_reason:
                self._increment_duplicate_count(duplicate_counts, duplicate_reason)
                logger.debug(
                    "[DEDUP] Skipping %s duplicate: %s/%s (desc_fp=%s…)",
                    duplicate_reason,
                    platform,
                    platform_id,
                    (desc_fp or "")[:8],
                )
                continue

            self._record_dedup_markers(
                key=key,
                url=url,
                fuzzy=fuzzy_key,
                desc_fp=desc_fp,
                run_state=dedup_state,
                history=profile_history,
            )

            # Feature 2 check: applied elsewhere (O(1) dict lookup — no per-listing DB queries)
            applied_elsewhere = (platform, platform_id) in applied_scraped_id_by_pair

            setattr(listing, "_applied_elsewhere", applied_elsewhere)
            unique_jobs.append(listing)

        duplicates = self._duplicate_total(duplicate_counts)
        return unique_jobs, duplicates

    async def _save_single_job(
        self, listing, analysis, profile_dict, origin_coords, commit: bool = True
    ):
        await self.search_persistence.save_single_job(
            listing,
            analysis,
            profile_dict,
            origin_coords,
            upsert_scraped_job=self._upsert_scraped_job,
            geocode_location_fn=geocode_location,
            commit=commit,
        )

    def _status_metrics(self, profile_id: int) -> Dict[str, int]:
        status = get_status(profile_id) or {}

        def as_int(key: str) -> int:
            value = status.get(key, 0)
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        return {
            "errors": as_int("errors"),
            "provider_failures": as_int("provider_failures"),
            "provider_successes": as_int("provider_successes"),
        }

    def _status_duplicate_metrics(self, profile_id: int) -> Dict[str, int]:
        status = get_status(profile_id) or {}

        def as_int(key: str) -> int:
            value = status.get(key, 0)
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        total = as_int("jobs_duplicates_total")
        if total == 0:
            total = as_int("jobs_duplicates")

        return {
            "jobs_duplicates_total": total,
            "jobs_duplicates_runtime": as_int("jobs_duplicates_runtime"),
            "jobs_duplicates_history": as_int("jobs_duplicates_history"),
            "jobs_duplicates_catalog_conflicts": as_int("jobs_duplicates_catalog_conflicts"),
        }

    @staticmethod
    def _new_duplicate_counts() -> Dict[str, int]:
        return {
            "runtime": 0,
            "history": 0,
        }

    @staticmethod
    def _duplicate_total(duplicate_counts: Dict[str, int]) -> int:
        return int(duplicate_counts.get("runtime", 0)) + int(duplicate_counts.get("history", 0))

    @staticmethod
    def _increment_duplicate_count(duplicate_counts: Dict[str, int], reason: str) -> None:
        bucket = "history" if reason == "history" else "runtime"
        duplicate_counts[bucket] = int(duplicate_counts.get(bucket, 0)) + 1

    def _update_duplicate_breakdown_status(
        self, profile_id: int, duplicate_counts: Dict[str, int]
    ) -> None:
        update_status(
            profile_id,
            jobs_duplicates_total=self._duplicate_total(duplicate_counts),
            jobs_duplicates_runtime=int(duplicate_counts.get("runtime", 0)),
            jobs_duplicates_history=int(duplicate_counts.get("history", 0)),
        )

    def _increment_catalog_conflicts(self, profile_id: int, count: int) -> int:
        current = self._status_duplicate_metrics(profile_id)["jobs_duplicates_catalog_conflicts"]
        next_value = current + max(0, count)
        update_status(profile_id, jobs_duplicates_catalog_conflicts=next_value)
        return next_value

    def _increment_status_errors(self, profile_id: int, count: int = 1) -> int:
        next_errors = self._status_metrics(profile_id)["errors"] + max(0, count)
        update_status(profile_id, errors=next_errors)
        return next_errors

    def _load_profile_dedup_history(self, profile_id: int, user_id: Optional[int]) -> dict:
        """Pre-load profile job history sets for incremental deduplication in the producer."""
        existing_identifiers = self.job_repo.get_profile_job_identifiers(profile_id)
        applied_scraped_ids = (
            self.job_repo.get_applied_scraped_job_ids(user_id) if user_id is not None else set()
        )
        existing_fuzzy_keys_strong = {
            listing_fuzzy_key(r)
            for r in existing_identifiers
            if listing_fuzzy_key(r) and (listing_identity_key(r) or listing_url_token(r))
        }
        return {
            "existing_keys": {
                listing_identity_key(r) for r in existing_identifiers if listing_identity_key(r)
            },
            "existing_urls": {
                listing_url_token(r) for r in existing_identifiers if listing_url_token(r)
            },
            "existing_fuzzy_keys": {
                listing_fuzzy_key(r) for r in existing_identifiers if listing_fuzzy_key(r)
            },
            "existing_fuzzy_keys_strong": existing_fuzzy_keys_strong,
            "applied_scraped_ids": applied_scraped_ids,
        }

    @staticmethod
    def _new_run_dedup_state() -> dict:
        return {
            "seen_identity_keys": set(),
            "seen_url_tokens": set(),
            "seen_fuzzy_keys_any": set(),
            "seen_fuzzy_keys_strong": set(),
            "seen_desc_fingerprints": set(),
        }

    @staticmethod
    def _duplicate_reason(
        *,
        key: Optional[str],
        url: str,
        fuzzy: str,
        desc_fp: Optional[str],
        run_state: dict,
        history: dict,
    ) -> Optional[str]:
        if key and key in run_state["seen_identity_keys"]:
            return "runtime"
        if key and key in history["existing_keys"]:
            return "history"

        if url and url in run_state["seen_url_tokens"]:
            return "runtime"
        if url and url in history["existing_urls"]:
            return "history"

        if desc_fp and desc_fp in run_state["seen_desc_fingerprints"]:
            return "runtime"

        if not fuzzy:
            return None

        has_anchor = bool(key or url)
        in_existing_fuzzy = fuzzy in history["existing_fuzzy_keys"]
        in_seen_fuzzy = fuzzy in run_state["seen_fuzzy_keys_any"]

        # Fuzzy is a standalone signal only for weakly identified listings.
        if not has_anchor and in_existing_fuzzy:
            return "history"
        if not has_anchor and in_seen_fuzzy:
            return "runtime"

        # For strongly identified jobs, fuzzy collisions alone are too aggressive.
        # Require same body fingerprint as additional evidence.
        in_run_strong_fuzzy = fuzzy in run_state["seen_fuzzy_keys_strong"]
        in_history_strong_fuzzy = fuzzy in history["existing_fuzzy_keys_strong"]
        if (
            has_anchor
            and (in_run_strong_fuzzy or in_history_strong_fuzzy)
            and desc_fp
            and desc_fp in run_state["seen_desc_fingerprints"]
        ):
            return "history" if in_history_strong_fuzzy else "runtime"

        return None

    @classmethod
    def _should_skip_duplicate(
        cls,
        *,
        key: Optional[str],
        url: str,
        fuzzy: str,
        desc_fp: Optional[str],
        run_state: dict,
        history: dict,
    ) -> bool:
        return (
            cls._duplicate_reason(
                key=key,
                url=url,
                fuzzy=fuzzy,
                desc_fp=desc_fp,
                run_state=run_state,
                history=history,
            )
            is not None
        )

    @staticmethod
    def _record_dedup_markers(
        *,
        key: Optional[str],
        url: str,
        fuzzy: str,
        desc_fp: Optional[str],
        run_state: dict,
        history: dict,
    ) -> None:
        if key:
            run_state["seen_identity_keys"].add(key)
            history["existing_keys"].add(key)
        if url:
            run_state["seen_url_tokens"].add(url)
            history["existing_urls"].add(url)
        if fuzzy:
            run_state["seen_fuzzy_keys_any"].add(fuzzy)
            history["existing_fuzzy_keys"].add(fuzzy)
            if key or url or desc_fp:
                run_state["seen_fuzzy_keys_strong"].add(fuzzy)
                history["existing_fuzzy_keys_strong"].add(fuzzy)
        if desc_fp:
            run_state["seen_desc_fingerprints"].add(desc_fp)
