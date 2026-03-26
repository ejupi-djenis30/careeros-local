"""Pure utility helpers for inspecting raw job listing objects.

These functions have no external module-level dependencies beyond the standard
library and re (regex). They accept listing objects from any provider and
return plain Python values. Because they are side-effect-free they are safe
to import and call from anywhere without worrying about circular imports.
"""

import re
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def normalized_text_token(value: str) -> str:
    """Lowercase and strip punctuation from a string for fuzzy comparison."""
    if not isinstance(value, str):
        return ""
    text = re.sub(r"[^\w\s]", " ", (value or "").lower())
    return " ".join(text.split())


def coerce_int(value, default=None):
    """Safely coerce a value to int, returning *default* on failure."""
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


def coerce_string_list(value, normalizer) -> List[str]:
    """Convert a comma-string or list to a deduplicated list of normalized tokens."""
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


def extract_company_name(listing) -> str:
    """Extract the company name string from a listing object."""
    company_obj = getattr(listing, "company", None)
    if hasattr(company_obj, "name"):
        return company_obj.name or ""
    if isinstance(company_obj, str):
        return company_obj
    return ""


def listing_identity_key(listing) -> Optional[str]:
    """Return a ``platform:platform_id`` dedup key, or *None* if unavailable."""
    platform = getattr(listing, "source", None) or getattr(listing, "platform", None)
    platform_id = getattr(listing, "id", None) or getattr(listing, "platform_job_id", None)
    if platform and platform_id:
        return f"{platform}:{platform_id}"
    return None


def listing_url_token(listing) -> str:
    """Return the normalised external URL for URL-based deduplication."""
    url = getattr(listing, "external_url", None) or getattr(listing, "url", None) or ""
    return (url or "").strip().lower()


def listing_fuzzy_key(listing) -> str:
    """Return a ``normalized_title::normalized_company`` key for fuzzy dedup."""
    title = normalized_text_token(getattr(listing, "title", ""))
    company = normalized_text_token(extract_company_name(listing))
    if not title and not company:
        return ""
    return f"{title}::{company}"


def listing_is_remote(listing) -> bool:
    """Heuristically detect whether a listing is remote/hybrid."""
    employment = getattr(listing, "employment", None)
    work_forms = getattr(employment, "work_forms", None) or []
    for item in work_forms:
        token = normalized_text_token(str(item))
        if token in {"home office", "remote", "telework", "teletravail"}:
            return True

    title = normalized_text_token(getattr(listing, "title", ""))
    desc_text = ""
    descs = getattr(listing, "descriptions", [])
    if descs:
        first = descs[0]
        desc_text = (
            first.description
            if hasattr(first, "description")
            else (first.get("description", "") if isinstance(first, dict) else "")
        )
    haystack = f"{title} {normalized_text_token(desc_text)}"
    return any(
        token in haystack
        for token in ["remote", "home office", "hybrid", "teletravail", "telelavoro"]
    )


def extract_salary_max_chf(listing) -> Optional[int]:
    """Extract the maximum mentioned CHF salary from a listing's description / raw data."""
    chunks: List[str] = []
    descs = getattr(listing, "descriptions", [])
    if descs:
        first = descs[0]
        desc_text = (
            first.description
            if hasattr(first, "description")
            else (first.get("description", "") if isinstance(first, dict) else "")
        )
        chunks.append(str(desc_text or ""))
    raw_data = getattr(listing, "raw_data", None)
    if raw_data:
        chunks.append(str(raw_data))
    text = " ".join(chunks)
    if not text:
        return None

    matches = re.findall(r"(?i)(?:chf|sfr|fr\.?)(?:\s*)(\d{2,3}(?:[\s''.]\d{3})?)", text)
    if not matches:
        matches = re.findall(r"(?i)(\d{2,3}(?:[\s''.]\d{3})?)(?:\s*)(?:chf|sfr|fr\.?)", text)

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


def extract_listing_description_text(listing) -> str:
    """Return the first description text from a listing."""
    descs = getattr(listing, "descriptions", [])
    if not descs:
        return ""
    first = descs[0]
    return (
        first.description
        if hasattr(first, "description")
        else (first.get("description", "") if isinstance(first, dict) else "")
    )


def extract_listing_location_string(listing) -> str:
    """Return a city/location string from a listing."""
    location = getattr(listing, "location", None)
    return getattr(location, "city", None) or getattr(listing, "location", "") or ""


def extract_listing_workload_string(listing) -> str:
    """Return a workload percentage string such as "80-100%" from a listing."""
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


def parse_listing_publication_date(listing, platform: str, platform_id: str):
    """Parse the listing publication date to a datetime, or return None."""
    publication = getattr(listing, "publication", None)
    if not publication or not getattr(publication, "start_date", None):
        return None

    try:
        date_raw = publication.start_date
        if "T" in date_raw:
            return datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
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


def bootstrap_normalized_job_data(
    listing, *, desc_text: str, company_name: str, location_str: str
) -> Dict[str, Any]:
    """Build a provider_bootstrap normalization dict from raw listing fields.

    This is the first normalization pass (confidence 0.35) applied immediately
    after scraping, before any LLM-based normalization is attempted.
    """
    from backend.services.utils import clean_html_tags

    employment = getattr(listing, "employment", None)
    workload_min = getattr(employment, "workload_min", None) if employment else None
    workload_max = getattr(employment, "workload_max", None) if employment else None

    language_requirements = []
    for skill in getattr(listing, "language_skills", []) or []:
        code = str(getattr(skill, "language_code", "") or "").strip().lower()
        level = str(getattr(skill, "spoken_level", "") or "").strip().upper() or None
        if not code:
            continue
        language_requirements.append({"code": code, "level": level})

    education_levels: List[str] = []
    qualification_codes: List[str] = []
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
    for match in re.findall(
        r"(?i)(\d{1,2})\s*\+?\s*(?:years|year|yrs|yr|anni|jahre|ans)", desc_text or ""
    ):
        try:
            experience_values.append(int(match))
        except ValueError:
            continue

    salary_max = extract_salary_max_chf(listing)
    remote = listing_is_remote(listing)

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
