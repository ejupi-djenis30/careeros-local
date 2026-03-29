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
from backend.models import Job, ScrapedJob, SearchProfile
from backend.providers.jobs.jobroom.client import JobRoomProvider
from backend.providers.jobs.swissdevjobs.client import SwissDevJobsProvider
from backend.repositories.job_repository import JobRepository
from backend.repositories.profile_repository import ProfileRepository
from backend.services.llm_service import llm_service
from backend.services.search.listing_utils import (
    _word_bounded_substring,
    bootstrap_normalized_job_data,
    coerce_int,
    coerce_string_list,
    compute_posting_quality,
    compute_prescore,
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
    normalized_text_token,
    parse_listing_publication_date,
    semantic_skills_score,
)
from backend.services.search.search_validator import build_search_request
from backend.services.utils import (
    clean_html_tags,
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

    def __init__(self, db: Session = None, job_repo=None, profile_repo=None):
        self.db = db or getattr(job_repo, "db", None) or getattr(profile_repo, "db", None)
        self.job_repo = job_repo or (JobRepository(db) if db else None)
        self.profile_repo = profile_repo or (ProfileRepository(db) if db else None)
        # Providers (registered by domain)
        self.providers = {
            "job_room": JobRoomProvider(),
            "swissdevjobs": SwissDevJobsProvider(),
            "local_db": LocalDbProvider(self.db) if self.db else None
        }
        if AdeccoProvider:
            self.providers["adecco"] = AdeccoProvider()


    def _profile_preferences(self, profile) -> Dict[str, Any]:
        remote_pref = get_profile_preference(profile, "remote_only", False)
        return {
            "preferred_languages": coerce_string_list(get_profile_preference(profile, "preferred_languages"), normalize_language),
            "preferred_domains": coerce_string_list(get_profile_preference(profile, "preferred_domains"), normalize_domain),
            "remote_only": remote_pref if isinstance(remote_pref, bool) else False,
            "salary_min_chf": coerce_int(get_profile_preference(profile, "salary_min_chf"), None),
            "workload_min": coerce_int(get_profile_preference(profile, "workload_min"), None),
            "workload_max": coerce_int(get_profile_preference(profile, "workload_max"), None),
            "hard_max_distance_km": coerce_int(get_profile_preference(profile, "hard_max_distance_km"), None),
        }

    def _apply_query_preferences(self, searches: List[Dict[str, Any]], preferences: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
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
        platform = getattr(listing, "source", None) or getattr(listing, "platform", "unknown")
        platform_id = str(getattr(listing, "id", "") or getattr(listing, "platform_job_id", ""))

        existing_sj = self.db.query(ScrapedJob).filter(
            ScrapedJob.platform == platform,
            ScrapedJob.platform_job_id == platform_id,
        ).first()

        desc_text = extract_listing_description_text(listing)
        company_name = extract_company_name(listing) or "Unknown"
        location_str = extract_listing_location_string(listing)
        workload_str = extract_listing_workload_string(listing)
        pub_date = parse_listing_publication_date(listing, platform, platform_id)
        normalized_bootstrap = bootstrap_normalized_job_data(
            listing,
            desc_text=desc_text,
            company_name=company_name,
            location_str=location_str,
        )

        created = False
        if not existing_sj:
            existing_sj = ScrapedJob(
                platform=platform,
                platform_job_id=platform_id,
                title=clean_html_tags(getattr(listing, "title", "Unknown")),
                company=company_name,
                description=clean_html_tags(desc_text) if desc_text else None,
                location=location_str,
                external_url=getattr(listing, "external_url", None) or getattr(listing, "url", None) or platform_id,
                application_url=getattr(listing, "application", None).form_url if getattr(listing, "application", None) else None,
                application_email=getattr(listing, "application", None).email if getattr(listing, "application", None) else None,
                workload=workload_str or None,
                publication_date=pub_date,
                source_query=getattr(listing, "_source_query", "Unknown"),
                **normalized_bootstrap,
            )
            self.db.add(existing_sj)
            self.db.flush()
            created = True
        else:
            refresh_fields = {
                "description": clean_html_tags(desc_text) if desc_text else None,
                "location": location_str or None,
                "application_url": getattr(listing, "application", None).form_url if getattr(listing, "application", None) else None,
                "application_email": getattr(listing, "application", None).email if getattr(listing, "application", None) else None,
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
        return existing_sj, created

    async def _persist_scraped_job_catalog(self, profile_id: int, jobs: list) -> tuple[int, int]:
        if not jobs:
            return 0, 0

        created = 0
        updated = 0
        try:
            for listing in jobs:
                _, was_created = self._upsert_scraped_job(listing)
                if was_created:
                    created += 1
                else:
                    updated += 1
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.error("Failed to persist scraped job catalog for profile %s: %s", profile_id, exc)
            raise

        add_log(profile_id, f"Persisted shared job catalog entries before filtering: {created} created, {updated} refreshed")
        return created, updated

    async def _normalize_persisted_jobs(self, profile_id: int, jobs: List[Any]) -> int:
        if not jobs:
            return 0

        candidates: List[Dict[str, Any]] = []
        candidate_records: List[ScrapedJob] = []

        # Batch-load all referenced ScrapedJob records in a single IN query
        all_scraped_ids = [
            getattr(listing, "_scraped_job_id", None)
            for listing in jobs
        ]
        all_scraped_ids = [sid for sid in all_scraped_ids if sid is not None]
        scraped_jobs_by_id: Dict[int, ScrapedJob] = {}
        if all_scraped_ids:
            batch = self.db.query(ScrapedJob).filter(ScrapedJob.id.in_(all_scraped_ids)).all()
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

        # ── Chunked normalization: send candidates in small batches to avoid
        # context-limit errors (APIStatusError) that would fail the entire batch.
        batch_size = max(1, settings.NORMALIZE_BATCH_SIZE)
        normalized_rows: List[Dict[str, Any]] = []
        for chunk_start in range(0, len(candidates), batch_size):
            chunk = candidates[chunk_start: chunk_start + batch_size]
            try:
                chunk_result = await llm_service.normalize_job_batch(chunk)
                normalized_rows.extend(chunk_result)
            except Exception as batch_err:
                logger.warning(
                    "[NORMALIZE] Batch %d-%d failed for profile %s, skipping chunk: %s",
                    chunk_start, chunk_start + len(chunk) - 1, profile_id, batch_err,
                )
                # Pad with empty dicts so indices stay aligned with candidate_records
                normalized_rows.extend([{} for _ in chunk])

        upgraded = 0
        for scraped_job, normalized in zip(candidate_records, normalized_rows):
            if not normalized:
                # Batch failed for this job — leave normalization_status unchanged
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
            # V2 enhanced job normalization fields
            scraped_job.normalized_preferred_skills = normalized.get("preferred_skills") or None
            scraped_job.normalized_soft_skills = normalized.get("soft_skills") or None
            scraped_job.normalized_physical_requirements = normalized.get("physical_requirements") or None
            scraped_job.normalized_entry_barrier = normalized.get("entry_barrier")
            scraped_job.normalized_career_changer_friendly = normalized.get("career_changer_friendly")
            scraped_job.normalized_hard_blockers = normalized.get("hard_blockers") or None

            metadata = scraped_job.normalized_metadata or {}
            metadata.update({"llm_normalized": True, "source": "llm_normalizer"})
            scraped_job.normalized_metadata = metadata

            # ── Phase 4.1: Compute and store posting quality score ────────
            if scraped_job.posting_quality is None and scraped_job.description:
                try:
                    scraped_job.posting_quality = compute_posting_quality(scraped_job.description)
                except Exception:
                    pass

            upgraded += 1

        self.db.commit()

        # Propagate normalized_job_data from already-updated in-memory records
        # (avoids a second per-job DB round-trip after the commit)
        for listing in jobs:
            scraped_job_id = getattr(listing, "_scraped_job_id", None)
            if not scraped_job_id:
                continue
            scraped_job = scraped_jobs_by_id.get(scraped_job_id)
            if scraped_job:
                setattr(listing, "_normalized_job_data", scraped_job.normalized_job_data)

        if upgraded > 0:
            add_log(profile_id, f"Normalized {upgraded} persisted jobs with LLM structured extraction.")
        return upgraded

    # ─── Step 1.5: User/Candidate Profile Normalization ──────────────

    @staticmethod
    def _compute_profile_norm_fingerprint(cv_content: str, role_description: str, search_strategy: str) -> str:
        payload = {
            "cv": str(cv_content or "")[:12000],
            "role": str(role_description or "")[:4000],
            "strategy": str(search_strategy or "")[:1200],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        ).hexdigest()

    async def _normalize_user_profile(self, profile_id: int, profile: SearchProfile, profile_dict: dict, force: bool = False) -> dict:
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

        current_fp = self._compute_profile_norm_fingerprint(cv_content, role_description, search_strategy)
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
                "industry_sectors": getattr(profile, "profile_normalized_industry_sectors", None) or [],
                "transferable_skills": getattr(profile, "profile_normalized_transferable_skills", None) or [],
                # V2 enhanced search intent fields
                "intent_role_type": getattr(profile, "profile_search_intent_role_type", None),
                "intent_seniority_min": getattr(profile, "profile_search_intent_seniority_min", None),
                "intent_seniority_max": getattr(profile, "profile_search_intent_seniority_max", None),
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
            from tenacity import RetryError
            from backend.services.llm_service import _unwrap_retry_error
            _, error_msg = _unwrap_retry_error(exc)
            logger.error(
                "Profile normalization failed for profile %s: %s",
                profile_id, error_msg, exc_info=True,
            )
            add_log(profile_id, f"⚠ Profile normalization failed (normalization filters will be skipped): {error_msg}")
            return {}

    def _apply_structured_filters(self, profile_id: int, profile_dict: Dict[str, Any], jobs: List[Any], preferences: Dict[str, Any]) -> List[Any]:
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
            reasons_text = ", ".join([f"{key}:{value}" for key, value in sorted(dropped_reasons.items())])
            add_log(
                profile_id,
                f"Structured filtering dropped {dropped_total}/{len(jobs)} jobs. Reasons: {reasons_text}",
            )
        if kept:
            add_log(profile_id, f"Structured filtering kept {len(kept)} / {len(jobs)} jobs using persisted job facts and deterministic constraints.")
        return kept

    def _passes_structured_filters(self, listing, preferences: Dict[str, Any], profile_dict: Dict[str, Any]) -> tuple[bool, str]:
        normalized = getattr(listing, "_normalized_job_data", None)
        if not isinstance(normalized, dict):
            normalized = {}

        if preferences.get("remote_only"):
            mode_token = normalized_text_token(normalized.get("employment_mode", ""))
            is_remote_like = mode_token in {"remote", "hybrid", "home office", "telework", "teletravail"}
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

        required_min, required_max = self._resolve_required_workload_range(profile_dict, preferences)
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
        # Only active when the feature flag is enabled AND the candidate profile
        # has been successfully normalized (non-empty profile_normalization dict).
        if settings.SEARCH_ENABLE_NORMALIZATION_MATCHING:
            profile_norm = profile_dict.get("profile_normalization") or {}
            if profile_norm:
                preference_signals = profile_dict.get("preference_signals") or {}
                ok, reason = self._passes_normalization_filters(normalized, profile_norm, preference_signals)
                if not ok:
                    return False, reason

        return True, "ok"

    # ─── qualification hierarchy used by normalization filters ───────────────
    _QUALIFICATION_RANK: Dict[str, int] = {
        "none": 0,
        "vocational": 1,
        "bachelor": 2,
        "master": 3,
        "phd": 4,
    }

    # Groups of closely related domains where cross-domain filter is relaxed.
    # Domains within the same group are considered "distance 1" (related).
    _RELATED_DOMAIN_GROUPS: tuple[frozenset[str], ...] = (
        frozenset({"it", "engineering"}),
        frozenset({"it", "consulting"}),
        frozenset({"it", "marketing"}),           # digital marketing / growth
        frozenset({"finance", "administration"}),
        frozenset({"finance", "consulting"}),
        frozenset({"medical", "pharma"}),
        frozenset({"medical", "education"}),      # healthcare training
        frozenset({"sales", "marketing"}),
        frozenset({"sales", "hospitality"}),      # client-facing service
        frozenset({"engineering", "construction"}),
        frozenset({"logistics", "construction"}),
        frozenset({"logistics", "general"}),
        frozenset({"hospitality", "general"}),
        frozenset({"administration", "legal"}),
        frozenset({"education", "consulting"}),
    )

    def _domains_are_related(self, domain_a: str, domain_b: str) -> bool:
        """Return True when two domains are in the same related group.

        Uses the continuous domain affinity matrix (threshold 0.40) when available,
        falling back to the legacy group-based check.
        """
        try:
            from backend.data.domain_affinity import domains_are_related  # type: ignore
            return domains_are_related(domain_a, domain_b, threshold=0.40)
        except Exception:
            # Legacy fallback
            for group in self._RELATED_DOMAIN_GROUPS:
                if domain_a in group and domain_b in group:
                    return True
            return False

    def _domain_affinity_score(self, domain_a: str, domain_b: str) -> float:
        """Return a continuous 0.0–1.0 affinity score between two domains."""
        try:
            from backend.data.domain_affinity import get_domain_affinity  # type: ignore
            return get_domain_affinity(domain_a, domain_b)
        except Exception:
            if domain_a == domain_b:
                return 1.0
            return 0.5 if self._domains_are_related(domain_a, domain_b) else 0.0

    def _domain_distance(self, domain_a: str, domain_b: str) -> int:
        """Return 0 (same), 1 (related), or 2 (unrelated) for two domain strings."""
        if domain_a == domain_b:
            return 0
        if self._domains_are_related(domain_a, domain_b):
            return 1
        return 2

    # Ordered seniority levels for range-based comparison
    _SENIORITY_ORDER: Dict[str, int] = {
        "intern": 0, "trainee": 0, "entry": 0,
        "junior": 1,
        "mid": 2,
        "senior": 3,
        "lead": 4,
        "director": 5,
    }

    # Role types grouped by family for compatibility checks
    _ROLE_TYPE_FAMILIES: List[frozenset] = [
        frozenset({"manual", "service"}),
        frozenset({"technical", "professional"}),
        frozenset({"administrative", "managerial"}),
        frozenset({"creative"}),
    ]

    def _role_types_compatible(self, intent_rt: str, job_rt: str) -> bool:
        """Return True when intent_role_type and job_role_type are in the same family."""
        if intent_rt == job_rt:
            return True
        for family in self._ROLE_TYPE_FAMILIES:
            if intent_rt in family and job_rt in family:
                return True
        return False

    def _passes_normalization_filters(
        self,
        job_norm: Dict[str, Any],
        profile_norm: Dict[str, Any],
        preference_signals: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        """Intent-aware deterministic field-vs-field match between normalized job and candidate.

        Uses the SEARCH INTENT (what the user WANTS) as the primary comparison axis,
        falling back to the candidate CV profile for fields the intent doesn't specify.

        Key principle: if the user explicitly searches in a domain different from their CV
        (open_to_unrelated=True), domain and skills filters are bypassed so cross-domain
        job exploration works correctly.

        Checks (in order):
        0. Confidence gate           — low-confidence normalizations skip all checks
        0.5 Dealbreaker rejection    — absolute no-gos from the search intent
        1. Domain match              — uses intent_domain; bypassed when open_to_unrelated=True
        2. Role-type match           — intent_role_type vs job role_type family check
        3. Seniority range match     — uses intent_seniority_min/max (falls back to single seniority)
        4. Qualification match       — uses intent_qualification_level (falls back to candidate)
        5a. Entry barrier gate       — high-barrier jobs rejected for cross-domain explorers
        5b. Experience floor         — uses candidate's actual experience (CV fact)
        6. Skills overlap            — alias-aware; extended with transferable_skills;
                                       bypassed when job is career_changer_friendly
        """
        # ─── 0. Confidence gate ───────────────────────────────────────────
        # Low-confidence normalization means categorical fields (domain, seniority,
        # role_type, qualification, skills) are unreliable.  Rather than skipping ALL
        # checks (old, unsafe behaviour), we set a flag and selectively skip only the
        # inference-based categorical gates, while still enforcing hard numeric facts
        # (experience floor, entry barrier) and the candidate's own dealbreakers.
        # The prescore threshold is raised by 15 pts as an additional safety net.
        raw_confidence = job_norm.get("confidence")
        low_confidence = False
        if raw_confidence is not None:
            try:
                if float(raw_confidence) < 0.7:
                    low_confidence = True
            except (TypeError, ValueError):
                pass

        open_to_unrelated = bool(profile_norm.get("open_to_unrelated", False))
        flexibility = profile_norm.get("flexibility") or {}

        # ─── 0.5. Dealbreaker rejection ──────────────────────────────────
        # Absolute no-gos from the search intent take effect before any other filter.
        dealbreakers = [str(d).lower().strip() for d in (profile_norm.get("dealbreakers") or []) if d]
        if dealbreakers:
            hard_blockers_raw = list(job_norm.get("hard_blockers") or []) + list(job_norm.get("key_requirements") or [])
            hard_blockers = [normalized_text_token(str(b)) for b in hard_blockers_raw if b]
            for dk in dealbreakers:
                dk_token = normalized_text_token(dk)
                if dk_token and any(
                    _word_bounded_substring(dk_token, hb) or _word_bounded_substring(hb, dk_token)
                    for hb in hard_blockers if hb
                ):
                    return False, "norm_dealbreaker_hit"

        # ─── 0.6. Progressive dealbreaker escalation (Tier 3 hard filter) ────
        # When a user has dismissed 10+ jobs with the same feedback signal, that pattern
        # is a strong learned preference. We auto-reject new jobs that clearly match it
        # without waiting for MATCH — saving tokens and improving precision.
        if preference_signals:
            _t3 = int(getattr(settings, "DEALBREAKER_ESCALATION_TIER3", 10))
            _dealbreaker_patterns = preference_signals.get("dealbreaker_patterns") or {}
            _job_seniority_esc = str(job_norm.get("seniority") or job_norm.get("normalized_seniority") or "").lower()
            _profile_seniority_esc = str(
                profile_norm.get("intent_seniority") or profile_norm.get("seniority") or ""
            ).lower()
            _job_domain_esc = str(job_norm.get("domain") or job_norm.get("normalized_domain") or "general").lower()
            _avoided_domains_esc = [d.lower() for d in (preference_signals.get("avoided_domains") or [])]
            for _sig, _cnt in _dealbreaker_patterns.items():
                if _cnt < _t3:
                    continue
                if _sig == "too_senior" and _job_seniority_esc == "senior" and _profile_seniority_esc in ("junior", "mid"):
                    return False, "norm_escalated_dealbreaker:too_senior"
                if _sig == "too_junior" and _job_seniority_esc == "junior" and _profile_seniority_esc in ("senior", "mid"):
                    return False, "norm_escalated_dealbreaker:too_junior"
                if _sig == "wrong_domain" and _job_domain_esc and _job_domain_esc in _avoided_domains_esc:
                    return False, "norm_escalated_dealbreaker:wrong_domain"

        # ─── 1. Domain match ─────────────────────────────────────────────
        # Skip for low-confidence normalizations — the extracted domain may be wrong.
        # Primary: use search intent domain; fallback to CV domain
        intent_domain = str(profile_norm.get("intent_domain") or profile_norm.get("domain") or "general").strip().lower()
        job_domain = str(job_norm.get("domain") or "general").strip().lower()

        if not low_confidence and not open_to_unrelated:
            if (
                intent_domain
                and job_domain
                and intent_domain != "general"
                and job_domain != "general"
                and intent_domain != job_domain
                and not self._domains_are_related(intent_domain, job_domain)
            ):
                return False, "norm_domain_mismatch"

        # ─── 2. Role-type match ───────────────────────────────────────────
        # Use explicit intent_role_type when available.
        # Example: junior developer with intent_role_type="manual" should only see manual/service jobs.
        # Skip for low-confidence normalizations — the extracted role_type may be wrong.
        intent_role_type = str(profile_norm.get("intent_role_type") or "").strip().lower() or None
        job_role_type = str(job_norm.get("role_type") or "").strip().lower() or None

        if not low_confidence and intent_role_type and job_role_type:
            flexible_domain = bool(flexibility.get("domain", False))
            if not flexible_domain and not open_to_unrelated:
                if not self._role_types_compatible(intent_role_type, job_role_type):
                    return False, "norm_role_type_mismatch"

        # ─── Manual-work gate (keyword fallback when intent_role_type not extracted yet) ─
        intent_keywords = [str(k).lower() for k in (profile_norm.get("intent_keywords") or []) if k]
        _manual_signals = {"manual", "warehouse", "cleaning", "physical", "handwerk", "lager", "reinigung", "manuell"}
        searching_manual = (
            (intent_role_type in {"manual", "service"})
            or open_to_unrelated
            or bool(_manual_signals & set(intent_keywords))
        )

        # ─── 3. Seniority range match ─────────────────────────────────────
        # Use intent_seniority_min/max range; fall back to single intent_seniority or CV seniority.
        # Skip for low-confidence normalizations — the extracted seniority may be wrong.
        intent_seniority_min = str(profile_norm.get("intent_seniority_min") or "").strip().lower() or None
        intent_seniority_max = str(profile_norm.get("intent_seniority_max") or "").strip().lower() or None
        has_range = intent_seniority_min or intent_seniority_max
        job_seniority = str(job_norm.get("seniority") or "").strip().lower()

        if not low_confidence and job_seniority and has_range:
            job_rank = self._SENIORITY_ORDER.get(job_seniority, -1)
            if job_rank >= 0:
                if intent_seniority_min:
                    min_rank = self._SENIORITY_ORDER.get(intent_seniority_min, -1)
                    if min_rank >= 0 and job_rank < min_rank:
                        pass  # job is below min — fine, user can fill an easier role
                if intent_seniority_max:
                    max_rank = self._SENIORITY_ORDER.get(intent_seniority_max, -1)
                    if max_rank >= 0 and job_rank > max_rank:
                        # Job requires higher seniority than max tolerance — check exp gap
                        user_exp = coerce_int(profile_norm.get("experience_years"), None)
                        job_exp_min = coerce_int(job_norm.get("experience_min_years"), None)
                        tolerance = int(getattr(settings, "SEARCH_NORMALIZATION_EXPERIENCE_TOLERANCE", 2))
                        if job_exp_min is not None and user_exp is not None and job_exp_min > user_exp + tolerance:
                            return False, "norm_seniority_overqualified"
        elif not low_confidence and job_seniority:
            # Legacy single-point seniority check
            effective_seniority = str(
                profile_norm.get("intent_seniority") or profile_norm.get("seniority") or ""
            ).strip().lower()
            if effective_seniority:
                if effective_seniority == "junior" and job_seniority == "senior":
                    job_exp_min = coerce_int(job_norm.get("experience_min_years"), None)
                    user_exp = coerce_int(profile_norm.get("experience_years"), None)
                    tolerance = int(getattr(settings, "SEARCH_NORMALIZATION_EXPERIENCE_TOLERANCE", 2))
                    if (
                        job_exp_min is not None
                        and user_exp is not None
                        and job_exp_min > user_exp + tolerance
                    ):
                        return False, "norm_seniority_overqualified"
                if effective_seniority == "senior" and job_seniority == "junior":
                    job_exp_max = coerce_int(job_norm.get("experience_max_years"), None)
                    user_exp = coerce_int(profile_norm.get("experience_years"), None)
                    if (
                        job_exp_max is not None
                        and user_exp is not None
                        and job_exp_max < user_exp - 3
                    ):
                        return False, "norm_seniority_underqualified"

        # ─── 4. Qualification level ───────────────────────────────────────
        # Use intent qualification (what the user is willing to meet); fall back to CV level.
        # Skip for low-confidence normalizations — the extracted qualification may be wrong.
        effective_ql = str(
            profile_norm.get("intent_qualification_level") or profile_norm.get("qualification_level") or ""
        ).strip().lower()
        job_ql = str(job_norm.get("qualification_level") or "").strip().lower()

        if not low_confidence and effective_ql and job_ql:
            # Skip qualification check for entry_barrier=none or career_changer_friendly jobs
            job_entry_barrier = str(job_norm.get("entry_barrier") or "").strip().lower()
            job_career_changer = bool(job_norm.get("career_changer_friendly", False))
            if not job_career_changer and job_entry_barrier not in {"none", "low"}:
                user_rank = self._QUALIFICATION_RANK.get(effective_ql, -1)
                job_rank = self._QUALIFICATION_RANK.get(job_ql, -1)
                if user_rank >= 0 and job_rank >= 0 and job_rank > user_rank + 1:
                    return False, "norm_qualification_mismatch"

        # ─── 5a. Entry barrier gate ───────────────────────────────────────
        # Cross-domain explorers (open_to_unrelated) should not be forced into
        # high-barrier jobs that require domain-specific credentials.
        job_entry_barrier_check = str(job_norm.get("entry_barrier") or "").strip().lower()
        if open_to_unrelated and job_entry_barrier_check == "high":
            return False, "norm_entry_barrier_high"

        # ─── 5b. Experience floor ─────────────────────────────────────────
        job_exp_min = coerce_int(job_norm.get("experience_min_years"), None)
        user_exp = coerce_int(profile_norm.get("experience_years"), None)
        if job_exp_min is not None and user_exp is not None:
            tolerance = int(getattr(settings, "SEARCH_NORMALIZATION_EXPERIENCE_TOLERANCE", 2))
            if job_exp_min > user_exp + tolerance:
                return False, "norm_experience_floor"

        # ─── 6. Skills overlap (alias-aware, extended with transferable skills) ─
        # Skip for low-confidence normalizations — required_skills may be empty or wrong.
        career_changer_friendly = bool(job_norm.get("career_changer_friendly", False))
        if not low_confidence and not searching_manual and not career_changer_friendly:
            job_skills = [s for s in (job_norm.get("required_skills") or []) if s]
            # Combine CV skills + intent target skills + transferable skills as the candidate pool
            profile_skills = list({
                *[s for s in (profile_norm.get("skills") or []) if s],
                *[s for s in (profile_norm.get("intent_skills") or []) if s],
                *[s for s in (profile_norm.get("transferable_skills") or []) if s],
            })
            if len(job_skills) >= 3 and len(profile_skills) >= 3:
                overlap = semantic_skills_score(job_skills, profile_skills)
                if overlap == 0.0:
                    return False, "norm_skills_disjoint"

        # ─── 7. Continuous pre-score gate (optional) ──────────────────────────
        # Runs after structural filters pass. Uses compute_prescore() to get a
        # 0-100 multi-signal score and rejects jobs that are very unlikely matches.
        if getattr(settings, "STRUCTURED_PRESCORE_ENABLED", False):
            try:
                threshold = float(getattr(settings, "STRUCTURED_PRESCORE_THRESHOLD", 30.0))
                # Dynamic threshold: stricter when user has established preference signals
                if (
                    preference_signals
                    and preference_signals.get("signal_count", 0) >= getattr(settings, "PREFERENCE_MIN_SIGNAL_COUNT", 10)
                ):
                    threshold = float(getattr(settings, "STRUCTURED_PRESCORE_THRESHOLD_WITH_PREFS", 35.0))
                # Low-confidence penalty: unreliable normalization must clear a higher bar
                if low_confidence:
                    threshold += 15.0
                prescore = compute_prescore(job_norm, profile_norm, preference_signals)
                if prescore < threshold:
                    return False, f"norm_prescore_low:{prescore:.1f}"
            except Exception:
                pass  # If prescore computation fails, allow the job through

        return True, "ok"

    def _resolve_required_workload_range(self, profile_dict: Dict[str, Any], preferences: Dict[str, Any]) -> tuple[Optional[int], Optional[int]]:
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
        "a1": 1, "a2": 2, "b1": 3, "b2": 4, "c1": 5, "c2": 6, "native": 6,
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
        configured_max = max(1, int(getattr(settings, "SEARCH_DEGRADED_PLAN_MAX_QUERIES", 3)))
        if isinstance(max_by_profile, int) and max_by_profile > 0:
            max_count = min(configured_max, max_by_profile)
        else:
            max_count = configured_max

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

        keyword_pool = ["python", "java", "javascript", "typescript", "react", "docker", "sql", "aws"]
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
        max_keywords = max(1, int(getattr(settings, "SEARCH_DEGRADED_PLAN_MAX_KEYWORDS", 2)))
        keyword_count = 0
        for candidate in raw_candidates:
            normalized_search, _ = normalize_search_item(candidate)
            if not normalized_search:
                continue
            if normalized_search.get("type") == "keyword" and keyword_count >= max_keywords:
                continue
            fingerprint = exact_query_fingerprint(normalized_search)
            if not fingerprint or fingerprint in seen:
                continue
            seen.add(fingerprint)
            fallback_searches.append(normalized_search)
            if normalized_search.get("type") == "keyword":
                keyword_count += 1
            if len(fallback_searches) >= max_count:
                break

        return fallback_searches

    async def run_search(
        self,
        profile_id: int,
        force_regenerate_cv_summary: bool = False,
        force_regenerate_queries: bool = False,
    ):
        """Run the full search workflow for a saved profile."""
        register_task(profile_id, asyncio.current_task())

        # Ensure fresh LLM providers (reload config)
        llm_service.clear_provider_cache()

        try:
            await asyncio.wait_for(
                self._run_pipeline(profile_id, force_regenerate_cv_summary, force_regenerate_queries),
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
        except Exception as e:
            logger.error(f"Unexpected error in run_search for profile {profile_id}: {e}", exc_info=True)
            update_status(profile_id, state="error", error=f"Unexpected error: {e}")
        finally:
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
                    logger.warning("Failed to close provider %s cleanly: %s", provider_name, close_error)

            unregister_task(profile_id)

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

        provider_infos = {
            name: p.get_provider_info() for name, p in self.providers.items() if p
        }

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

            enable_degraded_fallback = bool(getattr(settings, "SEARCH_ENABLE_DEGRADED_PLAN_FALLBACK", False))
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
                    add_log(profile_id, "Degraded fallback plan did not produce executable queries.")

            if searches:
                add_log(profile_id, "Continuing search with degraded fallback plan.")
            else:
                terminal_reason = status_reason or "no_queries"
                if terminal_reason == "no_valid_queries_after_filter":
                    add_log(profile_id, "LLM generated plan candidates, but all were filtered out as invalid/duplicates.")
                else:
                    add_log(profile_id, "No valid search queries were generated.")
                add_log(profile_id, f"[LLM_DEBUG] state=done terminal_reason={terminal_reason} profile_id={profile_id}")
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
        add_log(profile_id, "Step 2+: Streaming search with real-time normalization and analysis...")

        # Pre-load profile job history for incremental deduplication inside the producer.
        profile_history = self._load_profile_dedup_history(profile_id, user_id)

        # The producer streams unique-per-query batches; the consumer normalizes,
        # filters, and runs LLM analysis on each batch as it arrives.
        job_queue: asyncio.Queue = asyncio.Queue()
        (total_found, total_duplicates), (total_filtered, analyzed_pairs) = await asyncio.gather(
            self._search_and_produce(
                profile_id, profile, searches, provider_infos, job_queue, profile_history
            ),
            self._processing_consumer(
                profile_id, profile_dict, profile_preferences, job_queue
            ),
        )

        if total_found == 0:
            add_log(profile_id, "No jobs found across all queries.")
            add_log(profile_id, f"[LLM_DEBUG] state=done terminal_reason=no_results profile_id={profile_id}")
            update_status(profile_id, state="done", terminal_reason="no_results")
            return

        unique_total = total_found - total_duplicates
        if unique_total == 0:
            add_log(profile_id, "All found jobs are already in profile history.")
            add_log(profile_id, f"[LLM_DEBUG] state=done terminal_reason=all_duplicates profile_id={profile_id}")
            update_status(
                profile_id, state="done", terminal_reason="all_duplicates",
                jobs_found=total_found, jobs_duplicates=total_duplicates,
            )
            return

        if not analyzed_pairs:
            add_log(profile_id, "No jobs passed structured filtering and analysis.")
            add_log(profile_id, f"[LLM_DEBUG] state=done terminal_reason=no_jobs_after_structured_filters profile_id={profile_id}")
            update_status(
                profile_id, state="done",
                terminal_reason="no_jobs_after_structured_filters",
                jobs_found=total_found, jobs_duplicates=total_duplicates, jobs_skipped=total_filtered,
            )
            return

        # ── Step 6b: Optional final passes (critique, rerank) then save ──
        needs_final_pass = (
            getattr(settings, "MATCH_CRITIQUE_ENABLED", False)
            or getattr(settings, "MATCH_RERANK_ENABLED", False)
        )
        if needs_final_pass:
            add_log(profile_id, f"Step 6b: Running final analysis passes ({len(analyzed_pairs)} jobs)...")
            update_status(profile_id, state="analyzing")

        saved_count, skipped_count = await self._finalize_and_save(
            profile_id, profile_dict, analyzed_pairs
        )
        total_skipped = total_filtered + skipped_count

        add_log(profile_id, f"✓ Search complete – {saved_count} jobs saved, {skipped_count} skipped")
        add_log(profile_id, f"[LLM_DEBUG] state=done terminal_reason=completed profile_id={profile_id} jobs_saved={saved_count} jobs_skipped={skipped_count}")
        update_status(
            profile_id,
            state="done",
            terminal_reason="completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            jobs_found=total_found,
            jobs_new=saved_count,
            jobs_duplicates=total_duplicates,
            jobs_skipped=total_skipped,
        )

    # ───────────────────────── helper methods ─────────────────────────

    async def _generate_plan(self, profile_id: int, profile_dict: dict, profile, provider_infos) -> list:
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
                    profile_dict, list(provider_infos.values()),
                    max_queries=profile.max_queries,
                    max_occupation_queries=profile.max_occupation_queries,
                    max_keyword_queries=profile.max_keyword_queries,
                )
                add_log(profile_id, f"[LLM_DEBUG] plan_raw_output_count={len(searches) if searches else 0}")
                update_status(profile_id, plan_raw_count=len(searches) if searches else 0)
            except Exception as e:
                logger.error(f"LLM keyword generation failed: {e}")
                error_text = str(e).lower()
                terminal_reason = "llm_plan_error"
                if "rate limit" in error_text or "rate_limit" in error_text:
                    terminal_reason = "llm_plan_rate_limited"
                update_status(profile_id, state="error", terminal_reason=terminal_reason, error=str(e))
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

    async def _execute_searches(self, profile_id: int, profile, searches: list, provider_infos) -> list:
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
                        add_log(profile_id, f"  ℹ AVAM found no codes for «{query}», JobRoom will use keyword fallback")

                compatible = route_provider_names(normalized_search, self.providers, provider_infos)
                if not compatible:
                    execution_metrics["queries_without_provider"] += 1
                    add_log(profile_id, f"⚠ No providers accept domain '{domain}' for «{query}»")
                    return []

                # Update status
                update_status(profile_id, current_search_index=idx + 1, current_query=f"«{query}» ({domain})")
                add_log(profile_id, f"Running query {idx+1}/{len(searches)}: «{query}» on {', '.join(compatible)}")

                async def search_provider(provider_name: str, req: JobSearchRequest):
                    provider = self.providers[provider_name]
                    if not provider:
                        return provider_name, [], None

                    provider_jobs = []
                    try:
                        current_page = 0
                        while True:
                            page_size = 50
                            if hasattr(provider, "capabilities") and hasattr(provider.capabilities, "max_page_size"):
                                page_size = provider.capabilities.max_page_size

                            page_req = req.model_copy(update={"page": current_page, "page_size": page_size})
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
                            if total_count is not None and total_count >= 0 and len(provider_jobs) >= total_count:
                                break

                            current_page += 1

                            if provider.throttle_delay > 0:
                                await asyncio.sleep(provider.throttle_delay)  # Provider-level throttling

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
                    if hasattr(provider, "capabilities") and hasattr(provider.capabilities, "max_page_size"):
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

                return found_jobs

        results = await asyncio.gather(*(execute_single_search(i, q) for i, q in enumerate(searches)))

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

        seen_keys: set = set()
        seen_fuzzy_keys: set = set()
        seen_desc_fingerprints: set = set()
        unique_jobs: list = []

        existing_identifiers = self.job_repo.get_profile_job_identifiers(profile_id)
        profile_user_id = getattr(profile, "user_id", None)
        applied_scraped_ids = (
            self.job_repo.get_applied_scraped_job_ids(profile_user_id)
            if profile_user_id is not None
            else set()
        )

        existing_keys = {
            listing_identity_key(row) for row in existing_identifiers
            if listing_identity_key(row)
        }
        existing_urls = {
            listing_url_token(row) for row in existing_identifiers
            if listing_url_token(row)
        }
        existing_fuzzy_keys = {
            listing_fuzzy_key(row) for row in existing_identifiers
            if listing_fuzzy_key(row)
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

            for platform_name, platform_ids in pairs_by_platform.items():
                batch_sjs = self.db.query(
                    ScrapedJob.id, ScrapedJob.platform, ScrapedJob.platform_job_id
                ).filter(
                    ScrapedJob.platform == platform_name,
                    ScrapedJob.platform_job_id.in_(platform_ids),
                ).all()
                for sj_id, sj_platform, sj_platform_id in batch_sjs:
                    if sj_id in applied_scraped_ids:
                        applied_scraped_id_by_pair[(sj_platform, sj_platform_id)] = sj_id

        for listing in all_jobs:
            platform = getattr(listing, "source", None) or getattr(listing, "platform", "unknown")
            platform_id = str(getattr(listing, "id", "") or getattr(listing, "platform_job_id", ""))

            key = listing_identity_key(listing)
            url = listing_url_token(listing)
            fuzzy_key = listing_fuzzy_key(listing)

            if (platform and platform_id and (key in seen_keys or key in existing_keys)) or \
               (url and (url in existing_urls and key not in existing_keys)):
                   continue

            if fuzzy_key and (fuzzy_key in existing_fuzzy_keys or fuzzy_key in seen_fuzzy_keys):
                continue

            # Tier 4: description fingerprint — catches cross-provider reposts where
            # different platform IDs, URLs, and titles are used for the same body text.
            desc_fp = listing_description_fingerprint(listing)
            if desc_fp and desc_fp in seen_desc_fingerprints:
                logger.debug(
                    "[DEDUP][T4] Skipping cross-provider repost: %s/%s (desc_fp=%s…)",
                    platform, platform_id, desc_fp[:8],
                )
                continue

            if key:
                seen_keys.add(key)
            if url:
                existing_urls.add(url)
            if fuzzy_key:
                seen_fuzzy_keys.add(fuzzy_key)
            if desc_fp:
                seen_desc_fingerprints.add(desc_fp)

            # Feature 2 check: applied elsewhere (O(1) dict lookup — no per-listing DB queries)
            applied_elsewhere = (platform, platform_id) in applied_scraped_id_by_pair

            setattr(listing, "_applied_elsewhere", applied_elsewhere)
            unique_jobs.append(listing)

        duplicates = len(all_jobs) - len(unique_jobs)
        return unique_jobs, duplicates

    async def _analyze_and_save(self, profile_id: int, profile_dict: dict, unique_jobs: list) -> tuple[int, int]:
        semaphore = asyncio.Semaphore(settings.ANALYSIS_CONCURRENCY)
        batch_size = settings.ANALYSIS_BATCH_SIZE
        batches = [unique_jobs[i:i+batch_size] for i in range(0, len(unique_jobs), batch_size)]

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
                        desc_text = descs[0].description if hasattr(descs[0], "description") else (descs[0].get("description", "") if isinstance(descs[0], dict) else "")

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
                        "role_type": raw_norm.get("role_type") or raw_norm.get("normalized_role_type"),
                        "industry_sector": raw_norm.get("industry_sector") or raw_norm.get("normalized_industry_sector"),
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

                    jobs_metadata.append({
                        "title": getattr(job, "title", "Unknown"),
                        "description": await llm_service._compress_description_if_needed(
                            desc_text, settings.MAX_DESCRIPTION_CHARS
                        ),
                        "location": job.location.city if getattr(job, "location", None) else "Unknown",
                        "workload": f"{job.employment.workload_min}-{job.employment.workload_max}%" if getattr(job, "employment", None) else "Unknown",
                        "languages": [f"{s.language_code} ({s.spoken_level})" for s in getattr(job, "language_skills", [])] if getattr(job, "language_skills", None) else [],
                        "education": ", ".join(education_info) if education_info else "None specified",
                        "company": company_name,
                        "normalized_data": normalized_data,
                    })

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
                            desc_text = descs[0].description if hasattr(descs[0], "description") else (descs[0].get("description", "") if isinstance(descs[0], dict) else "")
                        raw_norm = getattr(job, "_normalized_job_data", None) or {}
                        borderline_jobs_meta.append({
                            "title": getattr(job, "title", "Unknown"),
                            "company": extract_company_name(job),
                            "description": desc_text,
                            "normalized_data": raw_norm,
                        })
                    borderline_analyses = [analysis for _, _, analysis in borderline]
                    critiqued = await llm_service.critique_job_batch(borderline_jobs_meta, borderline_analyses, profile_dict)
                    for orig_idx, critiqued_analysis in zip(borderline_indices, critiqued):
                        jobs_to_persist[orig_idx] = (jobs_to_persist[orig_idx][0], critiqued_analysis)
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
                        desc_text = descs[0].description if hasattr(descs[0], "description") else (descs[0].get("description", "") if isinstance(descs[0], dict) else "")
                    raw_norm = getattr(job, "_normalized_job_data", None) or {}
                    top_entries.append({
                        "job_index": orig_idx,
                        "current_score": analysis.get("affinity_score", 0),
                        "job_metadata": {
                            "title": getattr(job, "title", "Unknown"),
                            "company": extract_company_name(job),
                            "description": desc_text,
                            "normalized_data": raw_norm,
                        },
                    })
                reranked = await llm_service.rerank_top_jobs(top_entries, profile_dict)
                for rerank_result in reranked:
                    orig_idx = rerank_result.get("job_index", -1)
                    final_score = rerank_result.get("final_score")
                    if orig_idx >= 0 and final_score is not None and 0 <= orig_idx < len(jobs_to_persist):
                        job, analysis = jobs_to_persist[orig_idx]
                        updated = dict(analysis)
                        updated["affinity_score"] = final_score
                        updated["worth_applying"] = bool(analysis.get("worth_applying", False)) and final_score >= 65
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

    async def _save_single_job(self, listing, analysis, profile_dict, origin_coords, commit: bool = True):
        platform = getattr(listing, "source", None) or getattr(listing, "platform", "unknown")
        platform_id = str(getattr(listing, "id", "") or getattr(listing, "platform_job_id", ""))

        # 1. ScrapedJob (or fetch existing)
        existing_sj, _ = self._upsert_scraped_job(listing)

        location_str = extract_listing_location_string(listing)

        # 2. Distance
        distance_km = None
        if origin_coords and getattr(listing, "location", None):
            # Try to geocode if no coords
            coords = getattr(listing.location, "coordinates", None)
            if not coords and location_str:
                coords = await geocode_location(location_str)
                if coords:
                    logger.info("Resolved missing coordinates for %s via geocoding fallback", location_str)
                else:
                    logger.warning(
                        "Could not resolve coordinates for %s/%s with location %r",
                        platform,
                        platform_id,
                        location_str,
                    )

            if coords:
                distance_km = haversine_distance(
                    origin_coords[0], origin_coords[1],
                    coords.lat, coords.lon
                )

        # 3. Job (Link)
        new_job = Job(
            user_id=profile_dict["user_id"],
            search_profile_id=profile_dict["id"],
            scraped_job_id=existing_sj.id,
            affinity_score=analysis.get("affinity_score", 0),
            affinity_analysis=analysis.get("affinity_analysis", ""),
            worth_applying=analysis.get("worth_applying", False),
            distance_km=distance_km,
            applied=False,
            skill_match_score=analysis.get("skill_match_score"),
            experience_match_score=analysis.get("experience_match_score"),
            intent_match_score=analysis.get("intent_match_score"),
            language_match_score=analysis.get("language_match_score"),
            location_match_score=analysis.get("location_match_score"),
            transferability_score=analysis.get("transferability_score"),
            qualification_gap_score=analysis.get("qualification_gap_score"),
            analysis_structured=analysis.get("analysis_structured"),
            red_flags=analysis.get("red_flags"),
        )
        self.db.add(new_job)
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


    # ─── Streaming pipeline helpers ───────────────────────────────────────

    def _load_profile_dedup_history(self, profile_id: int, user_id: Optional[int]) -> dict:
        """Pre-load profile job history sets for incremental deduplication in the producer."""
        existing_identifiers = self.job_repo.get_profile_job_identifiers(profile_id)
        applied_scraped_ids = (
            self.job_repo.get_applied_scraped_job_ids(user_id)
            if user_id is not None
            else set()
        )
        return {
            "existing_keys": {listing_identity_key(r) for r in existing_identifiers if listing_identity_key(r)},
            "existing_urls": {listing_url_token(r) for r in existing_identifiers if listing_url_token(r)},
            "existing_fuzzy_keys": {listing_fuzzy_key(r) for r in existing_identifiers if listing_fuzzy_key(r)},
            "applied_scraped_ids": applied_scraped_ids,
        }

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
        total_duplicates = 0
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
        seen_identity_keys: set = set()
        seen_url_tokens: set = set()
        seen_fuzzy_keys: set = set()
        seen_desc_fingerprints: set = set()

        # Profile-history sets — mutated in-place so cross-query history dedup is cumulative.
        existing_keys: set = profile_history["existing_keys"]
        existing_urls: set = profile_history["existing_urls"]
        existing_fuzzy_keys: set = profile_history["existing_fuzzy_keys"]
        applied_scraped_ids: set = profile_history["applied_scraped_ids"]

        async def execute_and_push(idx: int, search: dict):
            nonlocal total_found, total_duplicates

            async with semaphore:
                status_data = get_status(profile_id)
                if status_data.get("state") in STOP_STATES:
                    return

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
                        add_log(profile_id, f"  ℹ AVAM found no codes for «{query}», JobRoom will use keyword fallback")

                compatible = route_provider_names(normalized_search, self.providers, provider_infos)
                if not compatible:
                    execution_metrics["queries_without_provider"] += 1
                    add_log(profile_id, f"⚠ No providers accept domain '{domain}' for «{query}»")
                    return

                update_status(profile_id, current_search_index=idx + 1, current_query=f"«{query}» ({domain})")
                add_log(profile_id, f"Running query {idx+1}/{len(searches)}: «{query}» on {', '.join(compatible)}")

                async def search_provider(provider_name: str, req: JobSearchRequest):
                    provider = self.providers[provider_name]
                    if not provider:
                        return provider_name, [], None
                    provider_jobs = []
                    try:
                        current_page = 0
                        while True:
                            page_size = 50
                            if hasattr(provider, "capabilities") and hasattr(provider.capabilities, "max_page_size"):
                                page_size = provider.capabilities.max_page_size
                            page_req = req.model_copy(update={"page": current_page, "page_size": page_size})
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
                            if total_count is not None and total_count >= 0 and len(provider_jobs) >= total_count:
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
                    if hasattr(provider, "capabilities") and hasattr(provider.capabilities, "max_page_size"):
                        page_size = provider.capabilities.max_page_size
                    if p_name == "job_room" and avam_fallback_keyword:
                        req_fallback = build_search_request(
                            profile, query, [],
                            language=supported_request_language(query_language, provider),
                            page_size=page_size, provider=provider,
                        )
                        p_tasks.append(search_provider(p_name, req_fallback))
                    else:
                        req = build_search_request(
                            profile, query, profession_codes,
                            language=supported_request_language(query_language, provider),
                            page_size=page_size, provider=provider,
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

                    if key and (key in seen_identity_keys or key in existing_keys):
                        continue
                    if url and (url in seen_url_tokens or (url in existing_urls and key not in existing_keys)):
                        continue
                    if fuzzy and (fuzzy in seen_fuzzy_keys or fuzzy in existing_fuzzy_keys):
                        continue
                    if desc_fp and desc_fp in seen_desc_fingerprints:
                        continue

                    if key:
                        seen_identity_keys.add(key)
                        existing_keys.add(key)
                    if url:
                        seen_url_tokens.add(url)
                        existing_urls.add(url)
                    if fuzzy:
                        seen_fuzzy_keys.add(fuzzy)
                        existing_fuzzy_keys.add(fuzzy)
                    if desc_fp:
                        seen_desc_fingerprints.add(desc_fp)

                    new_unique.append(job)

                total_duplicates += len(found_jobs) - len(new_unique)

                if not new_unique:
                    return

                # ── Persist this query's unique batch to the shared catalog ──
                try:
                    await self._persist_scraped_job_catalog(profile_id, new_unique)
                except Exception as persist_err:
                    logger.error(
                        "Failed to persist job batch for profile %s: %s", profile_id, persist_err
                    )
                    return

                # ── Set _applied_elsewhere flag (scraped_job_id is now assigned) ──
                for job in new_unique:
                    scraped_id = getattr(job, "_scraped_job_id", None)
                    setattr(
                        job, "_applied_elsewhere",
                        scraped_id is not None and scraped_id in applied_scraped_ids,
                    )

                # Push batch to the consumer for normalization + filtering + analysis.
                await job_queue.put(new_unique)

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
    ) -> tuple[int, list]:
        """Consume job batches from the queue; run normalize → filter → LLM analysis
        on each batch immediately as it arrives, overlapping with ongoing searches.

        Returns (total_filtered_count, analyzed_pairs) where analyzed_pairs is a list of
        (job_listing, analysis_dict).  Critique and reranking are deferred to _finalize_and_save.
        """
        total_filtered = 0
        analyzed_pairs: list = []
        cumulative_to_analyze = 0

        while True:
            batch = await job_queue.get()
            if batch is None:
                # Sentinel: producer finished.
                break

            status_data = get_status(profile_id)
            if status_data.get("state") in STOP_STATES:
                break

            # ── Normalize ──
            try:
                await self._normalize_persisted_jobs(profile_id, batch)
            except Exception as norm_err:
                from backend.services.llm_service import _unwrap_retry_error
                _, err_msg = _unwrap_retry_error(norm_err)
                logger.error(
                    "LLM normalization failed for profile %s batch — proceeding without full normalization: %s",
                    profile_id, err_msg,
                )
                add_log(
                    profile_id,
                    f"Normalization error (batch proceeds without field-level filtering): {err_msg}",
                )

            # ── Filter ──
            pre_filter = len(batch)
            filtered_batch = self._apply_structured_filters(
                profile_id, profile_dict, batch, profile_preferences
            )
            total_filtered += pre_filter - len(filtered_batch)

            if not filtered_batch:
                continue

            # Update running total so the frontend can show analysis progress in real time.
            cumulative_to_analyze += len(filtered_batch)
            update_status(profile_id, jobs_analyze_total=cumulative_to_analyze)

            # ── LLM analysis (batch-parallel, no critique/rerank yet) ──
            batch_pairs = await self._run_analysis_batches(profile_id, profile_dict, filtered_batch)
            analyzed_pairs.extend(batch_pairs)
            update_status(profile_id, jobs_analyzed=len(analyzed_pairs))

        return total_filtered, analyzed_pairs

    async def _run_analysis_batches(self, profile_id: int, profile_dict: dict, jobs: list) -> list:
        """Run LLM match analysis on a list of jobs using concurrent internal batches.

        Returns a list of (job_listing, analysis_dict) pairs.
        Critique, reranking, and salary benchmark are *not* applied here —
        they are handled once across all batches by _finalize_and_save.
        """
        semaphore = asyncio.Semaphore(settings.ANALYSIS_CONCURRENCY)
        batch_size = settings.ANALYSIS_BATCH_SIZE
        batches = [jobs[i:i + batch_size] for i in range(0, len(jobs), batch_size)]

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
                            else (descs[0].get("description", "") if isinstance(descs[0], dict) else "")
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
                        "role_type": raw_norm.get("role_type") or raw_norm.get("normalized_role_type"),
                        "industry_sector": raw_norm.get("industry_sector") or raw_norm.get("normalized_industry_sector"),
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
                    jobs_metadata.append({
                        "title": getattr(job, "title", "Unknown"),
                        "description": await llm_service._compress_description_if_needed(
                            desc_text, settings.MAX_DESCRIPTION_CHARS
                        ),
                        "location": job.location.city if getattr(job, "location", None) else "Unknown",
                        "workload": (
                            f"{job.employment.workload_min}-{job.employment.workload_max}%"
                            if getattr(job, "employment", None) else "Unknown"
                        ),
                        "languages": (
                            [f"{s.language_code} ({s.spoken_level})" for s in getattr(job, "language_skills", [])]
                            if getattr(job, "language_skills", None) else []
                        ),
                        "education": ", ".join(education_info) if education_info else "None specified",
                        "company": company_name,
                        "normalized_data": normalized_data,
                    })

                try:
                    results = await llm_service.analyze_job_batch(jobs_metadata, profile_dict)
                    return list(zip(batch, results))
                except Exception as e:
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
    ) -> tuple[int, int]:
        """Apply optional critique, reranking, and salary benchmark; then persist all jobs.

        Receives (job, analysis) pairs that have already been through LLM analysis
        (produced by _processing_consumer → _run_analysis_batches).
        """
        post_status = get_status(profile_id)
        if post_status.get("state") in STOP_STATES:
            add_log(profile_id, "Search was stopped during analysis — discarding results.")
            return 0, len(analyzed_pairs)

        origin_coords = None
        if profile_dict.get("latitude") and profile_dict.get("longitude"):
            origin_coords = (profile_dict["latitude"], profile_dict["longitude"])

        jobs_to_persist = list(analyzed_pairs)

        # ── Phase: Two-pass critique for borderline scores ────────────────
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
                                else (descs[0].get("description", "") if isinstance(descs[0], dict) else "")
                            )
                        raw_norm = getattr(job, "_normalized_job_data", None) or {}
                        borderline_jobs_meta.append({
                            "title": getattr(job, "title", "Unknown"),
                            "company": extract_company_name(job),
                            "description": desc_text,
                            "normalized_data": raw_norm,
                        })
                    borderline_analyses = [analysis for _, _, analysis in borderline]
                    critiqued = await llm_service.critique_job_batch(
                        borderline_jobs_meta, borderline_analyses, profile_dict
                    )
                    for orig_idx, critiqued_analysis in zip(borderline_indices, critiqued):
                        jobs_to_persist[orig_idx] = (jobs_to_persist[orig_idx][0], critiqued_analysis)
                    add_log(profile_id, f"Critique pass refined {len(borderline)} borderline jobs.")
                except Exception as exc:
                    logger.warning("[CRITIQUE] Critique pass failed: %s", exc)

        # ── Phase: Comparative re-ranking of top-N jobs ──────────────────
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
                            else (descs[0].get("description", "") if isinstance(descs[0], dict) else "")
                        )
                    raw_norm = getattr(job, "_normalized_job_data", None) or {}
                    top_entries.append({
                        "job_index": orig_idx,
                        "current_score": analysis.get("affinity_score", 0),
                        "job_metadata": {
                            "title": getattr(job, "title", "Unknown"),
                            "company": extract_company_name(job),
                            "description": desc_text,
                            "normalized_data": raw_norm,
                        },
                    })
                reranked = await llm_service.rerank_top_jobs(top_entries, profile_dict)
                for rerank_result in reranked:
                    orig_idx = rerank_result.get("job_index", -1)
                    final_score = rerank_result.get("final_score")
                    if orig_idx >= 0 and final_score is not None and 0 <= orig_idx < len(jobs_to_persist):
                        job, analysis = jobs_to_persist[orig_idx]
                        updated = dict(analysis)
                        updated["affinity_score"] = final_score
                        updated["worth_applying"] = bool(analysis.get("worth_applying", False)) and final_score >= 65
                        jobs_to_persist[orig_idx] = (job, updated)
                add_log(profile_id, f"Re-ranked top {len(reranked)} jobs for calibration.")
            except Exception as exc:
                logger.warning("[RERANK] Re-rank pass failed: %s", exc)

        # ── Phase: Deterministic salary_below_market red flag injection ──
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

        saved_count = 0
        for job, analysis in jobs_to_persist:
            try:
                await self._save_single_job(job, analysis, profile_dict, origin_coords, commit=True)
                saved_count += 1
            except Exception as exc:
                logger.warning(
                    "Skipping job due to persistence error (profile %s): %s",
                    profile_dict.get("id"), exc,
                )

        skipped_count = len(analyzed_pairs) - saved_count
        return saved_count, skipped_count


def get_search_service(db: Session) -> SearchService:
    return SearchService(db)
