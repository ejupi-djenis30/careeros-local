# ruff: noqa: F401

"""Focused domain slice of the local job-search pipeline."""

import asyncio
import inspect
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.jobs.matching import deterministic_job_match
from backend.models import ScrapedJob, SearchProfile
from backend.providers.circuit_breaker import CircuitOpenError
from backend.providers.jobs.jobroom.client import JobRoomProvider
from backend.providers.jobs.swissdevjobs.client import SwissDevJobsProvider
from backend.repositories.job_repository import JobRepository
from backend.repositories.profile_repository import ProfileRepository
from backend.search.deterministic_planning import build_deterministic_search_plan
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


class AcquisitionMixin:
    def _profile_preferences(self, profile) -> Dict[str, Any]:
        remote_pref = get_profile_preference(profile, "remote_only", False)
        return {
            "preferred_languages": coerce_string_list(
                get_profile_preference(profile, "preferred_languages"), normalize_language
            ),
            "preferred_domains": coerce_string_list(
                get_profile_preference(profile, "preferred_domains"), normalize_domain
            ),
            "remote_only": remote_pref if isinstance(remote_pref, bool) else False,
            "salary_min_chf": coerce_int(get_profile_preference(profile, "salary_min_chf"), None),
            "workload_min": coerce_int(get_profile_preference(profile, "workload_min"), None),
            "workload_max": coerce_int(get_profile_preference(profile, "workload_max"), None),
            "hard_max_distance_km": coerce_int(
                get_profile_preference(profile, "hard_max_distance_km"), None
            ),
        }

    def _apply_query_preferences(
        self, searches: List[Dict[str, Any]], preferences: Dict[str, Any]
    ) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
        # NOTE: preferred_languages intentionally NOT used here.
        # Queries are always generated in all core languages (en, de, fr, it) so that
        # jobs written in any language are discovered — a job posting in German may still
        # accept Italian-speaking candidates.  Language preference is enforced later at the
        # job-filtering stage (_passes_structured_filters → _extract_required_language_codes).
        allowed_domains = set(preferences.get("preferred_domains") or [])

        stats = {
            "dropped_language": 0,
            "dropped_domain": 0,
        }
        filtered: List[Dict[str, Any]] = []
        for search in searches:
            domain = normalize_domain(search.get("domain", "general"))
            if allowed_domains and domain not in allowed_domains:
                stats["dropped_domain"] += 1
                continue
            filtered.append(search)
        return filtered, stats

    def _build_deterministic_explicit_plan(
        self, profile_dict: dict, profile
    ) -> List[Dict[str, str]]:
        """Build provider queries exclusively from explicit search settings."""
        return build_deterministic_search_plan(
            profile_dict,
            profile,
            default_max_queries=max(
                0, int(getattr(settings, "SEARCH_DEGRADED_PLAN_MAX_QUERIES", 3))
            ),
            default_max_keywords=max(
                0, int(getattr(settings, "SEARCH_DEGRADED_PLAN_MAX_KEYWORDS", 2))
            ),
        )

    async def _close_provider_resources(self) -> None:
        for provider_name, provider in self.providers.items():
            if not provider:
                continue

            try:
                # Use static lookup to avoid triggering synthetic Mock attributes.
                if inspect.getattr_static(provider, "close", None) is not None:
                    close_result = provider.close()
                    if asyncio.iscoroutine(close_result):
                        await close_result
                    continue

                session = getattr(provider, "_session", None)
                if session and inspect.getattr_static(session, "aclose", None) is not None:
                    close_result = session.aclose()
                    if asyncio.iscoroutine(close_result):
                        await close_result
            except Exception as close_error:
                logger.warning(
                    "Failed to close provider %s cleanly: %s", provider_name, close_error
                )

    async def _generate_plan(
        self, profile_id: int, profile_dict: dict, profile, provider_infos
    ) -> list:
        # Provider-facing queries are intentionally model-free.  Local model output may
        # still enrich matching later in the pipeline, but it never crosses this boundary.
        del provider_infos
        preferences = self._profile_preferences(profile)
        force_regen_q = profile_dict.get("force_regenerate_queries", False)
        add_log(
            profile_id,
            "Provider query plan: deterministic explicit-input planner; "
            f"profile_id={profile_id} force_regenerate_queries={force_regen_q} "
            f"max_queries={profile.max_queries} max_occupation_queries={profile.max_occupation_queries} "
            f"max_keyword_queries={profile.max_keyword_queries} "
            f"role_description_len={len(profile_dict.get('role_description') or '')}",
        )
        fingerprint_profile = {
            **profile_dict,
            "preferred_domains": preferences.get("preferred_domains") or [],
        }
        input_fingerprint = compute_plan_input_fingerprint(
            fingerprint_profile,
            max_queries=profile.max_queries,
            max_occupation_queries=profile.max_occupation_queries,
            max_keyword_queries=profile.max_keyword_queries,
        )

        cache_compatible = False
        searches: list[dict[str, Any]] = []
        if profile.cached_queries and not force_regen_q:
            try:
                cached_searches, cache_meta = unpack_plan_cache_payload(profile.cached_queries)
                if is_cached_plan_compatible(cache_meta, input_fingerprint):
                    searches = cached_searches
                    cache_compatible = True
                    add_log(
                        profile_id,
                        f"Using {len(searches)} cached deterministic explicit queries.",
                    )
                    update_status(profile_id, plan_cache_hit=1, plan_cache_miss=0)
                else:
                    add_log(
                        profile_id,
                        "Cached queries ignored: legacy, model-derived, or built from different explicit inputs.",
                    )
                    update_status(profile_id, plan_cache_hit=0, plan_cache_miss=1)
            except Exception as e:
                logger.error(f"Failed to parse cached queries: {e}")
                update_status(profile_id, plan_cache_hit=0, plan_cache_miss=1)
        else:
            update_status(profile_id, plan_cache_hit=0, plan_cache_miss=1)

        if not cache_compatible:
            searches = self._build_deterministic_explicit_plan(profile_dict, profile)
            add_log(
                profile_id,
                f"Built {len(searches)} provider queries from explicit search instructions.",
            )
            update_status(
                profile_id,
                planner_mode="deterministic_explicit",
                plan_provenance="deterministic-explicit",
                plan_raw_count=len(searches),
            )

        unique_searches = []
        seen_queries = set()
        dropped_empty_queries = 0
        dropped_duplicate_queries = 0
        for s in searches:
            normalized_search, reason = normalize_search_item(s)
            if not normalized_search:
                dropped_empty_queries += 1
                continue

            fingerprint = exact_query_fingerprint(normalized_search)
            if fingerprint not in seen_queries:
                seen_queries.add(fingerprint)
                unique_searches.append(normalized_search)
            else:
                dropped_duplicate_queries += 1

        preferred_searches, pref_stats = self._apply_query_preferences(unique_searches, preferences)
        dropped_by_preferences = len(unique_searches) - len(preferred_searches)
        if dropped_by_preferences:
            add_log(
                profile_id,
                "Provider plan preference filter: "
                f"kept={len(preferred_searches)} dropped={dropped_by_preferences} "
                f"dropped_language={pref_stats.get('dropped_language', 0)} "
                f"dropped_domain={pref_stats.get('dropped_domain', 0)}",
            )
        unique_searches = preferred_searches

        add_log(
            profile_id,
            "Provider plan validation: "
            f"input={len(searches)} kept={len(unique_searches)} "
            f"dropped_empty={dropped_empty_queries} dropped_duplicates={dropped_duplicate_queries}",
        )
        terminal_reason = None
        if not unique_searches:
            terminal_reason = (
                "no_queries_matching_preferences"
                if dropped_by_preferences
                else "no_explicit_queries"
            )

        if not cache_compatible:
            try:
                cache_payload = build_plan_cache_payload(
                    unique_searches,
                    input_fingerprint=input_fingerprint,
                    stats={"count": len(unique_searches)},
                )
                self.profile_repo.update(profile, {"cached_queries": cache_payload})
            except Exception as e:
                logger.warning(f"Failed to cache deterministic queries: {e}")

        # Update status with the actual plan details
        update_status(
            profile_id,
            total_searches=len(unique_searches),
            searches_generated=unique_searches,
            plan_unique_count=len(unique_searches),
            planner_mode="deterministic_explicit",
            plan_provenance="deterministic-explicit",
            terminal_reason=terminal_reason,
        )
        add_log(
            profile_id,
            f"Provider plan contains {len(unique_searches)} validated explicit queries.",
        )
        if profile.max_queries and len(unique_searches) < profile.max_queries:
            add_log(
                profile_id,
                f"⚠ Requested {profile.max_queries} queries but only {len(unique_searches)} unique queries were available after validation/deduplication",
            )
        return unique_searches

    async def _execute_searches(
        self, profile_id: int, profile, searches: list, provider_infos
    ) -> list:
        all_jobs: list = []
        execution_metrics = {
            "queries_without_provider": 0,
            "provider_failures": 0,
            "provider_successes": 0,
            "avam_fallback_count": 0,
        }
        execution_mode = (settings.SEARCH_EXECUTION_MODE or "sequential").strip().lower()
        query_concurrency = settings.SEARCH_CONCURRENCY if execution_mode == "immediate" else 1
        semaphore = asyncio.Semaphore(max(1, query_concurrency))
        provider_parallel = execution_mode == "immediate"
        add_log(profile_id, f"Execution mode: {execution_mode}")

        async def execute_single_search(idx: int, search: dict):
            async with semaphore:
                # Real-time stop check
                status_data = get_status(profile_id)
                if status_data.get("state") in STOP_STATES:
                    return []

                normalized_search, _ = normalize_search_item(search)
                if not normalized_search:
                    add_log(profile_id, f"⚠ Skipping invalid query payload at index {idx + 1}")
                    return []

                query = normalized_search.get("query", "")
                domain = normalized_search.get("domain", "general")
                query_type = normalized_search.get("type", "keyword")
                query_language = normalized_search.get("language", "en")

                profession_codes = []
                avam_fallback_keyword = False
                if query_type == "occupation":
                    profession_codes = await avam_mapper.resolve(query)
                    if not profession_codes:
                        avam_fallback_keyword = True
                        execution_metrics["avam_fallback_count"] += 1
                        add_log(
                            profile_id,
                            f"  ℹ AVAM found no codes for «{query}», JobRoom will use keyword fallback",
                        )

                compatible = route_provider_names(normalized_search, self.providers, provider_infos)
                if not compatible:
                    execution_metrics["queries_without_provider"] += 1
                    add_log(profile_id, f"⚠ No providers accept domain '{domain}' for «{query}»")
                    return []

                # Update status
                update_status(
                    profile_id, current_search_index=idx + 1, current_query=f"«{query}» ({domain})"
                )
                add_log(
                    profile_id,
                    f"Running query {idx + 1}/{len(searches)}: «{query}» on {', '.join(compatible)}",
                )

                async def search_provider(provider_name: str, req: JobSearchRequest):
                    provider = self.providers[provider_name]
                    if not provider:
                        return provider_name, [], None

                    provider_jobs = []
                    try:
                        current_page = 0
                        while True:
                            page_size = 50
                            if hasattr(provider, "capabilities") and hasattr(
                                provider.capabilities, "max_page_size"
                            ):
                                page_size = provider.capabilities.max_page_size

                            page_req = req.model_copy(
                                update={"page": current_page, "page_size": page_size}
                            )
                            result = await provider.search(page_req)
                            page_items = list(getattr(result, "items", []) or [])

                            for item in page_items:
                                # Mark the source query for tracking
                                if hasattr(item, "_source_query"):
                                    item._source_query = query
                                else:
                                    setattr(item, "_source_query", query)

                            provider_jobs.extend(page_items)

                            if not page_items:
                                break

                            total_pages = getattr(result, "total_pages", 1)
                            total_count = getattr(result, "total_count", None)
                            if total_pages and current_page >= total_pages - 1:
                                break
                            if (
                                total_count is not None
                                and total_count >= 0
                                and len(provider_jobs) >= total_count
                            ):
                                break

                            current_page += 1

                            if provider.throttle_delay > 0:
                                await asyncio.sleep(
                                    provider.throttle_delay
                                )  # Provider-level throttling

                            # Abort check
                            status_data = get_status(profile_id)
                            if status_data.get("state") in STOP_STATES:
                                break

                        return provider_name, provider_jobs, None
                    except Exception as e:
                        return provider_name, provider_jobs, e

                p_tasks = []
                for p_name in compatible:
                    provider = self.providers[p_name]
                    page_size = 50
                    if hasattr(provider, "capabilities") and hasattr(
                        provider.capabilities, "max_page_size"
                    ):
                        page_size = provider.capabilities.max_page_size

                    if p_name == "job_room" and avam_fallback_keyword:
                        req_fallback = build_search_request(
                            profile,
                            query,
                            [],
                            language=supported_request_language(query_language, provider),
                            page_size=page_size,
                            provider=provider,
                        )
                        p_tasks.append(search_provider(p_name, req_fallback))
                    else:
                        req = build_search_request(
                            profile,
                            query,
                            profession_codes,
                            language=supported_request_language(query_language, provider),
                            page_size=page_size,
                            provider=provider,
                        )
                        p_tasks.append(search_provider(p_name, req))

                if provider_parallel:
                    p_results = await asyncio.gather(*p_tasks)
                else:
                    p_results = []
                    for task in p_tasks:
                        p_results.append(await task)

                found_jobs = []
                for p_name, items, error in p_results:
                    if error:
                        execution_metrics["provider_failures"] += 1
                        self._increment_status_errors(profile_id)
                        add_log(profile_id, f"  ⚠ {p_name} failed: {str(error)[:100]}")
                    else:
                        execution_metrics["provider_successes"] += 1
                        found_jobs.extend(items)
                        add_log(profile_id, f"  ↳ {p_name}: {len(items)} jobs")

                return found_jobs

        results = await asyncio.gather(
            *(execute_single_search(i, q) for i, q in enumerate(searches))
        )

        seen_identity_keys: set[str] = set()
        seen_url_tokens: set[str] = set()
        seen_fuzzy_keys: set[str] = set()
        for batch in results:
            for job in batch:
                identity_key = listing_identity_key(job)
                url_token = listing_url_token(job)
                fuzzy_key = listing_fuzzy_key(job)

                if identity_key and identity_key in seen_identity_keys:
                    continue
                if url_token and url_token in seen_url_tokens:
                    continue
                if fuzzy_key and fuzzy_key in seen_fuzzy_keys:
                    continue

                all_jobs.append(job)
                if identity_key:
                    seen_identity_keys.add(identity_key)
                if url_token:
                    seen_url_tokens.add(url_token)
                if fuzzy_key:
                    seen_fuzzy_keys.add(fuzzy_key)

        update_status(
            profile_id,
            queries_without_provider=execution_metrics["queries_without_provider"],
            provider_failures=execution_metrics["provider_failures"],
            provider_successes=execution_metrics["provider_successes"],
            avam_fallback_count=execution_metrics["avam_fallback_count"],
        )

        return all_jobs

    async def _search_and_produce(
        self,
        profile_id: int,
        profile,
        searches: list,
        provider_infos: dict,
        job_queue: asyncio.Queue,
        profile_history: dict,
    ) -> tuple[int, int]:
        """Execute all search queries, deduplicate incrementally, persist each batch, and
        push it to job_queue for the consumer to normalize+filter+analyze concurrently.

        Returns (total_found, total_duplicates).
        """
        total_found = 0
        duplicate_counts = self._new_duplicate_counts()
        execution_metrics = {
            "queries_without_provider": 0,
            "provider_failures": 0,
            "provider_successes": 0,
            "avam_fallback_count": 0,
        }
        execution_mode = (settings.SEARCH_EXECUTION_MODE or "sequential").strip().lower()
        query_concurrency = settings.SEARCH_CONCURRENCY if execution_mode == "immediate" else 1
        semaphore = asyncio.Semaphore(max(1, query_concurrency))
        provider_parallel = execution_mode == "immediate"
        add_log(profile_id, f"Execution mode: {execution_mode}")

        # Mutable dedup state — shared across concurrent coroutines.
        # Safe in asyncio: check+add is always synchronous (no await between).
        dedup_state = self._new_run_dedup_state()
        active_query_indices: set[int] = set()
        completed_query_indices: set[int] = set()

        # Profile-history sets — mutated in-place so cross-query history dedup is cumulative.
        profile_history.setdefault("existing_fuzzy_keys_strong", set())
        applied_scraped_ids: set = profile_history["applied_scraped_ids"]

        async def execute_and_push(idx: int, search: dict):
            nonlocal total_found
            query_idx = idx + 1

            async with semaphore:
                status_data = get_status(profile_id)
                if status_data.get("state") in STOP_STATES:
                    return

                query_started = False
                try:
                    normalized_search, _ = normalize_search_item(search)
                    if not normalized_search:
                        add_log(profile_id, f"⚠ Skipping invalid query payload at index {idx + 1}")
                        return

                    query = normalized_search.get("query", "")
                    domain = normalized_search.get("domain", "general")
                    query_type = normalized_search.get("type", "keyword")
                    query_language = normalized_search.get("language", "en")

                    profession_codes = []
                    avam_fallback_keyword = False
                    if query_type == "occupation":
                        profession_codes = await avam_mapper.resolve(query)
                        if not profession_codes:
                            avam_fallback_keyword = True
                            execution_metrics["avam_fallback_count"] += 1
                            add_log(
                                profile_id,
                                f"  ℹ AVAM found no codes for «{query}», JobRoom will use keyword fallback",
                            )

                    compatible = route_provider_names(
                        normalized_search, self.providers, provider_infos
                    )
                    if not compatible:
                        execution_metrics["queries_without_provider"] += 1
                        add_log(
                            profile_id, f"⚠ No providers accept domain '{domain}' for «{query}»"
                        )
                        return

                    active_query_indices.add(query_idx)
                    query_started = True
                    update_status(
                        profile_id,
                        current_search_index=query_idx,
                        current_query=f"«{query}» ({domain})",
                        active_search_indices=sorted(active_query_indices),
                        searches_completed=len(completed_query_indices),
                        completed_search_indices=sorted(completed_query_indices),
                    )
                    add_log(
                        profile_id,
                        f"Running query {query_idx}/{len(searches)}: «{query}» on {', '.join(compatible)}",
                    )

                    async def search_provider(provider_name: str, req: JobSearchRequest):
                        provider = self.providers[provider_name]
                        if not provider:
                            return provider_name, [], None
                        provider_jobs = []
                        try:
                            current_page = 0
                            while True:
                                page_size = 50
                                if hasattr(provider, "capabilities") and hasattr(
                                    provider.capabilities, "max_page_size"
                                ):
                                    page_size = provider.capabilities.max_page_size
                                page_req = req.model_copy(
                                    update={"page": current_page, "page_size": page_size}
                                )
                                result = await provider.search(page_req)
                                page_items = list(getattr(result, "items", []) or [])
                                for item in page_items:
                                    if hasattr(item, "_source_query"):
                                        item._source_query = query
                                    else:
                                        setattr(item, "_source_query", query)
                                provider_jobs.extend(page_items)
                                if not page_items:
                                    break
                                total_pages = getattr(result, "total_pages", 1)
                                total_count = getattr(result, "total_count", None)
                                if total_pages and current_page >= total_pages - 1:
                                    break
                                if (
                                    total_count is not None
                                    and total_count >= 0
                                    and len(provider_jobs) >= total_count
                                ):
                                    break
                                current_page += 1
                                if provider.throttle_delay > 0:
                                    await asyncio.sleep(provider.throttle_delay)
                                status_data = get_status(profile_id)
                                if status_data.get("state") in STOP_STATES:
                                    break
                            return provider_name, provider_jobs, None
                        except Exception as e:
                            return provider_name, provider_jobs, e

                    p_tasks = []
                    for p_name in compatible:
                        provider = self.providers[p_name]
                        page_size = 50
                        if hasattr(provider, "capabilities") and hasattr(
                            provider.capabilities, "max_page_size"
                        ):
                            page_size = provider.capabilities.max_page_size
                        if p_name == "job_room" and avam_fallback_keyword:
                            req_fallback = build_search_request(
                                profile,
                                query,
                                [],
                                language=supported_request_language(query_language, provider),
                                page_size=page_size,
                                provider=provider,
                            )
                            p_tasks.append(search_provider(p_name, req_fallback))
                        else:
                            req = build_search_request(
                                profile,
                                query,
                                profession_codes,
                                language=supported_request_language(query_language, provider),
                                page_size=page_size,
                                provider=provider,
                            )
                            p_tasks.append(search_provider(p_name, req))

                    if provider_parallel:
                        p_results = await asyncio.gather(*p_tasks)
                    else:
                        p_results = []
                        for task in p_tasks:
                            p_results.append(await task)

                    found_jobs = []
                    for p_name, items, error in p_results:
                        if error:
                            execution_metrics["provider_failures"] += 1
                            add_log(profile_id, f"  ⚠ {p_name} failed: {str(error)[:100]}")
                        else:
                            execution_metrics["provider_successes"] += 1
                            found_jobs.extend(items)
                            add_log(profile_id, f"  ↳ {p_name}: {len(items)} jobs")

                    total_found += len(found_jobs)

                    # ── Incremental dedup: cross-query (T1-T3) + profile history ──
                    # All check+add operations are synchronous — no await between, so atomically safe.
                    new_unique: list = []
                    for job in found_jobs:
                        key = listing_identity_key(job)
                        url = listing_url_token(job)
                        fuzzy = listing_fuzzy_key(job)
                        desc_fp = listing_description_fingerprint(job)

                        duplicate_reason = self._duplicate_reason(
                            key=key,
                            url=url,
                            fuzzy=fuzzy,
                            desc_fp=desc_fp,
                            run_state=dedup_state,
                            history=profile_history,
                        )
                        if duplicate_reason:
                            self._increment_duplicate_count(duplicate_counts, duplicate_reason)
                            continue

                        self._record_dedup_markers(
                            key=key,
                            url=url,
                            fuzzy=fuzzy,
                            desc_fp=desc_fp,
                            run_state=dedup_state,
                            history=profile_history,
                        )

                        new_unique.append(job)

                    total_duplicates = self._duplicate_total(duplicate_counts)

                    update_status(
                        profile_id,
                        jobs_found=total_found,
                        jobs_duplicates=total_duplicates,
                        jobs_unique=total_found - total_duplicates,
                    )
                    self._update_duplicate_breakdown_status(profile_id, duplicate_counts)

                    if not new_unique:
                        return

                    # ── Persist this query's unique batch to the shared catalog ──
                    try:
                        await self._persist_scraped_job_catalog(profile_id, new_unique)
                    except Exception as persist_err:
                        self._increment_status_errors(profile_id)
                        logger.error(
                            "Failed to persist job batch for profile %s: %s",
                            profile_id,
                            persist_err,
                        )
                        add_log(profile_id, f"Persistence error for streamed batch: {persist_err}")
                        return

                    persisted_batch = [
                        job for job in new_unique if getattr(job, "_catalog_persisted", False)
                    ]
                    failed_catalog_count = len(new_unique) - len(persisted_batch)
                    if failed_catalog_count:
                        self._increment_status_errors(profile_id, failed_catalog_count)
                        add_log(
                            profile_id,
                            "Skipped "
                            f"{failed_catalog_count} job(s) because catalog persistence failed before analysis.",
                        )

                    if not persisted_batch:
                        return

                    # ── Set _applied_elsewhere flag (scraped_job_id is now assigned) ──
                    for job in persisted_batch:
                        scraped_id = getattr(job, "_scraped_job_id", None)
                        setattr(
                            job,
                            "_applied_elsewhere",
                            scraped_id is not None and scraped_id in applied_scraped_ids,
                        )

                    # Push batch to the consumer for normalization + filtering + analysis.
                    await job_queue.put(persisted_batch)
                finally:
                    if query_started:
                        active_query_indices.discard(query_idx)
                    completed_query_indices.add(query_idx)
                    update_status(
                        profile_id,
                        active_search_indices=sorted(active_query_indices),
                        searches_completed=len(completed_query_indices),
                        completed_search_indices=sorted(completed_query_indices),
                    )

        try:
            await asyncio.gather(*(execute_and_push(i, q) for i, q in enumerate(searches)))
        finally:
            # Always signal end-of-stream to unblock the consumer, even on error/stop.
            await job_queue.put(None)

        update_status(
            profile_id,
            queries_without_provider=execution_metrics["queries_without_provider"],
            provider_failures=execution_metrics["provider_failures"],
            provider_successes=execution_metrics["provider_successes"],
            avam_fallback_count=execution_metrics["avam_fallback_count"],
        )
        total_duplicates = self._duplicate_total(duplicate_counts)
        if total_duplicates > 0:
            add_log(
                profile_id,
                f"Deduplication: {total_found} found, {total_duplicates} duplicates, "
                f"{total_found - total_duplicates} unique",
            )
        return total_found, total_duplicates
