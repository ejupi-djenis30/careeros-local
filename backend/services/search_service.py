import asyncio
import hashlib
import inspect
import json
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
from backend.services.llm_service import llm_service
from backend.services.search.listing_utils import (
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


class SearchService:
    """Orchestrates the entire multi-step job search pipeline (Feature 1 & 4)."""

    def __init__(
        self,
        db: Session = None,
        job_repo=None,
        profile_repo=None,
        normalization_filter_engine: SearchNormalizationFilterEngine | None = None,
        search_persistence: SearchPipelinePersistence | None = None,
    ):
        self.db = db or getattr(job_repo, "db", None) or getattr(profile_repo, "db", None)
        self.job_repo = job_repo or (JobRepository(db) if db else None)
        self.profile_repo = profile_repo or (ProfileRepository(db) if db else None)
        self.normalization_filter_engine = (
            normalization_filter_engine or SearchNormalizationFilterEngine()
        )
        self.search_persistence = search_persistence or SearchPipelinePersistence(
            self.db,
            self.job_repo,
        )
        # Providers (registered by domain)
        self.providers = {
            "job_room": JobRoomProvider(),
            "swissdevjobs": SwissDevJobsProvider(),
            "local_db": LocalDbProvider(self.db) if self.db else None,
        }
        if AdeccoProvider:
            self.providers["adecco"] = AdeccoProvider()

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

    @staticmethod
    def _listing_application_field(listing: Any, field_name: str) -> Any:
        application = getattr(listing, "application", None)
        if application is None:
            return None
        if isinstance(application, dict):
            return application.get(field_name)
        return getattr(application, field_name, None)

    async def _normalize_persisted_jobs(self, profile_id: int, jobs: List[Any]) -> int:
        upgraded = await self.search_persistence.normalize_persisted_jobs(
            profile_id,
            jobs,
            normalize_job_batch=llm_service.normalize_job_batch,
        )

        if upgraded > 0:
            add_log(
                profile_id, f"Normalized {upgraded} persisted jobs with LLM structured extraction."
            )
        return upgraded

    # ─── Step 1.5: User/Candidate Profile Normalization ──────────────

    @staticmethod
    def _compute_profile_norm_fingerprint(
        cv_content: str, role_description: str, search_strategy: str
    ) -> str:
        payload = {
            "cv": str(cv_content or "")[:12000],
            "role": str(role_description or "")[:4000],
            "strategy": str(search_strategy or "")[:1200],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        ).hexdigest()

    async def _normalize_user_profile(
        self, profile_id: int, profile: SearchProfile, profile_dict: dict, force: bool = False
    ) -> dict:
        """Extract/retrieve the dual-signal normalized candidate profile.

        Retrieves from cache when fingerprint matches; otherwise calls the LLM.
        Returns a dict with BOTH candidate_profile fields (seniority, domain, skills etc.)
        AND search_intent fields (intent_domain, intent_seniority, open_to_unrelated etc.).
        """
        cv_content = str(profile_dict.get("cv_content") or "")
        role_description = str(profile_dict.get("role_description") or "")
        search_strategy = str(profile_dict.get("search_strategy") or "")

        if not cv_content and not role_description:
            return {}

        current_fp = self._compute_profile_norm_fingerprint(
            cv_content, role_description, search_strategy
        )
        cached_fp = getattr(profile, "profile_normalization_fingerprint", None)
        already_normalized = (
            getattr(profile, "profile_normalization_status", None) == "normalized"
            and cached_fp == current_fp
        )

        if already_normalized and not force:
            add_log(profile_id, "✓ Using cached candidate profile normalization (dual-signal)")
            return {
                # Candidate profile (CV facts)
                "seniority": profile.profile_normalized_seniority,
                "domain": profile.profile_normalized_domain,
                "role_family": profile.profile_normalized_role_family,
                "qualification_level": profile.profile_normalized_qualification_level,
                "experience_years": profile.profile_normalized_experience_years,
                "languages": profile.profile_normalized_languages or [],
                "skills": profile.profile_normalized_skills or [],
                # Search intent (what the user wants)
                "intent_domain": profile.profile_search_intent_domain,
                "intent_seniority": profile.profile_search_intent_seniority,
                "intent_role_family": profile.profile_search_intent_role_family,
                "intent_qualification_level": profile.profile_search_intent_qualification_level,
                "intent_skills": profile.profile_search_intent_skills or [],
                "open_to_unrelated": profile.profile_search_intent_open_to_unrelated or False,
                "intent_keywords": profile.profile_search_intent_keywords or [],
                # V2 enhanced candidate profile fields
                "role_type": getattr(profile, "profile_normalized_role_type", None),
                "industry_sectors": getattr(profile, "profile_normalized_industry_sectors", None)
                or [],
                "transferable_skills": getattr(
                    profile, "profile_normalized_transferable_skills", None
                )
                or [],
                # V2 enhanced search intent fields
                "intent_role_type": getattr(profile, "profile_search_intent_role_type", None),
                "intent_seniority_min": getattr(
                    profile, "profile_search_intent_seniority_min", None
                ),
                "intent_seniority_max": getattr(
                    profile, "profile_search_intent_seniority_max", None
                ),
                "dealbreakers": getattr(profile, "profile_search_intent_dealbreakers", None) or [],
                "flexibility": getattr(profile, "profile_search_intent_flexibility", None) or {},
            }

        try:
            normalized = await llm_service.normalize_user_profile(
                cv_content=cv_content,
                role_description=role_description,
                search_strategy=search_strategy,
            )
            if normalized:
                self.profile_repo.update_normalized_profile(
                    profile_id,
                    normalized_data=normalized,
                    fingerprint=current_fp,
                )
                add_log(
                    profile_id,
                    f"Candidate profile normalized: seniority={normalized.get('seniority')!r}, "
                    f"domain={normalized.get('domain')!r}, "
                    f"experience={normalized.get('experience_years')} yrs, "
                    f"qualification={normalized.get('qualification_level')!r} | "
                    f"intent: target_domain={normalized.get('intent_domain')!r}, "
                    f"open_to_unrelated={normalized.get('open_to_unrelated')!r}",
                )
            return normalized or {}
        except Exception as exc:
            # Unwrap tenacity RetryError so the real API error is visible in logs.
            from backend.services.llm_service import _unwrap_retry_error

            _, error_msg = _unwrap_retry_error(exc)
            logger.error(
                "Profile normalization failed for profile %s: %s",
                profile_id,
                error_msg,
                exc_info=True,
            )
            add_log(
                profile_id,
                f"⚠ Profile normalization failed (normalization filters will be skipped): {error_msg}",
            )
            return {}

    def _apply_structured_filters(
        self,
        profile_id: int,
        profile_dict: Dict[str, Any],
        jobs: List[Any],
        preferences: Dict[str, Any],
    ) -> List[Any]:
        if not jobs:
            return jobs

        kept: List[Any] = []
        dropped_reasons: Dict[str, int] = {}
        for job in jobs:
            ok, reason = self._passes_structured_filters(job, preferences, profile_dict)
            if ok:
                kept.append(job)
                continue
            dropped_reasons[reason] = dropped_reasons.get(reason, 0) + 1

        dropped_total = len(jobs) - len(kept)
        if dropped_total > 0:
            reasons_text = ", ".join(
                [f"{key}:{value}" for key, value in sorted(dropped_reasons.items())]
            )
            add_log(
                profile_id,
                f"Structured filtering dropped {dropped_total}/{len(jobs)} jobs. Reasons: {reasons_text}",
            )
        if kept:
            add_log(
                profile_id,
                f"Structured filtering kept {len(kept)} / {len(jobs)} jobs using persisted job facts and deterministic constraints.",
            )
        return kept

    def _passes_structured_filters(
        self, listing, preferences: Dict[str, Any], profile_dict: Dict[str, Any]
    ) -> tuple[bool, str]:
        normalized = getattr(listing, "_normalized_job_data", None)
        if not isinstance(normalized, dict):
            normalized = {}

        if preferences.get("remote_only"):
            mode_token = self._normalized_text_token(normalized.get("employment_mode", ""))
            is_remote_like = mode_token in {
                "remote",
                "hybrid",
                "home office",
                "telework",
                "teletravail",
            }
            if mode_token:
                if not is_remote_like:
                    return False, "remote_only"
            elif not listing_is_remote(listing):
                return False, "remote_only"

        salary_min = preferences.get("salary_min_chf")
        if salary_min is not None:
            normalized_salary_max = coerce_int(normalized.get("salary_max_chf"), None)
            if normalized_salary_max is None:
                normalized_salary_max = extract_salary_max_chf(listing)
            if normalized_salary_max is None or normalized_salary_max < salary_min:
                return False, "salary_min_chf"

        required_min, required_max = self._resolve_required_workload_range(
            profile_dict, preferences
        )
        if required_min is not None or required_max is not None:
            listing_min = coerce_int(normalized.get("workload_min"), None)
            listing_max = coerce_int(normalized.get("workload_max"), None)
            if listing_min is None or listing_max is None:
                employment = getattr(listing, "employment", None)
                listing_min = getattr(employment, "workload_min", None) if employment else None
                listing_max = getattr(employment, "workload_max", None) if employment else None
            if listing_min is None or listing_max is None:
                return False, "workload_missing"

            min_expected = required_min if required_min is not None else 0
            max_expected = required_max if required_max is not None else 100
            if listing_max < min_expected or listing_min > max_expected:
                return False, "workload_range"

        allowed_languages = set(preferences.get("preferred_languages") or [])
        if allowed_languages:
            required_languages = self._extract_required_language_codes(listing, normalized)
            if required_languages and required_languages.isdisjoint(allowed_languages):
                return False, "preferred_languages"

        # ── CEFR language level check ────────────────────────────────────
        # Drop jobs that require a language level the candidate clearly cannot meet
        # (gap >= 2 CEFR tiers). Uses normalized profile languages, so only active
        # when the profile has been normalized.
        profile_norm_for_lang = profile_dict.get("profile_normalization") or {}
        user_languages = profile_norm_for_lang.get("languages") or []
        if user_languages:
            ok, reason = self._check_language_level_mismatch(
                normalized.get("required_languages") or [], user_languages
            )
            if not ok:
                return False, reason

        hard_max_distance = preferences.get("hard_max_distance_km")
        if hard_max_distance is not None:
            origin_lat = profile_dict.get("latitude")
            origin_lon = profile_dict.get("longitude")
            location = getattr(listing, "location", None)
            coords = getattr(location, "coordinates", None) if location else None
            if origin_lat is None or origin_lon is None or not coords:
                return False, "distance_missing"
            distance = haversine_distance(origin_lat, origin_lon, coords.lat, coords.lon)
            if distance > hard_max_distance:
                return False, "distance_limit"

        # ── Normalization-based deterministic matching ──────────────────────
        # Only active when the feature flag is enabled AND:
        #   • the candidate profile has been successfully normalized, AND
        #   • the job itself has a confirmed `normalized` status.
        # Jobs with status `failed`, `pending`, `provider_bootstrap`, or missing
        # data are passed through here — the expensive MATCH step will assess them.
        if settings.SEARCH_ENABLE_NORMALIZATION_MATCHING:
            profile_norm = profile_dict.get("profile_normalization") or {}
            norm_status = normalized.get("status")
            if profile_norm and norm_status == "normalized":
                preference_signals = profile_dict.get("preference_signals") or {}
                ok, reason = self._passes_normalization_filters(
                    normalized, profile_norm, preference_signals
                )
                if not ok:
                    return False, reason

        return True, "ok"

    def _passes_normalization_filters(
        self,
        job_norm: Dict[str, Any],
        profile_norm: Dict[str, Any],
        preference_signals: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        return self.normalization_filter_engine.passes_normalization_filters(
            job_norm,
            profile_norm,
            preference_signals,
        )

    @staticmethod
    def _normalized_text_token(value: Any) -> str:
        from backend.services.search.listing_utils import normalized_text_token

        return normalized_text_token(value)

    def _resolve_required_workload_range(
        self, profile_dict: Dict[str, Any], preferences: Dict[str, Any]
    ) -> tuple[Optional[int], Optional[int]]:
        min_pref = preferences.get("workload_min")
        max_pref = preferences.get("workload_max")
        if min_pref is not None or max_pref is not None:
            return min_pref, max_pref

        workload_filter = str(profile_dict.get("workload_filter") or "").strip()
        if not workload_filter:
            return None, None
        match = re.match(r"^\s*(\d{1,3})\s*-\s*(\d{1,3})\s*$", workload_filter)
        if not match:
            return None, None
        try:
            min_value = int(match.group(1))
            max_value = int(match.group(2))
        except ValueError:
            return None, None
        if min_value > max_value:
            min_value, max_value = max_value, min_value
        return min_value, max_value

    def _extract_required_language_codes(self, listing, normalized: Dict[str, Any]) -> set[str]:
        codes: set[str] = set()
        for entry in normalized.get("required_languages") or []:
            if not isinstance(entry, dict):
                continue
            code = normalize_language(entry.get("code", ""))
            if code:
                codes.add(code)
        if codes:
            return codes

        for skill in getattr(listing, "language_skills", []) or []:
            code = normalize_language(getattr(skill, "language_code", ""))
            if code:
                codes.add(code)
        return codes

    # CEFR level rank — higher = better; native treated as C2 when comparing job requirements
    _CEFR_RANK: Dict[str, int] = {
        "a1": 1,
        "a2": 2,
        "b1": 3,
        "b2": 4,
        "c1": 5,
        "c2": 6,
        "native": 6,
    }

    @staticmethod
    def _normalize_cefr_level(level: str) -> str:
        """Normalize CEFR level variants to standard base form before rank lookup.

        Handles real-world variants from job postings:
        - Trailing modifiers: "B1+" → "B1", "C2-" → "C2"
        - Ranges: "B2/C1" → "B2", "B2-C1" → "B2" (takes the lower/first level)
        """
        if not level:
            return level
        import re as _re

        # Strip trailing +/- modifiers
        normalized = _re.sub(r"[+\-]+$", "", level.strip().lower())
        # For range formats (b2/c1 or b2-c1), keep only the lower (first) level
        normalized = _re.split(r"[/\-]", normalized)[0].strip()
        return normalized

    def _check_language_level_mismatch(
        self,
        required_languages: list,
        user_languages: list,
    ) -> tuple[bool, str]:
        """Return (False, reason) when a job's required language level exceeds the user's
        level by 2 or more CEFR tiers for any language both sides declare.

        A gap of 1 tier is within normal tolerance and is passed through so the MATCH
        LLM can make a nuanced decision. A gap of 2+ tiers (e.g. user A2, job C2) is a
        hard mismatch — the candidate cannot realistically meet the requirement.

        Only fires when the job has explicit CEFR levels in its required_languages AND
        the user's profile normalization has corresponding language entries with levels.
        """
        # Build a lookup: language_code → user_cefr_rank
        user_level_map: Dict[str, int] = {}
        for entry in user_languages:
            if not isinstance(entry, dict):
                continue
            code = str(entry.get("code", "") or "").strip().lower()
            level = str(entry.get("level", "") or "").strip().lower()
            rank = self._CEFR_RANK.get(self._normalize_cefr_level(level))
            if code and rank is not None:
                # Keep the highest level if a language appears multiple times
                if code not in user_level_map or rank > user_level_map[code]:
                    user_level_map[code] = rank

        if not user_level_map:
            return True, "ok"

        for req in required_languages:
            if not isinstance(req, dict):
                continue
            req_code = str(req.get("code", "") or "").strip().lower()
            req_level = str(req.get("level", "") or "").strip().lower()
            req_rank = self._CEFR_RANK.get(self._normalize_cefr_level(req_level))
            if not req_code or req_rank is None:
                continue  # no level stated — code-only check already handled above
            user_rank = user_level_map.get(req_code)
            if user_rank is None:
                continue  # user doesn't list this language at all — handled by code filter
            if req_rank - user_rank >= 2:
                return False, "language_level_mismatch"

        return True, "ok"

    def _build_degraded_fallback_plan(self, profile_dict: dict, profile) -> List[Dict[str, str]]:
        """Build a minimal executable plan when LLM returns no queries.

        This is a safety fallback and is intentionally conservative.
        """
        role_description = (profile_dict.get("role_description") or "").strip()
        search_strategy = (profile_dict.get("search_strategy") or "").strip()
        cv_content = (profile_dict.get("cv_content") or "").strip()
        if not role_description:
            return []

        max_by_profile = getattr(profile, "max_queries", None)
        configured_max = int(getattr(settings, "SEARCH_DEGRADED_PLAN_MAX_QUERIES", 3))
        if isinstance(max_by_profile, int) and max_by_profile > 0:
            max_count = max_by_profile
        elif configured_max > 0:
            max_count = configured_max
        else:
            max_count = None

        raw_candidates: List[Dict[str, Any]] = []

        # Primary occupation candidate from role description.
        raw_candidates.append(
            {
                "query": role_description,
                "type": "occupation",
                "domain": "general",
                "language": "en",
            }
        )

        # Split role description on common separators to capture concrete sub-roles.
        for token in re.split(r"[,;/|]", role_description):
            token = token.strip()
            if token and token.lower() != role_description.lower():
                raw_candidates.append(
                    {
                        "query": token,
                        "type": "occupation",
                        "domain": "general",
                        "language": "en",
                    }
                )

        keyword_pool = [
            "python",
            "java",
            "javascript",
            "typescript",
            "react",
            "docker",
            "sql",
            "aws",
        ]
        lower_text = f"{role_description} {search_strategy} {cv_content}".lower()
        for kw in keyword_pool:
            if kw in lower_text:
                raw_candidates.append(
                    {
                        "query": kw,
                        "type": "keyword",
                        "domain": "general",
                        "language": "en",
                    }
                )

        fallback_searches: List[Dict[str, str]] = []
        seen = set()
        configured_keyword_limit = int(getattr(settings, "SEARCH_DEGRADED_PLAN_MAX_KEYWORDS", 2))
        max_keywords = configured_keyword_limit if configured_keyword_limit > 0 else None
        keyword_count = 0
        for candidate in raw_candidates:
            normalized_search, _ = normalize_search_item(candidate)
            if not normalized_search:
                continue
            if (
                normalized_search.get("type") == "keyword"
                and max_keywords is not None
                and keyword_count >= max_keywords
            ):
                continue
            fingerprint = exact_query_fingerprint(normalized_search)
            if not fingerprint or fingerprint in seen:
                continue
            seen.add(fingerprint)
            fallback_searches.append(normalized_search)
            if normalized_search.get("type") == "keyword":
                keyword_count += 1
            if max_count is not None and len(fallback_searches) >= max_count:
                break

        return fallback_searches

    async def run_search(
        self,
        profile_id: int,
        force_regenerate_cv_summary: bool = False,
        force_regenerate_queries: bool = False,
        reservation_token: str | None = None,
    ):
        """Run the full search workflow for a saved profile."""
        if not self._activate_search_task(profile_id, reservation_token):
            logger.warning(
                "Aborting search startup for profile %d because task activation was rejected",
                profile_id,
            )
            release_task(profile_id, reservation_token)
            return

        # Ensure fresh LLM providers (reload config)
        llm_service.clear_provider_cache()

        try:
            await self._run_pipeline_with_timeout(
                profile_id,
                force_regenerate_cv_summary=force_regenerate_cv_summary,
                force_regenerate_queries=force_regenerate_queries,
            )
        except Exception as e:
            logger.error(
                f"Unexpected error in run_search for profile {profile_id}: {e}", exc_info=True
            )
            update_status(profile_id, state="error", error=f"Unexpected error: {e}")
        finally:
            await self._close_provider_resources()
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
                f"Pipeline exceeded maximum allowed time ({settings.SEARCH_PIPELINE_TIMEOUT_SECONDS}s). "
                "Search terminated.",
            )
            update_status(
                profile_id,
                state="error",
                terminal_reason="pipeline_timeout",
                error=f"Pipeline timed out after {settings.SEARCH_PIPELINE_TIMEOUT_SECONDS}s",
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

    async def _run_pipeline(
        self,
        profile_id: int,
        force_regenerate_cv_summary: bool = False,
        force_regenerate_queries: bool = False,
    ) -> None:
        """Execute the core search pipeline steps (wrapped by run_search with timeout)."""
        profile = self.profile_repo.get(profile_id)
        if not profile:
            logger.error(f"Profile {profile_id} not found")
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
        add_log(profile_id, "Step 1: Generating/Retrieving search plan...")

        provider_infos = {name: p.get_provider_info() for name, p in self.providers.items() if p}

        searches = await self._generate_plan(profile_id, profile_dict, profile, provider_infos)
        if not searches:
            status_data = get_status(profile_id)
            status_state = status_data.get("state")
            status_reason = status_data.get("terminal_reason")

            if status_state == "error":
                add_log(
                    profile_id,
                    f"[LLM_DEBUG] state=error terminal_reason={status_reason or 'llm_plan_error'} profile_id={profile_id}",
                )
                return

            enable_degraded_fallback = bool(
                getattr(settings, "SEARCH_ENABLE_DEGRADED_PLAN_FALLBACK", False)
            )
            if enable_degraded_fallback:
                degraded_searches = self._build_degraded_fallback_plan(profile_dict, profile)
                if degraded_searches:
                    searches = degraded_searches
                    add_log(
                        profile_id,
                        f"⚠ LLM returned no usable plan. Using degraded fallback plan with {len(searches)} query(s).",
                    )
                    add_log(
                        profile_id,
                        f"[LLM_DEBUG] degraded_plan_fallback profile_id={profile_id} queries={len(searches)}",
                    )
                    update_status(
                        profile_id,
                        terminal_reason="degraded_plan_fallback",
                        degraded_mode=True,
                        total_searches=len(searches),
                        searches_generated=searches,
                    )
                else:
                    add_log(
                        profile_id, "Degraded fallback plan did not produce executable queries."
                    )

            if searches:
                add_log(profile_id, "Continuing search with degraded fallback plan.")
            else:
                terminal_reason = status_reason or "no_queries"
                if terminal_reason == "no_valid_queries_after_filter":
                    add_log(
                        profile_id,
                        "LLM generated plan candidates, but all were filtered out as invalid/duplicates.",
                    )
                else:
                    add_log(profile_id, "No valid search queries were generated.")
                add_log(
                    profile_id,
                    f"[LLM_DEBUG] state=done terminal_reason={terminal_reason} profile_id={profile_id}",
                )
                update_status(profile_id, state="done", terminal_reason=terminal_reason)
                return

        # ── CV Summary (with caching Feature 3) ──
        cv_summary = ""
        if profile_dict.get("cv_content"):
            force_regen_cv = profile_dict.get("force_regenerate_cv_summary", False)
            if profile.cached_cv_summary and not force_regen_cv:
                cv_summary = profile.cached_cv_summary
                add_log(profile_id, "✓ Using cached CV summary")
            else:
                try:
                    cv_summary = await llm_service.summarize_cv(profile_dict["cv_content"])
                    add_log(profile_id, "CV summary generated for efficient analysis")
                    # Save to cache
                    self.profile_repo.update(profile, {"cached_cv_summary": cv_summary})
                except Exception as e:
                    logger.warning(f"CV summarization failed: {e}")
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
            profile_id, "Step 2+: Streaming search with real-time normalization and analysis..."
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
                    profile_id, "All provider searches failed before any jobs could be processed."
                )
                add_log(
                    profile_id,
                    f"[LLM_DEBUG] state=error terminal_reason=search_execution_failed profile_id={profile_id}",
                )
                update_status(
                    profile_id,
                    state="error",
                    terminal_reason="search_execution_failed",
                    error="All provider searches failed before any jobs could be processed.",
                )
                return
            add_log(profile_id, "No jobs found across all queries.")
            add_log(
                profile_id,
                f"[LLM_DEBUG] state=done terminal_reason=no_results profile_id={profile_id}",
            )
            update_status(profile_id, state="done", terminal_reason="no_results")
            return

        unique_total = total_found - total_duplicates
        if unique_total == 0:
            if history_duplicates == total_duplicates and total_duplicates > 0:
                add_log(profile_id, "All found jobs are already in profile history.")
                add_log(
                    profile_id,
                    f"[LLM_DEBUG] state=done terminal_reason=all_duplicates profile_id={profile_id}",
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
                    "All fetched jobs collapsed during runtime deduplication (no prior profile history).",
                )
                add_log(
                    profile_id,
                    f"[LLM_DEBUG] state=done terminal_reason=no_jobs_after_dedup profile_id={profile_id}",
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
            # Jobs are "explained" if they were filtered by structured rules OR if they
            # passed filters but were lost due to LLM analysis errors (already counted in
            # errors counter by _run_analysis_batches).  Only truly unexplained missing jobs
            # — where neither filtering nor analysis failure accounts for them — warrant a
            # pipeline_processing_failed terminal state.
            unexplained_unique = max(0, unique_total - total_filtered - analysis_failed)
            if status_metrics["errors"] > 0 and unexplained_unique > 0:
                add_log(
                    profile_id,
                    "Jobs were fetched but pipeline processing failed before analysis completed.",
                )
                add_log(
                    profile_id,
                    f"[LLM_DEBUG] state=error terminal_reason=pipeline_processing_failed profile_id={profile_id}",
                )
                update_status(
                    profile_id,
                    state="error",
                    terminal_reason="pipeline_processing_failed",
                    jobs_found=total_found,
                    jobs_duplicates=total_duplicates,
                    jobs_unique=total_found - total_duplicates,
                    jobs_skipped=total_filtered + analysis_skipped,
                    error="Jobs were fetched but pipeline processing failed before analysis completed.",
                )
            else:
                add_log(profile_id, "No jobs passed structured filtering and analysis.")
                add_log(
                    profile_id,
                    f"[LLM_DEBUG] state=done terminal_reason=no_jobs_after_structured_filters profile_id={profile_id}",
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

        # Jobs have already been saved progressively by the consumer.
        # Check whether any job made it through analysis but failed to persist.
        pre_finalize_errors = self._status_metrics(profile_id)["errors"]
        if consumer_saved == 0 and analyzed_pairs and pre_finalize_errors > 0:
            add_log(profile_id, "Jobs were analyzed but none could be persisted.")
            add_log(
                profile_id,
                f"[LLM_DEBUG] state=error terminal_reason=job_persistence_failed profile_id={profile_id}",
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
                error="Jobs were analyzed but none could be persisted.",
            )
            return

        # ── Step 6b: Optional final passes (critique/rerank/salary) ──
        # These passes refine analysis on already-saved rows; they are LLM-heavy and run
        # only once across all batches after the search stream completes.
        needs_final_pass = (
            getattr(settings, "MATCH_CRITIQUE_ENABLED", False)
            or getattr(settings, "MATCH_RERANK_ENABLED", False)
            or getattr(settings, "SALARY_BENCHMARK_ENABLED", False)
        )
        if needs_final_pass and analyzed_pairs:
            add_log(
                profile_id,
                f"Step 6b: Running final refinement passes ({len(analyzed_pairs)} jobs)...",
            )
            update_status(profile_id, state="analyzing")
            await self._finalize_and_save(profile_id, profile_dict, analyzed_pairs)

        saved_count = consumer_saved
        total_skipped = total_filtered + consumer_skipped + analysis_skipped
        add_log(
            profile_id, f"✓ Search complete – {saved_count} jobs saved, {consumer_skipped} skipped"
        )
        add_log(
            profile_id,
            f"[LLM_DEBUG] state=done terminal_reason=completed profile_id={profile_id} jobs_saved={saved_count} jobs_skipped={consumer_skipped}",
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

    # ───────────────────────── helper methods ─────────────────────────

    async def _generate_plan(
        self, profile_id: int, profile_dict: dict, profile, provider_infos
    ) -> list:
        preferences = self._profile_preferences(profile)
        # Feature 3: check cached queries
        force_regen_q = profile_dict.get("force_regenerate_queries", False)
        add_log(
            profile_id,
            "[LLM_DEBUG] plan_input "
            f"profile_id={profile_id} force_regenerate_queries={force_regen_q} "
            f"max_queries={profile.max_queries} max_occupation_queries={profile.max_occupation_queries} "
            f"max_keyword_queries={profile.max_keyword_queries} "
            f"role_description_len={len(profile_dict.get('role_description') or '')} "
            f"cv_content_len={len(profile_dict.get('cv_content') or '')}",
        )
        input_fingerprint = compute_plan_input_fingerprint(
            profile_dict,
            max_queries=profile.max_queries,
            max_occupation_queries=profile.max_occupation_queries,
            max_keyword_queries=profile.max_keyword_queries,
        )

        if profile.cached_queries and not force_regen_q:
            try:
                cached_searches, cache_meta = unpack_plan_cache_payload(profile.cached_queries)
                if is_cached_plan_compatible(cache_meta, input_fingerprint):
                    searches = cached_searches
                    add_log(profile_id, f"✓ Using {len(searches)} cached queries")
                    update_status(profile_id, plan_cache_hit=1, plan_cache_miss=0)
                else:
                    searches = []
                    add_log(profile_id, "Cached queries ignored because planning inputs changed.")
                    update_status(profile_id, plan_cache_hit=0, plan_cache_miss=1)
            except Exception as e:
                logger.error(f"Failed to parse cached queries: {e}")
                searches = []
                update_status(profile_id, plan_cache_hit=0, plan_cache_miss=1)
        else:
            searches = []
            update_status(profile_id, plan_cache_hit=0, plan_cache_miss=1)

        if not searches:
            try:
                searches = await llm_service.generate_search_plan(
                    profile_dict,
                    list(provider_infos.values()),
                    max_queries=profile.max_queries,
                    max_occupation_queries=profile.max_occupation_queries,
                    max_keyword_queries=profile.max_keyword_queries,
                )
                add_log(
                    profile_id,
                    f"[LLM_DEBUG] plan_raw_output_count={len(searches) if searches else 0}",
                )
                update_status(profile_id, plan_raw_count=len(searches) if searches else 0)
            except Exception as e:
                logger.error(f"LLM keyword generation failed: {e}")
                error_text = str(e).lower()
                terminal_reason = "llm_plan_error"
                if "rate limit" in error_text or "rate_limit" in error_text:
                    terminal_reason = "llm_plan_rate_limited"
                update_status(
                    profile_id, state="error", terminal_reason=terminal_reason, error=str(e)
                )
                return []

            if not searches:
                return []

            # Save queries to cache (Feature 3)
            try:
                cache_payload = build_plan_cache_payload(
                    searches,
                    input_fingerprint=input_fingerprint,
                    stats={"count": len(searches)},
                )
                self.profile_repo.update(profile, {"cached_queries": cache_payload})
            except Exception as e:
                logger.warning(f"Failed to cache queries: {e}")

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
                "[LLM_DEBUG] plan_preference_filter "
                f"kept={len(preferred_searches)} dropped={dropped_by_preferences} "
                f"dropped_language={pref_stats.get('dropped_language', 0)} "
                f"dropped_domain={pref_stats.get('dropped_domain', 0)}",
            )
        unique_searches = preferred_searches

        add_log(
            profile_id,
            "[LLM_DEBUG] plan_filter_stats "
            f"input={len(searches)} kept={len(unique_searches)} "
            f"dropped_empty={dropped_empty_queries} dropped_duplicates={dropped_duplicate_queries}",
        )
        if searches and not unique_searches:
            terminal_reason = "no_valid_queries_after_filter"
            if dropped_by_preferences:
                terminal_reason = "no_queries_matching_preferences"
            update_status(profile_id, terminal_reason=terminal_reason)

        # Update status with the actual plan details
        update_status(
            profile_id,
            total_searches=len(unique_searches),
            searches_generated=unique_searches,
            plan_unique_count=len(unique_searches),
        )
        add_log(profile_id, f"Generated {len(searches)} queries → {len(unique_searches)} unique")
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

    async def _analyze_and_save(
        self, profile_id: int, profile_dict: dict, unique_jobs: list
    ) -> tuple[int, int]:
        semaphore = asyncio.Semaphore(settings.ANALYSIS_CONCURRENCY)
        batch_size = settings.ANALYSIS_BATCH_SIZE
        batches = [unique_jobs[i : i + batch_size] for i in range(0, len(unique_jobs), batch_size)]

        origin_coords = None
        if profile_dict.get("latitude") and profile_dict.get("longitude"):
            origin_coords = (profile_dict["latitude"], profile_dict["longitude"])

        async def analyze_batch(batch):
            async with semaphore:
                status_data = get_status(profile_id)
                if status_data.get("state") in ["stopped", "cancelled", "finished", "failed"]:
                    return []

                jobs_metadata = []
                for job in batch:
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

                    education_info = []
                    for occ in getattr(job, "occupations", []):
                        if getattr(occ, "education_code", None):
                            education_info.append(f"Edu: {occ.education_code}")

                    company_obj = getattr(job, "company", None)
                    company_name = company_obj.name if hasattr(company_obj, "name") else "Unknown"

                    # Include pre-computed normalized facts so the MATCH LLM has
                    # structured data instead of re-extracting it from raw text.
                    raw_norm = getattr(job, "_normalized_job_data", None) or {}
                    normalized_data = {
                        "domain": raw_norm.get("domain"),
                        "role_type": raw_norm.get("role_type")
                        or raw_norm.get("normalized_role_type"),
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

                    jobs_metadata.append(
                        {
                            "title": getattr(job, "title", "Unknown"),
                            "description": await llm_service._compress_description_if_needed(
                                desc_text, settings.MAX_DESCRIPTION_CHARS
                            ),
                            "location": job.location.city
                            if getattr(job, "location", None)
                            else "Unknown",
                            "workload": f"{job.employment.workload_min}-{job.employment.workload_max}%"
                            if getattr(job, "employment", None)
                            else "Unknown",
                            "languages": [
                                f"{s.language_code} ({s.spoken_level})"
                                for s in getattr(job, "language_skills", [])
                            ]
                            if getattr(job, "language_skills", None)
                            else [],
                            "education": ", ".join(education_info)
                            if education_info
                            else "None specified",
                            "company": company_name,
                            "normalized_data": normalized_data,
                        }
                    )

                try:
                    results = await llm_service.analyze_job_batch(jobs_metadata, profile_dict)
                    return list(zip(batch, results))
                except Exception as e:
                    logger.error(f"Analysis batch failed: {e}")
                    return []

        tasks = [analyze_batch(batch) for batch in batches]
        results = await asyncio.gather(*tasks)

        # Re-check cancellation: a stop/cancel request arriving during gather should
        # prevent us from persisting analysis results that are now unwanted.
        post_gather_status = get_status(profile_id)
        if post_gather_status.get("state") in STOP_STATES:
            add_log(profile_id, "Search was stopped during analysis — discarding results.")
            return 0, len(unique_jobs)

        jobs_to_persist = [item for batch_result in results for item in batch_result]

        # ── Phase 3.2: Two-pass critique for borderline scores ─────────────
        critique_enabled = getattr(settings, "MATCH_CRITIQUE_ENABLED", False)
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
        rerank_enabled = getattr(settings, "MATCH_RERANK_ENABLED", False)
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
        if getattr(settings, "SALARY_BENCHMARK_ENABLED", False):
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

    # ─── Streaming pipeline helpers ───────────────────────────────────────

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
            except Exception as norm_err:
                from backend.services.llm_service import _unwrap_retry_error

                _, err_msg = _unwrap_retry_error(norm_err)
                logger.warning(
                    "LLM normalization failed for profile %s batch — proceeding without full normalization: %s",
                    profile_id,
                    err_msg,
                )
                add_log(
                    profile_id,
                    f"⚠ Normalization warning (batch proceeds without field-level filters): {err_msg}",
                )

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
                # Wait for recovery window instead of permanent skip
                recovery_wait = float(settings.CIRCUIT_BREAKER_RECOVERY_SECONDS) + 2.0
                add_log(
                    profile_id,
                    f"⚠ MATCH circuit breaker is open — waiting {recovery_wait}s for recovery...",
                )
                await asyncio.sleep(recovery_wait)

                # Check again after waiting
                if llm_service.is_analysis_circuit_open():
                    analysis_failed += analysis_input_count
                    total_analysis_skipped += analysis_input_count
                    cumulative_to_analyze += analysis_input_count
                    cumulative_skipped += analysis_input_count
                    add_log(
                        profile_id,
                        "⚠ MATCH circuit breaker is still open — skipping analysis for "
                        f"{analysis_input_count} job(s).",
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
            analysis_failed += analysis_input_count - len(batch_pairs)
            cumulative_to_analyze += analysis_input_count
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
                    await self._save_single_job(
                        listing, analysis, profile_dict, origin_coords, commit=True
                    )
                    batch_saved += 1
                except Exception as save_exc:
                    self._increment_status_errors(profile_id)
                    logger.warning(
                        "Progressive save failed for profile %s: %s",
                        profile_id,
                        save_exc,
                    )
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

    async def _run_analysis_batches(self, profile_id: int, profile_dict: dict, jobs: list) -> list:
        """Run LLM match analysis on a list of jobs using concurrent internal batches.

        Returns a list of (job_listing, analysis_dict) pairs.
        Critique, reranking, and salary benchmark are *not* applied here —
        they are handled once across all batches by _finalize_and_save.
        """
        # Clamp concurrency to prevent mass LLM timeouts that trip the circuit breaker
        safe_concurrency = max(1, int(settings.ANALYSIS_CONCURRENCY))
        semaphore = asyncio.Semaphore(safe_concurrency)
        batch_size = settings.ANALYSIS_BATCH_SIZE
        batches = [jobs[i : i + batch_size] for i in range(0, len(jobs), batch_size)]

        async def analyze_batch(batch):
            async with semaphore:
                status_data = get_status(profile_id)
                if status_data.get("state") in STOP_STATES:
                    return []

                jobs_metadata = []
                for job in batch:
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

                    education_info = []
                    for occ in getattr(job, "occupations", []):
                        if getattr(occ, "education_code", None):
                            education_info.append(f"Edu: {occ.education_code}")

                    company_obj = getattr(job, "company", None)
                    company_name = company_obj.name if hasattr(company_obj, "name") else "Unknown"

                    raw_norm = getattr(job, "_normalized_job_data", None) or {}
                    normalized_data = {
                        "domain": raw_norm.get("domain"),
                        "role_type": raw_norm.get("role_type")
                        or raw_norm.get("normalized_role_type"),
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
                    jobs_metadata.append(
                        {
                            "title": getattr(job, "title", "Unknown"),
                            "description": await llm_service._compress_description_if_needed(
                                desc_text, settings.MAX_DESCRIPTION_CHARS
                            ),
                            "location": job.location.city
                            if getattr(job, "location", None)
                            else "Unknown",
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
                            "education": ", ".join(education_info)
                            if education_info
                            else "None specified",
                            "company": company_name,
                            "normalized_data": normalized_data,
                        }
                    )

                try:
                    results = await llm_service.analyze_job_batch(jobs_metadata, profile_dict)
                    return list(zip(batch, results))
                except CircuitOpenError as exc:
                    logger.warning(
                        "Analysis batch skipped for profile %s because match circuit is open: %s",
                        profile_id,
                        exc,
                    )
                    return []
                except Exception as e:
                    self._increment_status_errors(profile_id)
                    logger.error(f"Analysis batch failed: {e}")
                    return []

        tasks = [analyze_batch(b) for b in batches]
        results = await asyncio.gather(*tasks)
        return [item for batch_result in results for item in batch_result]

    async def _finalize_and_save(
        self,
        profile_id: int,
        profile_dict: dict,
        analyzed_pairs: list,
    ) -> None:
        """Apply optional critique, reranking, and salary benchmark to already-persisted jobs.

        Jobs have already been saved to the 'jobs' table progressively by _processing_consumer.
        This phase only refines analysis fields on existing rows when global passes
        (critique / rerank / salary benchmark) are enabled.  It is a no-op when all
        those settings are disabled.

        Receives (job, analysis) pairs carrying the initial analysis values together with
        ._scraped_job_id attributes stamped by _upsert_scraped_job.
        """
        post_status = get_status(profile_id)
        if post_status.get("state") in STOP_STATES:
            add_log(profile_id, "Search was stopped — skipping final refinement passes.")
            return

        needs_final_pass = (
            getattr(settings, "MATCH_CRITIQUE_ENABLED", False)
            or getattr(settings, "MATCH_RERANK_ENABLED", False)
            or getattr(settings, "SALARY_BENCHMARK_ENABLED", False)
        )
        if not needs_final_pass or not analyzed_pairs:
            return

        jobs_to_refine = list(analyzed_pairs)
        analysis_targets = [
            {"title": getattr(job, "title", "Unknown")} for job, _ in jobs_to_refine
        ]
        if analysis_targets:
            update_status(
                profile_id,
                analysis_targets=analysis_targets,
                analysis_current_index=1,
                jobs_analyze_total=len(analysis_targets),
                jobs_analyzed=0,
            )

        # ── Phase: Two-pass critique for borderline scores ────────────────
        critique_enabled = getattr(settings, "MATCH_CRITIQUE_ENABLED", False)
        critique_min = int(getattr(settings, "MATCH_CRITIQUE_SCORE_RANGE_MIN", 40))
        critique_max = int(getattr(settings, "MATCH_CRITIQUE_SCORE_RANGE_MAX", 80))
        if critique_enabled and jobs_to_refine:
            borderline = [
                (i, job, analysis)
                for i, (job, analysis) in enumerate(jobs_to_refine)
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
                        jobs_to_refine[orig_idx] = (jobs_to_refine[orig_idx][0], critiqued_analysis)
                    add_log(profile_id, f"Critique pass refined {len(borderline)} borderline jobs.")
                except Exception as exc:
                    logger.warning("[CRITIQUE] Critique pass failed: %s", exc)

        # ── Phase: Comparative re-ranking of top-N jobs ──────────────────
        rerank_enabled = getattr(settings, "MATCH_RERANK_ENABLED", False)
        rerank_top_n = int(getattr(settings, "MATCH_RERANK_TOP_N", 20))
        if rerank_enabled and len(jobs_to_refine) >= 3:
            try:
                scored_with_index = sorted(
                    enumerate(jobs_to_refine),
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
                        and 0 <= orig_idx < len(jobs_to_refine)
                    ):
                        job, analysis = jobs_to_refine[orig_idx]
                        updated = dict(analysis)
                        updated["affinity_score"] = final_score
                        updated["worth_applying"] = (
                            bool(analysis.get("worth_applying", False)) and final_score >= 65
                        )
                        jobs_to_refine[orig_idx] = (job, updated)
                add_log(profile_id, f"Re-ranked top {len(reranked)} jobs for calibration.")
            except Exception as exc:
                logger.warning("[RERANK] Re-rank pass failed: %s", exc)

        # ── Phase: Deterministic salary_below_market red flag injection ──
        if getattr(settings, "SALARY_BENCHMARK_ENABLED", False):
            try:
                from backend.services.preference_service import compute_salary_benchmark

                for idx, (job, analysis) in enumerate(jobs_to_refine):
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
                            jobs_to_refine[idx] = (job, updated)
            except Exception:
                logger.debug("salary_below_market check skipped (non-critical)")

        def report_refinement_progress(current_index: int, title: str) -> None:
            update_status(
                profile_id,
                analysis_current_index=current_index,
                jobs_analyzed=max(0, current_index - 1),
            )

        updated_count = self.search_persistence.apply_refined_analysis_updates(
            profile_id,
            profile_dict,
            jobs_to_refine,
            increment_status_errors=self._increment_status_errors,
            report_progress=report_refinement_progress,
        )

        if analysis_targets:
            update_status(
                profile_id,
                analysis_targets=analysis_targets,
                analysis_current_index=len(analysis_targets),
                jobs_analyze_total=len(analysis_targets),
                jobs_analyzed=len(analysis_targets),
            )

        if updated_count > 0:
            add_log(profile_id, f"Final passes applied: {updated_count} jobs refined in-place.")


def get_search_service(db: Session) -> SearchService:
    return SearchService(db)
