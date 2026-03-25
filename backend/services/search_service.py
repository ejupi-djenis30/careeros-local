import asyncio
import hashlib
import inspect
import json
import logging
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from backend.models import ScrapedJob, Job, SearchProfile
from backend.repositories.job_repository import JobRepository
from backend.repositories.profile_repository import ProfileRepository
from backend.services.llm_service import llm_service
from backend.services.search.search_validator import build_search_request
from backend.services.utils import geocode_location, calculate_distance, haversine_distance, clean_html_tags
from backend.core.config import settings

from backend.providers.jobs.jobroom.client import JobRoomProvider
from backend.providers.jobs.swissdevjobs.client import SwissDevJobsProvider
try:
    from backend.providers.jobs.adecco.client import AdeccoProvider
except ImportError:
    AdeccoProvider = None
from backend.providers.jobs.localdb.client import LocalDbProvider
from backend.providers.jobs.models import JobSearchRequest, SortOrder, RadiusSearchRequest, Coordinates
from backend.providers.jobs.jobroom.avam_mapper import avam_mapper
from backend.services.search.query_contracts import (
    build_plan_cache_payload,
    compute_plan_input_fingerprint,
    exact_query_fingerprint,
    is_cached_plan_compatible,
    loose_query_fingerprint,
    normalize_domain,
    normalize_language,
    normalize_search_item,
    route_provider_names,
    supported_request_language,
    unpack_plan_cache_payload,
)
from backend.services.search.profile_preferences import get_profile_preference
from backend.services.search_status import (
    init_status, add_log, update_status, clear_status, get_status, register_task, unregister_task
)

logger = logging.getLogger(__name__)


STOP_STATES = {"stopped", "cancelled", "finished", "failed"}


def get_query_fingerprint(query: str) -> str:
    return loose_query_fingerprint(query)


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
        if db is not None and not isinstance(db, Session) and job_repo is not None and profile_repo is None:
            profile_repo = job_repo
            job_repo = db
            db = None

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

    def _normalized_text_token(self, value: str) -> str:
        if not isinstance(value, str):
            return ""
        text = re.sub(r"[^\w\s]", " ", (value or "").lower())
        return " ".join(text.split())

    def _extract_company_name(self, listing) -> str:
        company_obj = getattr(listing, "company", None)
        if hasattr(company_obj, "name"):
            return company_obj.name or ""
        if isinstance(company_obj, str):
            return company_obj
        return ""

    def _listing_identity_key(self, listing) -> Optional[str]:
        platform = getattr(listing, "source", None) or getattr(listing, "platform", None)
        platform_id = getattr(listing, "id", None) or getattr(listing, "platform_job_id", None)
        if platform and platform_id:
            return f"{platform}:{platform_id}"
        return None

    def _listing_url_token(self, listing) -> str:
        url = getattr(listing, "external_url", None) or getattr(listing, "url", None) or ""
        return (url or "").strip().lower()

    def _listing_fuzzy_key(self, listing) -> str:
        title = self._normalized_text_token(getattr(listing, "title", ""))
        company = self._normalized_text_token(self._extract_company_name(listing))
        if not title and not company:
            return ""
        return f"{title}::{company}"

    def _coerce_int(self, value, default=None):
        if value is None or isinstance(value, bool):
            return default
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return default
            try:
                return int(text)
            except ValueError:
                return default
        return default

    def _coerce_string_list(self, value, normalizer) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",")]
        if not isinstance(value, list):
            return []
        normalized: List[str] = []
        seen = set()
        for item in value:
            token = normalizer(item)
            if not token or token in seen:
                continue
            seen.add(token)
            normalized.append(token)
        return normalized

    def _profile_preferences(self, profile) -> Dict[str, Any]:
        remote_pref = get_profile_preference(profile, "remote_only", False)
        return {
            "preferred_languages": self._coerce_string_list(get_profile_preference(profile, "preferred_languages"), normalize_language),
            "preferred_domains": self._coerce_string_list(get_profile_preference(profile, "preferred_domains"), normalize_domain),
            "remote_only": remote_pref if isinstance(remote_pref, bool) else False,
            "salary_min_chf": self._coerce_int(get_profile_preference(profile, "salary_min_chf"), None),
            "workload_min": self._coerce_int(get_profile_preference(profile, "workload_min"), None),
            "workload_max": self._coerce_int(get_profile_preference(profile, "workload_max"), None),
            "hard_max_distance_km": self._coerce_int(get_profile_preference(profile, "hard_max_distance_km"), None),
        }

    def _apply_query_preferences(self, searches: List[Dict[str, Any]], preferences: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
        allowed_languages = set(preferences.get("preferred_languages") or [])
        allowed_domains = set(preferences.get("preferred_domains") or [])

        stats = {
            "dropped_language": 0,
            "dropped_domain": 0,
        }
        filtered: List[Dict[str, Any]] = []
        for search in searches:
            lang = normalize_language(search.get("language", "en"))
            domain = normalize_domain(search.get("domain", "general"))
            if allowed_languages and lang not in allowed_languages:
                stats["dropped_language"] += 1
                continue
            if allowed_domains and domain not in allowed_domains:
                stats["dropped_domain"] += 1
                continue
            filtered.append(search)
        return filtered, stats

    def _listing_is_remote(self, listing) -> bool:
        employment = getattr(listing, "employment", None)
        work_forms = getattr(employment, "work_forms", None) or []
        for item in work_forms:
            token = self._normalized_text_token(str(item))
            if token in {"home office", "remote", "telework", "teletravail"}:
                return True

        title = self._normalized_text_token(getattr(listing, "title", ""))
        desc_text = ""
        descs = getattr(listing, "descriptions", [])
        if descs:
            first = descs[0]
            desc_text = first.description if hasattr(first, "description") else (first.get("description", "") if isinstance(first, dict) else "")
        haystack = f"{title} {self._normalized_text_token(desc_text)}"
        return any(token in haystack for token in ["remote", "home office", "hybrid", "teletravail", "telelavoro"])

    def _extract_salary_max_chf(self, listing) -> Optional[int]:
        chunks: List[str] = []
        descs = getattr(listing, "descriptions", [])
        if descs:
            first = descs[0]
            desc_text = first.description if hasattr(first, "description") else (first.get("description", "") if isinstance(first, dict) else "")
            chunks.append(str(desc_text or ""))
        raw_data = getattr(listing, "raw_data", None)
        if raw_data:
            chunks.append(str(raw_data))
        text = " ".join(chunks)
        if not text:
            return None

        matches = re.findall(r"(?i)(?:chf|sfr|fr\.?)(?:\s*)(\d{2,3}(?:[\s'’.]\d{3})?)", text)
        if not matches:
            matches = re.findall(r"(?i)(\d{2,3}(?:[\s'’.]\d{3})?)(?:\s*)(?:chf|sfr|fr\.?)", text)

        values = []
        for match in matches:
            digits = re.sub(r"\D", "", match)
            if not digits:
                continue
            try:
                values.append(int(digits))
            except ValueError:
                continue
        return max(values) if values else None

    def _extract_listing_description_text(self, listing) -> str:
        descs = getattr(listing, "descriptions", [])
        if not descs:
            return ""
        first = descs[0]
        return first.description if hasattr(first, "description") else (first.get("description", "") if isinstance(first, dict) else "")

    def _extract_listing_location_string(self, listing) -> str:
        location = getattr(listing, "location", None)
        return getattr(location, "city", None) or getattr(listing, "location", "") or ""

    def _extract_listing_workload_string(self, listing) -> str:
        employment = getattr(listing, "employment", None)
        if not employment:
            return ""
        workload_min = getattr(employment, "workload_min", None)
        workload_max = getattr(employment, "workload_max", None)
        if workload_min is None and workload_max is None:
            return ""
        if workload_min == workload_max:
            return f"{workload_min}%"
        return f"{workload_min}-{workload_max}%"

    def _parse_listing_publication_date(self, listing, platform: str, platform_id: str):
        publication = getattr(listing, "publication", None)
        if not publication or not getattr(publication, "start_date", None):
            return None

        try:
            date_raw = publication.start_date
            if "T" in date_raw:
                return datetime.fromisoformat(date_raw.replace('Z', '+00:00'))
            return datetime.strptime(date_raw, "%Y-%m-%d")
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Failed to parse publication date %r for %s/%s: %s",
                publication.start_date,
                platform,
                platform_id,
                exc,
            )
            return None

    def _bootstrap_normalized_job_data(self, listing, *, desc_text: str, company_name: str, location_str: str) -> Dict[str, Any]:
        employment = getattr(listing, "employment", None)
        workload_min = getattr(employment, "workload_min", None) if employment else None
        workload_max = getattr(employment, "workload_max", None) if employment else None

        language_requirements = []
        for skill in getattr(listing, "language_skills", []) or []:
            code = str(getattr(skill, "language_code", "") or "").strip().lower()
            level = str(getattr(skill, "spoken_level", "") or "").strip().upper() or None
            if not code:
                continue
            language_requirements.append({
                "code": code,
                "level": level,
            })

        education_levels = []
        qualification_codes = []
        for occupation in getattr(listing, "occupations", []) or []:
            education_code = getattr(occupation, "education_code", None)
            qualification_code = getattr(occupation, "qualification_code", None)
            if education_code:
                token = str(education_code).strip()
                if token and token not in education_levels:
                    education_levels.append(token)
            if qualification_code:
                token = str(qualification_code).strip()
                if token and token not in qualification_codes:
                    qualification_codes.append(token)

        title = clean_html_tags(getattr(listing, "title", "Unknown"))
        title_lower = title.lower()
        seniority = None
        for label, keywords in {
            "junior": ["junior", "entry", "intern", "trainee", "apprentice"],
            "mid": ["professional", "specialist", "associate"],
            "senior": ["senior", "lead", "principal", "head", "director", "manager"],
        }.items():
            if any(keyword in title_lower for keyword in keywords):
                seniority = label
                break

        experience_values = []
        for match in re.findall(r"(?i)(\d{1,2})\s*\+?\s*(?:years|year|yrs|yr|anni|jahre|ans)", desc_text or ""):
            try:
                experience_values.append(int(match))
            except ValueError:
                continue

        salary_max = self._extract_salary_max_chf(listing)
        remote = self._listing_is_remote(listing)

        return {
            "normalization_status": "provider_bootstrap",
            "normalized_at": datetime.now(timezone.utc),
            "normalization_version": 1,
            "normalization_source": "provider_bootstrap",
            "normalization_confidence": 0.35,
            "normalized_title": title,
            "normalized_role_family": title,
            "normalized_domain": "general",
            "normalized_seniority": seniority,
            "normalized_employment_mode": "remote" if remote else "on-site",
            "normalized_contract_type": None,
            "normalized_qualification_level": qualification_codes[0] if qualification_codes else None,
            "normalized_experience_min_years": min(experience_values) if experience_values else None,
            "normalized_experience_max_years": max(experience_values) if experience_values else None,
            "normalized_workload_min": workload_min,
            "normalized_workload_max": workload_max,
            "normalized_salary_min_chf": None,
            "normalized_salary_max_chf": salary_max,
            "normalized_required_languages": language_requirements or None,
            "normalized_required_skills": None,
            "normalized_education_levels": education_levels or None,
            "normalized_key_requirements": None,
            "normalized_metadata": {
                "bootstrap": True,
                "provider": getattr(listing, "source", None) or getattr(listing, "platform", "unknown"),
                "company": company_name,
                "location": location_str,
                "qualification_codes": qualification_codes,
            },
        }

    def _upsert_scraped_job(self, listing) -> tuple[ScrapedJob, bool]:
        platform = getattr(listing, "source", None) or getattr(listing, "platform", "unknown")
        platform_id = str(getattr(listing, "id", "") or getattr(listing, "platform_job_id", ""))

        existing_sj = self.db.query(ScrapedJob).filter(
            ScrapedJob.platform == platform,
            ScrapedJob.platform_job_id == platform_id,
        ).first()

        desc_text = self._extract_listing_description_text(listing)
        company_name = self._extract_company_name(listing) or "Unknown"
        location_str = self._extract_listing_location_string(listing)
        workload_str = self._extract_listing_workload_string(listing)
        pub_date = self._parse_listing_publication_date(listing, platform, platform_id)
        normalized_bootstrap = self._bootstrap_normalized_job_data(
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
                summary=getattr(listing, "_summary", None),
                **normalized_bootstrap,
            )
            self.db.add(existing_sj)
            self.db.flush()
            created = True
        else:
            if getattr(listing, "_summary", None) and not existing_sj.summary:
                existing_sj.summary = getattr(listing, "_summary", None)

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

        for listing in jobs:
            scraped_job_id = getattr(listing, "_scraped_job_id", None)
            if not scraped_job_id:
                continue
            scraped_job = self.db.query(ScrapedJob).filter(ScrapedJob.id == scraped_job_id).first()
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

        normalized_rows = await llm_service.normalize_job_batch(candidates)
        upgraded = 0
        for scraped_job, normalized in zip(candidate_records, normalized_rows):
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

            metadata = scraped_job.normalized_metadata or {}
            metadata.update({"llm_normalized": True, "source": "llm_normalizer"})
            scraped_job.normalized_metadata = metadata
            upgraded += 1

        self.db.commit()

        for listing in jobs:
            scraped_job_id = getattr(listing, "_scraped_job_id", None)
            if not scraped_job_id:
                continue
            refreshed = self.db.query(ScrapedJob).filter(ScrapedJob.id == scraped_job_id).first()
            if refreshed:
                setattr(listing, "_normalized_job_data", refreshed.normalized_job_data)

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
        """Extract/retrieve the normalized candidate profile for deterministic matching.

        Uses a fingerprint-based cache stored on the SearchProfile row.
        Re-runs LLM extraction only when the trigger inputs have changed or
        ``force=True`` (honours the same force_regenerate_cv_summary flag).

        Returns the normalized data dict (keys: seniority, domain, role_family,
        qualification_level, experience_years, languages, skills) or ``{}`` on failure.
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
            add_log(profile_id, "✓ Using cached candidate profile normalization")
            return {
                "seniority": profile.profile_normalized_seniority,
                "domain": profile.profile_normalized_domain,
                "role_family": profile.profile_normalized_role_family,
                "qualification_level": profile.profile_normalized_qualification_level,
                "experience_years": profile.profile_normalized_experience_years,
                "languages": profile.profile_normalized_languages or [],
                "skills": profile.profile_normalized_skills or [],
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
                    f"qualification={normalized.get('qualification_level')!r}",
                )
            return normalized or {}
        except Exception as exc:
            logger.warning("Profile normalization failed for profile %s: %s", profile_id, exc)
            add_log(profile_id, f"Profile normalization warning (non-fatal): {exc}")
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
            mode_token = self._normalized_text_token(normalized.get("employment_mode", ""))
            is_remote_like = mode_token in {"remote", "hybrid", "home office", "telework", "teletravail"}
            if mode_token:
                if not is_remote_like:
                    return False, "remote_only"
            elif not self._listing_is_remote(listing):
                return False, "remote_only"

        salary_min = preferences.get("salary_min_chf")
        if salary_min is not None:
            normalized_salary_max = self._coerce_int(normalized.get("salary_max_chf"), None)
            if normalized_salary_max is None:
                normalized_salary_max = self._extract_salary_max_chf(listing)
            if normalized_salary_max is None or normalized_salary_max < salary_min:
                return False, "salary_min_chf"

        required_min, required_max = self._resolve_required_workload_range(profile_dict, preferences)
        if required_min is not None or required_max is not None:
            listing_min = self._coerce_int(normalized.get("workload_min"), None)
            listing_max = self._coerce_int(normalized.get("workload_max"), None)
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
                ok, reason = self._passes_normalization_filters(normalized, profile_norm)
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

    _RELATED_DOMAINS: tuple[frozenset[str], ...] = (
        frozenset({"it", "engineering"}),
        frozenset({"finance", "administration"}),
    )

    def _domains_are_related(self, domain_a: str, domain_b: str) -> bool:
        for group in self._RELATED_DOMAINS:
            if domain_a in group and domain_b in group:
                return True
        return False

    def _passes_normalization_filters(
        self,
        job_norm: Dict[str, Any],
        profile_norm: Dict[str, Any],
    ) -> tuple[bool, str]:
        """Deterministic field-vs-field match between normalized job and candidate profile.

        All filters are *additive*: they only reject when BOTH sides have conclusive
        non-None data AND the data is clearly incompatible.  Unknown/missing data on
        either side always passes (benefit of the doubt).

        Checks (in order):
        1. Domain match          — rejects cross-domain mismatches (both sides non-"general")
        2. Seniority match       — rejects clear over-/under-qualification
        3. Qualification match   — rejects when job level exceeds candidate level
        4. Experience floor      — rejects when job minimum >>> candidate experience
        """
        # ─── 1. Domain match ─────────────────────────────────────────────
        user_domain = str(profile_norm.get("domain") or "general").strip().lower()
        job_domain = str(job_norm.get("domain") or "general").strip().lower()
        if (
            user_domain
            and job_domain
            and user_domain != "general"
            and job_domain != "general"
            and user_domain != job_domain
            and not self._domains_are_related(user_domain, job_domain)
        ):
            return False, "norm_domain_mismatch"

        # ─── 2. Seniority match ───────────────────────────────────────────
        user_seniority = str(profile_norm.get("seniority") or "").strip().lower()
        job_seniority = str(job_norm.get("seniority") or "").strip().lower()
        if user_seniority and job_seniority:
            # junior user → reject explicit senior jobs with experience floor clearly above user
            if user_seniority == "junior" and job_seniority == "senior":
                job_exp_min = self._coerce_int(job_norm.get("experience_min_years"), None)
                user_exp = self._coerce_int(profile_norm.get("experience_years"), None)
                tolerance = int(getattr(settings, "SEARCH_NORMALIZATION_EXPERIENCE_TOLERANCE", 2))
                if (
                    job_exp_min is not None
                    and user_exp is not None
                    and job_exp_min > user_exp + tolerance
                ):
                    return False, "norm_seniority_overqualified"
            # senior user → reject explicitly junior-only jobs
            # (only when job seniority is junior AND experience cap is low)
            if user_seniority == "senior" and job_seniority == "junior":
                job_exp_max = self._coerce_int(job_norm.get("experience_max_years"), None)
                user_exp = self._coerce_int(profile_norm.get("experience_years"), None)
                if (
                    job_exp_max is not None
                    and user_exp is not None
                    and job_exp_max < user_exp - 3
                ):
                    return False, "norm_seniority_underqualified"

        # ─── 3. Qualification level ───────────────────────────────────────
        user_ql = str(profile_norm.get("qualification_level") or "").strip().lower()
        job_ql = str(job_norm.get("qualification_level") or "").strip().lower()
        if user_ql and job_ql:
            user_rank = self._QUALIFICATION_RANK.get(user_ql, -1)
            job_rank = self._QUALIFICATION_RANK.get(job_ql, -1)
            # Only reject when both ranks are known AND job clearly exceeds candidate
            if user_rank >= 0 and job_rank >= 0 and job_rank > user_rank + 2:
                return False, "norm_qualification_mismatch"

        # ─── 4. Experience floor ─────────────────────────────────────────
        job_exp_min = self._coerce_int(job_norm.get("experience_min_years"), None)
        user_exp = self._coerce_int(profile_norm.get("experience_years"), None)
        if job_exp_min is not None and user_exp is not None:
            tolerance = int(getattr(settings, "SEARCH_NORMALIZATION_EXPERIENCE_TOLERANCE", 2))
            if job_exp_min > user_exp + tolerance:
                return False, "norm_experience_floor"

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

    def _passes_hard_filters(self, listing, preferences: Dict[str, Any], profile_dict: Dict[str, Any]) -> tuple[bool, str]:
        """DEPRECATED: Superseded by _passes_structured_filters (no normalization data used)."""
        if preferences.get("remote_only") and not self._listing_is_remote(listing):
            return False, "remote_only"

        salary_min = preferences.get("salary_min_chf")
        if salary_min is not None:
            salary_max = self._extract_salary_max_chf(listing)
            if salary_max is None or salary_max < salary_min:
                return False, "salary_min_chf"

        workload_min = preferences.get("workload_min")
        workload_max = preferences.get("workload_max")
        if workload_min is not None or workload_max is not None:
            employment = getattr(listing, "employment", None)
            if not employment:
                return False, "workload_missing"
            listing_min = getattr(employment, "workload_min", None)
            listing_max = getattr(employment, "workload_max", None)
            if listing_min is None or listing_max is None:
                return False, "workload_missing"
            required_min = workload_min if workload_min is not None else 0
            required_max = workload_max if workload_max is not None else 100
            if listing_max < required_min or listing_min > required_max:
                return False, "workload_range"

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

        return True, "ok"

    def _apply_hard_filters(self, profile_id: int, profile_dict: Dict[str, Any], jobs: List[Any], preferences: Dict[str, Any]) -> List[Any]:
        """DEPRECATED: Superseded by _apply_structured_filters (no normalization data used)."""
        if not jobs:
            return jobs

        has_hard_filters = any(
            [
                preferences.get("remote_only"),
                preferences.get("salary_min_chf") is not None,
                preferences.get("workload_min") is not None,
                preferences.get("workload_max") is not None,
                preferences.get("hard_max_distance_km") is not None,
            ]
        )
        if not has_hard_filters:
            return jobs

        kept: List[Any] = []
        dropped_reasons: Dict[str, int] = {}
        for job in jobs:
            ok, reason = self._passes_hard_filters(job, preferences, profile_dict)
            if ok:
                kept.append(job)
                continue
            dropped_reasons[reason] = dropped_reasons.get(reason, 0) + 1

        dropped_total = len(jobs) - len(kept)
        if dropped_total > 0:
            reasons_text = ", ".join([f"{key}:{value}" for key, value in sorted(dropped_reasons.items())])
            add_log(
                profile_id,
                f"Hard filters excluded {dropped_total}/{len(jobs)} jobs ({reasons_text}).",
            )
        return kept

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
                        cv_summary = profile_dict["cv_content"]
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

            # ── Step 2: Execute searches with domain routing (Feature 4) ──
            update_status(profile_id, state="searching")
            add_log(profile_id, f"Step 2: Executing scraper queries...")
            all_jobs = await self._execute_searches(profile_id, profile, searches, provider_infos)
            if not all_jobs:
                add_log(profile_id, "No jobs found across all queries.")
                add_log(profile_id, f"[LLM_DEBUG] state=done terminal_reason=no_results profile_id={profile_id}")
                update_status(profile_id, state="done", terminal_reason="no_results")
                return

            # ── Step 3: Deduplication & Feature 2 (Cross-Profile Applied) ──
            add_log(profile_id, "Step 3: Deduplicating and checking cross-profile status...")
            unique_jobs, duplicates = self._deduplicate(profile, all_jobs)
            add_log(profile_id, f"After dedup: {len(unique_jobs)} new, {duplicates} duplicates")
            
            if not unique_jobs:
                add_log(profile_id, "All found jobs are already in profile history.")
                add_log(profile_id, f"[LLM_DEBUG] state=done terminal_reason=all_duplicates profile_id={profile_id}")
                update_status(profile_id, state="done", terminal_reason="all_duplicates")
                return

            # ── Step 4: Persist every unique scraped job before any gating ──
            add_log(profile_id, f"Step 4: Persisting {len(unique_jobs)} unique fetched jobs into the shared catalog...")
            await self._persist_scraped_job_catalog(profile_id, unique_jobs)

            # ── Step 4.5: Upgrade provider bootstrap normalization with LLM normalization ──
            try:
                await self._normalize_persisted_jobs(profile_id, unique_jobs)
            except Exception as normalize_error:
                logger.warning("LLM normalization failed for profile %s: %s", profile_id, normalize_error)
                add_log(profile_id, f"Normalization warning: {normalize_error}")

            # ── Step 5: Structured filtering based on persisted job facts ──
            pre_filter_count = len(unique_jobs)
            unique_jobs = self._apply_structured_filters(profile_id, profile_dict, unique_jobs, profile_preferences)
            filtered_out_count = pre_filter_count - len(unique_jobs)

            if not unique_jobs:
                add_log(profile_id, "No jobs left after structured filtering.")
                add_log(profile_id, f"[LLM_DEBUG] state=done terminal_reason=no_jobs_after_structured_filters profile_id={profile_id}")
                update_status(profile_id, state="done", terminal_reason="no_jobs_after_structured_filters")
                return

            update_status(
                profile_id,
                state="analyzing",
                jobs_found=len(all_jobs),
                jobs_new=len(unique_jobs),
                jobs_duplicates=duplicates,
                jobs_skipped=filtered_out_count,
            )

            # ── Step 6: Analyze & save each structurally eligible job (Parallel) ──
            add_log(profile_id, f"Step 6: Detailed analysis and match scoring ({len(unique_jobs)} jobs)...")
            saved_count, skipped_count = await self._analyze_and_save(profile_id, profile_dict, unique_jobs)
            total_skipped = filtered_out_count + skipped_count

            add_log(profile_id, f"✓ Search complete – {saved_count} jobs saved, {skipped_count} skipped")
            add_log(profile_id, f"[LLM_DEBUG] state=done terminal_reason=completed profile_id={profile_id} jobs_saved={saved_count} jobs_skipped={skipped_count}")
            update_status(
                profile_id,
                state="done",
                terminal_reason="completed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                jobs_found=len(all_jobs),
                jobs_new=saved_count,
                jobs_duplicates=duplicates,
                jobs_skipped=total_skipped
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
                    if not provider: return provider_name, [], None
                    
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
                            
                            if provider_name == "adecco":
                                await asyncio.sleep(1.0) # Throttling
                                
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
                identity_key = self._listing_identity_key(job)
                url_token = self._listing_url_token(job)
                fuzzy_key = self._listing_fuzzy_key(job)

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
        unique_jobs: list = []
        
        existing_identifiers = self.job_repo.get_profile_job_identifiers(profile_id)
        profile_user_id = getattr(profile, "user_id", None)
        applied_scraped_ids = (
            self.job_repo.get_applied_scraped_job_ids(profile_user_id)
            if profile_user_id is not None
            else set()
        )
        
        existing_keys = {
            self._listing_identity_key(row) for row in existing_identifiers
            if self._listing_identity_key(row)
        }
        existing_urls = {
            self._listing_url_token(row) for row in existing_identifiers
            if self._listing_url_token(row)
        }
        existing_fuzzy_keys = {
            self._listing_fuzzy_key(row) for row in existing_identifiers
            if self._listing_fuzzy_key(row)
        }

        for listing in all_jobs:
            platform = getattr(listing, "source", None) or getattr(listing, "platform", "unknown")
            platform_id = str(getattr(listing, "id", "") or getattr(listing, "platform_job_id", ""))

            key = self._listing_identity_key(listing)
            url = self._listing_url_token(listing)
            fuzzy_key = self._listing_fuzzy_key(listing)

            if (platform and platform_id and (key in seen_keys or key in existing_keys)) or \
               (url and (url in existing_urls and key not in existing_keys)):
                   continue

            if fuzzy_key and (fuzzy_key in existing_fuzzy_keys or fuzzy_key in seen_fuzzy_keys):
                continue

            if key:
                seen_keys.add(key)
            if url:
                existing_urls.add(url)
            if fuzzy_key:
                seen_fuzzy_keys.add(fuzzy_key)
            
            # Feature 2 check: applied elsewhere
            applied_elsewhere = False
            # We don't have scraped_job_id yet for new jobs, so we check by platform_id
            from backend.models import ScrapedJob
            existing_sj = self.db.query(ScrapedJob).filter(
                ScrapedJob.platform == platform,
                ScrapedJob.platform_job_id == platform_id
            ).first()
            if existing_sj and existing_sj.id in applied_scraped_ids:
                applied_elsewhere = True
            
            setattr(listing, "_applied_elsewhere", applied_elsewhere)
            unique_jobs.append(listing)
                
        duplicates = len(all_jobs) - len(unique_jobs)
        return unique_jobs, duplicates

    async def _summarize_jobs(self, profile_id: int, jobs: list, batch_size: int = 10) -> list:
        """DEPRECATED: Job summaries are no longer used by the main pipeline.
        The normalization step and direct LLM analysis replace this pre-screen.
        Kept for compatibility only.
        """
        add_log(profile_id, f"Summarizing job descriptions for {len(jobs)} jobs…")
        
        jobs_needing_summary = []
        from backend.models import ScrapedJob
        
        for job in jobs:
            platform = getattr(job, "source", None) or getattr(job, "platform", "")
            job_id = str(getattr(job, "id", "") or getattr(job, "platform_job_id", ""))
            
            existing_sj = self.db.query(ScrapedJob).filter(
                ScrapedJob.platform == platform,
                ScrapedJob.platform_job_id == job_id
            ).first()
            
            if existing_sj and existing_sj.summary:
                setattr(job, "_summary", existing_sj.summary)
            else:
                jobs_needing_summary.append(job)
        
        if not jobs_needing_summary:
            return jobs
        
        add_log(profile_id, f"  Generating {len(jobs_needing_summary)} new summaries…")
        
        for i in range(0, len(jobs_needing_summary), batch_size):
            batch = jobs_needing_summary[i:i + batch_size]
            batch_data = []
            for j in batch:
                desc = ""
                descs = getattr(j, "descriptions", [])
                if descs:
                    desc = descs[0].description if hasattr(descs[0], "description") else (descs[0].get("description", "") if isinstance(descs[0], dict) else "")
                
                batch_data.append({
                    "title": getattr(j, "title", "Unknown"),
                    "company": getattr(j, "company").name if hasattr(getattr(j, "company", None), "name") else "Unknown",
                    "description": desc[:2000],
                })
            
            try:
                summaries = await llm_service.summarize_job_batch(batch_data)
                for j, summary_text in zip(batch, summaries):
                    setattr(j, "_summary", summary_text)
            except Exception as e:
                logger.warning(f"Job summary batch failed: {e}")
        
        return jobs

    async def _relevance_filter(self, profile_id: int, profile_dict: dict, jobs: list, batch_size: int = 20) -> list:
        """DEPRECATED: Title/summary-based LLM relevance filter, superseded by normalization-based
        deterministic matching in _passes_normalization_filters.  This method is no longer called by
        the main run_search pipeline.  Kept for compatibility only.
        """
        relevant_jobs = []
        fallback_mode = (settings.SEARCH_RELEVANCE_FALLBACK_MODE or "conservative").strip().lower()
        keep_on_failure = fallback_mode == "keep"
        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            batch_data = []
            for j in batch:
                summary = getattr(j, "_summary", None)
                if not summary:
                    descs = getattr(j, "descriptions", [])
                    if descs:
                        summary = descs[0].description[:150] if hasattr(descs[0], "description") else (descs[0].get("description", "")[:150] if isinstance(descs[0], dict) else "")
                
                batch_data.append({
                    "title": getattr(j, "title", "Unknown"),
                    "company": getattr(j, "company").name if hasattr(getattr(j, "company", None), "name") else "Unknown",
                    "description_snippet": summary or "",
                })
            try:
                results = await llm_service.check_relevance_batch(
                    batch_data,
                    profile_dict.get("role_description", ""),
                    search_strategy=profile_dict.get("search_strategy", ""),
                )
                for j, is_relevant in zip(batch, results):
                    if is_relevant:
                        relevant_jobs.append(j)
            except Exception as e:
                logger.warning(f"Relevance filter failed: {e}")
                add_log(
                    profile_id,
                    f"[LLM_DEBUG] relevance_fallback mode={fallback_mode} batch_start={i} batch_size={len(batch)} error={type(e).__name__}",
                )
                if keep_on_failure:
                    relevant_jobs.extend(batch)
        
        return relevant_jobs

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

                    jobs_metadata.append({
                        "title": getattr(job, "title", "Unknown"),
                        "description": desc_text[:settings.MAX_DESCRIPTION_CHARS],
                        "location": job.location.city if getattr(job, "location", None) else "Unknown",
                        "workload": f"{job.employment.workload_min}-{job.employment.workload_max}%" if getattr(job, "employment", None) else "Unknown",
                        "languages": [f"{s.language_code} ({s.spoken_level})" for s in getattr(job, "language_skills", [])] if getattr(job, "language_skills", None) else [],
                        "education": ", ".join(education_info) if education_info else "None specified",
                        "company": company_name,
                    })
                
                try:
                    results = await llm_service.analyze_job_batch(jobs_metadata, profile_dict)

                    relevant_jobs = []
                    for job, analysis in zip(batch, results):
                        if analysis.get("relevant", True):
                            relevant_jobs.append((job, analysis))
                    return relevant_jobs
                except Exception as e:
                    logger.error(f"Analysis batch failed: {e}")
                    return []

        tasks = [analyze_batch(batch) for batch in batches]
        results = await asyncio.gather(*tasks)

        jobs_to_persist = [item for batch_result in results for item in batch_result]

        try:
            for job, analysis in jobs_to_persist:
                await self._save_single_job(job, analysis, profile_dict, origin_coords, commit=False)
            if jobs_to_persist:
                self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.error(
                "Failed staged persistence for profile %s: %s",
                profile_dict.get("id"),
                exc,
            )
            return 0, len(unique_jobs)

        saved_count = len(jobs_to_persist)
        skipped_count = len(unique_jobs) - saved_count
        return saved_count, skipped_count

    async def _save_single_job(self, listing, analysis, profile_dict, origin_coords, commit: bool = True):
        platform = getattr(listing, "source", None) or getattr(listing, "platform", "unknown")
        platform_id = str(getattr(listing, "id", "") or getattr(listing, "platform_job_id", ""))
        
        # 1. ScrapedJob (or fetch existing)
        existing_sj, _ = self._upsert_scraped_job(listing)

        location_str = self._extract_listing_location_string(listing)

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
            is_scraped=True,
            affinity_score=analysis.get("affinity_score", 0),
            affinity_analysis=analysis.get("affinity_analysis", ""),
            worth_applying=analysis.get("worth_applying", False),
            distance_km=distance_km,
            applied=False,
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


def get_search_service(db: Session) -> SearchService:
    return SearchService(db)
