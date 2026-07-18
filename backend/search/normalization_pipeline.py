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
from backend.jobs.matching import deterministic_job_match
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


class NormalizationMixin:
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
            resolve_runtime_policy=llm_service.get_step_runtime_policy,
        )

        if upgraded > 0:
            add_log(
                profile_id, f"Normalized {upgraded} persisted jobs with LLM structured extraction."
            )
        return upgraded

    @staticmethod
    def _compute_profile_norm_fingerprint(
        cv_content: str, role_description: str, search_strategy: str
    ) -> str:
        return build_profile_normalization_fingerprint(
            cv_content,
            role_description,
            search_strategy,
        )

    def _ensure_match_profile_snapshot(
        self,
        profile_id: int,
        profile: SearchProfile,
        profile_dict: dict,
        profile_normalization: dict,
        *,
        force: bool = False,
    ) -> str:
        cv_content = str(profile_dict.get("cv_content") or "")
        role_description = str(profile_dict.get("role_description") or "")
        search_strategy = str(profile_dict.get("search_strategy") or "")
        cv_summary = str(profile_dict.get("cv_summary") or "")
        snapshot_fingerprint = self._compute_profile_norm_fingerprint(
            cv_content,
            role_description,
            search_strategy,
        )
        cached_snapshot = getattr(profile, "cached_profile_snapshot", None)
        cached_fingerprint = getattr(profile, "cached_profile_snapshot_fingerprint", None)

        if cached_snapshot and cached_fingerprint == snapshot_fingerprint and not force:
            add_log(profile_id, "✓ Using cached compact MATCH profile snapshot")
            return cached_snapshot

        runtime_policy = llm_service.get_step_runtime_policy("match")
        snapshot_max_chars = (
            int(getattr(settings, "SEARCH_LOW_CONTEXT_PROFILE_SNAPSHOT_MAX_CHARS", 700) or 700)
            if runtime_policy.get("low_context")
            else int(getattr(settings, "SEARCH_PROFILE_SNAPSHOT_MAX_CHARS", 1000) or 1000)
        )
        snapshot = build_profile_match_snapshot(
            role_description=role_description,
            search_strategy=search_strategy,
            cv_summary=cv_summary,
            profile_normalization=profile_normalization,
            max_chars=snapshot_max_chars,
        )
        if snapshot:
            self.profile_repo.update(
                profile,
                {
                    "cached_profile_snapshot": snapshot,
                    "cached_profile_snapshot_fingerprint": snapshot_fingerprint,
                },
            )
        return snapshot

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
        from backend.search.normalization.listings import normalized_text_token

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
