"""Pure utility helpers for inspecting raw job listing objects.

These functions have no external module-level dependencies beyond the standard
library and re (regex). They accept listing objects from any provider and
return plain Python values. Because they are side-effect-free they are safe
to import and call from anywhere without worrying about circular imports.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Skill taxonomy loader ────────────────────────────────────────────────────

def _load_skill_taxonomy() -> Dict[str, Any]:
    """Load the skill taxonomy JSON from backend/data/skill_taxonomy.json."""
    try:
        _here = os.path.dirname(os.path.abspath(__file__))
        taxonomy_path = os.path.join(_here, "..", "..", "data", "skill_taxonomy.json")
        with open(taxonomy_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("[SKILL_TAXONOMY] Could not load skill_taxonomy.json: %s", exc)
        return {}


_TAXONOMY: Dict[str, Any] = _load_skill_taxonomy()
# Pre-built lookup: alias → canonical skill name
_ALIAS_TO_CANONICAL: Dict[str, str] = {}
# Pre-built lookup: canonical → related {skill: weight}
_CANONICAL_RELATED: Dict[str, Dict[str, float]] = {}

for _canonical, _entry in (_TAXONOMY.get("skills") or {}).items():
    _ALIAS_TO_CANONICAL[_canonical] = _canonical
    for _alias in (_entry.get("aliases") or []):
        _ALIAS_TO_CANONICAL[_alias.lower()] = _canonical
    _CANONICAL_RELATED[_canonical] = {
        k.lower(): float(v) for k, v in (_entry.get("related") or {}).items()
    }


def normalized_text_token(value: Any) -> str:
    """Lowercase and strip punctuation from a string for fuzzy comparison."""
    if not isinstance(value, str):
        return ""
    text = re.sub(r"[^\w\s]", " ", (value or "").lower())
    return " ".join(text.split())


# ─── Skill synonym/alias map ─────────────────────────────────────────────────
# Maps common abbreviations and variants to a canonical lowercase form.
# Matching is done after normalizing both sides to their canonical form.
_SKILL_ALIASES: Dict[str, str] = {
    # JavaScript ecosystem
    "js": "javascript", "javascript": "javascript", "ecmascript": "javascript",
    "ts": "typescript", "typescript": "typescript",
    "react.js": "react", "reactjs": "react", "react": "react",
    "vue.js": "vue", "vuejs": "vue", "vue": "vue",
    "angular.js": "angular", "angularjs": "angular", "angular": "angular",
    "node.js": "nodejs", "nodejs": "nodejs", "node": "nodejs",
    "next.js": "nextjs", "nextjs": "nextjs",
    "nuxt.js": "nuxtjs", "nuxtjs": "nuxtjs",
    # Python / ML
    "python": "python", "py": "python",
    "ml": "machine learning", "machine learning": "machine learning",
    "ai": "artificial intelligence", "artificial intelligence": "artificial intelligence",
    "dl": "deep learning", "deep learning": "deep learning",
    "sklearn": "scikit-learn", "scikit-learn": "scikit-learn",
    "tf": "tensorflow", "tensorflow": "tensorflow",
    "pytorch": "pytorch", "torch": "pytorch",
    # Data / DB
    "sql": "sql", "postgresql": "postgresql", "postgres": "postgresql",
    "mysql": "mysql", "mssql": "sql server", "sql server": "sql server",
    "mongodb": "mongodb", "mongo": "mongodb",
    "elasticsearch": "elasticsearch", "elastic": "elasticsearch",
    # Cloud / DevOps
    "aws": "aws", "amazon web services": "aws",
    "gcp": "gcp", "google cloud": "gcp",
    "azure": "azure", "microsoft azure": "azure",
    "k8s": "kubernetes", "kubernetes": "kubernetes",
    "docker": "docker",
    "ci/cd": "cicd", "cicd": "cicd", "devops": "devops",
    # Java / JVM
    "java": "java", "kotlin": "kotlin", "scala": "scala",
    "spring": "spring", "spring boot": "spring boot",
    # .NET
    "c#": "csharp", "csharp": "csharp", ".net": "dotnet", "dotnet": "dotnet",
    # Other languages
    "go": "golang", "golang": "golang",
    "rust": "rust", "ruby": "ruby", "php": "php", "swift": "swift",
    "c++": "cpp", "cpp": "cpp", "c": "c",
    # Manual / physical work
    "staplerfahrer": "forklift", "gabelstapler": "forklift", "forklift": "forklift",
    "führerschein": "driving license", "driving license": "driving license",
    "führerschein b": "driving license b", "driving license b": "driving license b",
    # Hospitality
    "housekeeping": "housekeeping", "zimmerreinigung": "housekeeping",
    "küche": "kitchen", "kitchen": "kitchen", "gastro": "gastronomy",
    # Transferable / management skills (multilingual)
    "project management": "project management", "projektleitung": "project management",
    "projektmanagement": "project management", "gestion de projet": "project management",
    "gestione del progetto": "project management",
    "team leadership": "team leadership", "teamführung": "team leadership",
    "führung": "leadership", "leadership": "leadership",
    "kommunikation": "communication", "communication": "communication",
    "teamwork": "teamwork", "teamarbeit": "teamwork",
    "customer service": "customer service", "kundendienst": "customer service",
    "kundenbetreuung": "customer service", "service client": "customer service",
    "problem solving": "problem solving", "problemlösung": "problem solving",
    "organisation": "organisation", "organization": "organisation",
    "time management": "time management", "zeitmanagement": "time management",
    "accounting": "accounting", "buchhaltung": "accounting", "rechnungswesen": "accounting",
    "comptabilité": "accounting", "contabilità": "accounting",
    # Manual / logistics / warehousing
    "lagermitarbeiter": "warehouse worker", "lagerist": "warehouse worker",
    "warehouse worker": "warehouse worker", "warehouse": "warehouse",
    "montage": "assembly", "monteur": "assembly technician", "assembly": "assembly",
    "lieferant": "delivery", "lieferfahrer": "delivery driver",
    "delivery driver": "delivery driver", "fahrer": "driver", "driver": "driver",
    "reinigung": "cleaning", "cleaning": "cleaning", "haushaltsführung": "housekeeping",
    "hilfsarbeiter": "general helper", "aushilfe": "general helper",
    "handwerk": "skilled trade", "handwerker": "skilled tradesperson",
    "elektrik": "electrical work", "elektriker": "electrician", "electrician": "electrician",
    "sanitär": "plumbing", "klempner": "plumber", "plumber": "plumber",
    "maler": "painting", "painter": "painting",
    # Office / administrative
    "ms office": "microsoft office", "microsoft office": "microsoft office",
    "excel": "excel", "word": "word", "powerpoint": "powerpoint",
    "sap": "sap", "erp": "erp",
    "verwaltung": "administration", "administration": "administration",
    "datenerfassung": "data entry", "data entry": "data entry",
}


def _canonicalize_skill(skill: str) -> str:
    """Return the canonical lowercase alias for a skill string, or the normalized raw token."""
    token = normalized_text_token(skill)
    return _SKILL_ALIASES.get(token, token)


def _word_bounded_substring(needle: str, haystack: str) -> bool:
    """Return True only when *needle* appears as a complete word inside *haystack*.

    Prevents false-positive skill overlaps such as "java" matching "javascript".
    Uses ``\\b`` word-boundary anchors so "java" matches "core java backend" but
    not "javascript" or "javafx".
    """
    if not needle or not haystack:
        return False
    return bool(re.search(r"\b" + re.escape(needle) + r"\b", haystack))


def skills_overlap(job_skills: List[str], profile_skills: List[str]) -> float:
    """Compute skill overlap ratio between two skill lists.

    Uses a multi-tier matching strategy:
    1. Exact canonical match (via alias map)
    2. Substring containment (one skill contains the other)

    Returns a float 0.0–1.0 representing the proportion of job_skills
    that are covered by at least one profile_skill.
    Returns 0.0 if either list is empty.
    """
    if not job_skills or not profile_skills:
        return 0.0

    job_canonical = [_canonicalize_skill(s) for s in job_skills if s]
    profile_canonical = set(_canonicalize_skill(s) for s in profile_skills if s)
    profile_raw_tokens = set(normalized_text_token(s) for s in profile_skills if s)

    matched = 0
    for jc in job_canonical:
        if not jc:
            continue
        # Tier 1: exact canonical
        if jc in profile_canonical:
            matched += 1
            continue
        # Tier 2: substring containment with word boundaries (prevents "java" ⊂ "javascript")
        if any(_word_bounded_substring(jc, pc) or _word_bounded_substring(pc, jc) for pc in profile_canonical if pc):
            matched += 1
            continue
        # Tier 3: raw token substring with word boundaries
        job_raw = normalized_text_token(jc)
        if any(_word_bounded_substring(job_raw, pt) or _word_bounded_substring(pt, job_raw) for pt in profile_raw_tokens if pt):
            matched += 1

    return matched / len(job_canonical) if job_canonical else 0.0


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
    if company_obj is not None and hasattr(company_obj, "name"):
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

    # Heuristic role_type from title keywords (confidence 0.35 — overwritten by LLM later)
    role_type: Optional[str] = None
    for rt, keywords in {
        "manual": [
            "warehouse", "lager", "cleaning", "reinigung", "delivery", "driver", "fahrer",
            "packer", "sortierer", "lagermitarbeiter", "construction", "bauarbeiter",
            "helper", "hilfsarbeiter", "courier", "kurier", "forklift", "gabelstapler",
        ],
        "managerial": ["manager", "head of", "director", "chief", "vp ", "vice president"],
        "technical": [
            "engineer", "developer", "entwickler", "ingenieur", "programmer", "analyst",
            "devops", "architect",
        ],
        "administrative": [
            "administrator", "secretary", "receptionist", "sachbearbeiter", "assistant",
            "koordinator", "buchhalter",
        ],
        "service": [
            "customer service", "receptionist", "waitress", "waiter", "kellner",
            "servicemitarbeiter", "barista",
        ],
    }.items():
        if any(kw in title_lower for kw in keywords):
            role_type = rt
            break

    salary_max = extract_salary_max_chf(listing)
    remote = listing_is_remote(listing)

    # ─── Heuristic: career_changer_friendly (confidence 0.35) ────────────
    desc_lower = (desc_text or "").lower()
    _career_changer_signals = [
        "quereinsteiger", "quereinstieg", "career changer", "career change",
        "training provided", "einarbeitung", "keine erfahrung", "no experience required",
        "no experience needed", "will train", "we train", "wir bilden aus",
        "auch ohne erfahrung", "reconversion", "reconversion professionnelle",
        "anche senza esperienza",
    ]
    career_changer_friendly = any(sig in desc_lower for sig in _career_changer_signals)

    # ─── Heuristic: entry_barrier (confidence 0.35) ───────────────────────
    # Derive from experience requirements + qualification codes
    entry_barrier: Optional[str] = None
    if qualification_codes:
        high_qual_codes = {"bachelor", "master", "phd", "eidg. dipl.", "eidg dipl"}
        if any(qc.lower() in high_qual_codes for qc in qualification_codes):
            entry_barrier = "high"
        elif qualification_codes:
            entry_barrier = "medium"
    if entry_barrier is None:
        max_exp = max(experience_values) if experience_values else 0
        if max_exp >= 5:
            entry_barrier = "medium"
        elif max_exp == 0 and career_changer_friendly:
            entry_barrier = "none"
        else:
            entry_barrier = "low"

    # ─── Heuristic: physical_requirements ────────────────────────────────
    _physical_signals = [
        ("heavy lifting", "heavy lifting"), ("schweres heben", "heavy lifting"),
        ("körperlich", "physically demanding"), ("physically demanding", "physically demanding"),
        ("stehen", "prolonged standing"), ("standing", "prolonged standing"),
        ("outdoor", "outdoor work"), ("im freien", "outdoor work"),
        ("heben", "lifting"), ("lifting", "lifting"),
        ("tragen", "carrying"), ("carrying", "carrying"),
    ]
    physical_requirements = list({
        canonical for signal, canonical in _physical_signals
        if signal in desc_lower
    })

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
        "normalized_preferred_skills": None,
        "normalized_soft_skills": None,
        "normalized_physical_requirements": physical_requirements or None,
        "normalized_entry_barrier": entry_barrier,
        "normalized_career_changer_friendly": career_changer_friendly if career_changer_friendly else None,
        "normalized_hard_blockers": None,
        "normalized_education_levels": education_levels or None,
        "normalized_key_requirements": None,
        "normalized_role_type": role_type,
        "normalized_metadata": {
            "bootstrap": True,
            "provider": getattr(listing, "source", None) or getattr(listing, "platform", "unknown"),
            "company": company_name,
            "location": location_str,
            "qualification_codes": qualification_codes,
        },
    }


# ─── Semantic skill score ─────────────────────────────────────────────────────


def semantic_skills_score(
    job_skills: List[str], profile_skills: List[str]
) -> float:
    """Weighted semantic skill overlap using the skill taxonomy.

    Unlike ``skills_overlap`` (which is binary), this accounts for related skills:
    - Exact match → weight 1.0
    - Alias match → weight 1.0
    - Related skill from taxonomy → weight from taxonomy (e.g., 0.5–0.9)
    - String containment fallback → weight 0.5

    Returns a float 0.0–1.0 representing the *weighted* coverage of the job's
    required skills with the candidate's profile skills.
    """
    if not job_skills or not profile_skills:
        return 0.0

    profile_canonical_set = {
        _ALIAS_TO_CANONICAL.get(normalized_text_token(s), normalized_text_token(s))
        for s in profile_skills if s
    }

    total_weight = 0.0
    matched_weight = 0.0

    for js in job_skills:
        if not js:
            continue
        total_weight += 1.0
        job_token = normalized_text_token(js)
        job_canon = _ALIAS_TO_CANONICAL.get(job_token, job_token)

        # Tier 1: exact canonical match
        if job_canon in profile_canonical_set:
            matched_weight += 1.0
            continue

        # Tier 2: taxonomy-weighted related skill match
        best_related_weight = 0.0
        related_map = _CANONICAL_RELATED.get(job_canon, {})
        for prof_canon in profile_canonical_set:
            w = related_map.get(prof_canon, 0.0)
            if w > best_related_weight:
                best_related_weight = w
            rev_related = _CANONICAL_RELATED.get(prof_canon, {})
            w_rev = rev_related.get(job_canon, 0.0)
            if w_rev > best_related_weight:
                best_related_weight = w_rev

        if best_related_weight > 0.0:
            matched_weight += best_related_weight
            continue

        # Tier 3: string containment fallback
        job_raw = normalized_text_token(js)
        for prof_canon in profile_canonical_set:
            if prof_canon and (
                _word_bounded_substring(job_raw, prof_canon)
                or _word_bounded_substring(prof_canon, job_raw)
            ):
                matched_weight += 0.5
                break

    return matched_weight / total_weight if total_weight > 0 else 0.0


# ─── Structured pre-score ─────────────────────────────────────────────────────


def compute_prescore(job_norm: Dict[str, Any], profile_norm: Dict[str, Any]) -> float:
    """Compute a continuous pre-score (0–100) from normalized structured fields.

    This runs BEFORE the expensive LLM MATCH step and acts as a lightweight gate.
    It only uses fields available after normalization.

    Score breakdown (total 100):
    - Domain alignment (20 pts)
    - Seniority fit (15 pts)
    - Semantic skill overlap (25 pts)
    - Experience years fit (15 pts)
    - Entry barrier vs. qualifications (10 pts)
    - Language requirements (10 pts)
    - Qualification level match (5 pts)
    """
    score = 0.0

    try:
        from backend.data.domain_affinity import get_domain_affinity  # type: ignore
    except Exception:
        get_domain_affinity = None  # type: ignore

    # 1. Domain alignment (0–20 pts)
    job_domain = (job_norm.get("normalized_domain") or "").lower().strip()
    profile_domains = profile_norm.get("target_domains") or profile_norm.get("normalized_domains") or []
    if isinstance(profile_domains, str):
        profile_domains = [profile_domains]
    if job_domain and profile_domains:
        best_domain_aff = 0.0
        for pd in profile_domains:
            pd_str = (pd or "").lower().strip()
            if pd_str:
                if get_domain_affinity:
                    aff = get_domain_affinity(job_domain, pd_str)
                else:
                    aff = 1.0 if job_domain == pd_str else 0.0
                best_domain_aff = max(best_domain_aff, aff)
        score += best_domain_aff * 20.0
    elif not job_domain:
        score += 10.0  # neutral if domain unknown

    # 2. Seniority fit (0–15 pts)
    job_seniority = (job_norm.get("normalized_seniority") or "").lower()
    profile_seniority = (
        profile_norm.get("seniority")
        or profile_norm.get("target_seniority")
        or ""
    ).lower()
    _SENIORITY_SCORES: Dict[Tuple[str, str], float] = {
        ("junior", "junior"): 1.0, ("mid", "mid"): 1.0, ("senior", "senior"): 1.0,
        ("junior", "mid"): 0.6, ("mid", "junior"): 0.6,
        ("mid", "senior"): 0.6, ("senior", "mid"): 0.5,
        ("senior", "junior"): 0.1, ("junior", "senior"): 0.2,
    }
    if job_seniority and profile_seniority:
        seniority_fit = _SENIORITY_SCORES.get((job_seniority, profile_seniority), 0.5)
        score += seniority_fit * 15.0
    else:
        score += 7.5  # neutral

    # 3. Semantic skill overlap (0–25 pts)
    job_skills: List[str] = job_norm.get("normalized_required_skills") or []
    profile_skills: List[str] = (
        profile_norm.get("skills") or profile_norm.get("normalized_skills") or []
    )
    if job_skills and profile_skills:
        sem_score = semantic_skills_score(job_skills, profile_skills)
        score += sem_score * 25.0
    else:
        score += 12.5  # neutral if missing

    # 4. Experience years fit (0–15 pts)
    job_exp_min = job_norm.get("normalized_experience_min_years")
    job_exp_max = job_norm.get("normalized_experience_max_years")
    profile_exp = profile_norm.get("experience_years") or profile_norm.get("years_of_experience")
    if profile_exp is not None and (job_exp_min is not None or job_exp_max is not None):
        try:
            p_exp = float(profile_exp)
            j_min = float(job_exp_min) if job_exp_min is not None else 0.0
            j_max = float(job_exp_max) if job_exp_max is not None else j_min + 10.0
            if j_min <= p_exp <= j_max:
                score += 15.0
            elif p_exp < j_min:
                gap = j_min - p_exp
                score += max(0.0, 15.0 - gap * 3.0)
            else:
                score += 10.0  # slightly over-qualified
        except (TypeError, ValueError):
            score += 7.5  # neutral
    else:
        score += 7.5  # neutral

    # 5. Entry barrier vs. qualifications (0–10 pts)
    job_barrier = (job_norm.get("normalized_entry_barrier") or "").lower()
    profile_qualification = (
        profile_norm.get("qualification_level")
        or profile_norm.get("normalized_qualification_level")
        or ""
    ).lower()
    _BARRIER_QUAL_FIT: Dict[Tuple[str, str], float] = {
        ("none", "none"): 1.0, ("none", "low"): 1.0, ("none", "medium"): 1.0, ("none", "high"): 1.0,
        ("low", "none"): 0.8, ("low", "low"): 1.0, ("low", "medium"): 1.0, ("low", "high"): 1.0,
        ("medium", "none"): 0.4, ("medium", "low"): 0.7, ("medium", "medium"): 1.0, ("medium", "high"): 1.0,
        ("high", "none"): 0.1, ("high", "low"): 0.4, ("high", "medium"): 0.8, ("high", "high"): 1.0,
    }
    if job_barrier and profile_qualification:
        fit = _BARRIER_QUAL_FIT.get((job_barrier, profile_qualification), 0.5)
        score += fit * 10.0
    else:
        score += 5.0  # neutral

    # 6. Language requirements (0–10 pts)
    job_langs: List[Dict] = job_norm.get("normalized_required_languages") or []
    profile_langs = profile_norm.get("languages") or profile_norm.get("normalized_languages") or []
    if job_langs and profile_langs:
        profile_lang_codes = set()
        for lang_item in profile_langs:
            if isinstance(lang_item, dict):
                code = (lang_item.get("code") or "").lower()
            else:
                code = str(lang_item).lower()
            if code:
                profile_lang_codes.add(code)
        matched_langs = sum(
            1 for jl in job_langs if (jl.get("code") or "").lower() in profile_lang_codes
        )
        lang_ratio = matched_langs / len(job_langs) if job_langs else 1.0
        score += lang_ratio * 10.0
    else:
        score += 5.0  # neutral

    # 7. Qualification level match (0–5 pts)
    job_qual = (job_norm.get("normalized_qualification_level") or "").lower()
    if profile_qualification and job_qual:
        _QUAL_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "bachelor": 2, "master": 3, "phd": 4}
        p_rank = _QUAL_RANK.get(profile_qualification, 1)
        j_rank = _QUAL_RANK.get(job_qual, 1)
        if p_rank >= j_rank:
            score += 5.0
        else:
            score += max(0.0, 5.0 - (j_rank - p_rank) * 2.0)
    else:
        score += 2.5  # neutral

    return min(100.0, max(0.0, score))


# ─── Job posting quality ──────────────────────────────────────────────────────


def compute_posting_quality(description: str) -> float:
    """Rate the information quality of a job description (0.0–1.0).

    Higher score = better structured, more informative posting.
    Used to down-weight jobs that lack detail (making MATCH less reliable).

    Signals:
    - Length (>= 300 words = max signal)
    - Salary/compensation mentioned
    - CEFR language level mentioned
    - Explicit skills/requirements section
    - Structured sections (responsibilities, requirements, etc.)
    - Contact info / application process described
    """
    if not description:
        return 0.1

    score = 0.0
    text = description.lower()
    word_count = len(description.split())

    # 1. Length (0.0–0.30)
    if word_count >= 300:
        score += 0.30
    elif word_count >= 150:
        score += 0.15 + 0.15 * ((word_count - 150) / 150)
    elif word_count >= 50:
        score += 0.05 + 0.10 * ((word_count - 50) / 100)
    else:
        score += 0.02

    # 2. Salary / compensation (0.0–0.20)
    _salary_patterns = [
        r"chf\s*\d", r"\d+\s*chf", r"salary", r"lohn", r"gehalt", r"salaire",
        r"\d+[kK]\s*[-\u2013]\s*\d+[kK]", r"\bcompensation\b", r"\bverg.tung\b",
        r"per\s+(?:year|month|annum|jahr|monat)", r"j.hrlich", r"monatlich",
    ]
    if any(re.search(p, text) for p in _salary_patterns):
        score += 0.20

    # 3. CEFR language levels (0.0–0.10)
    if re.search(r"\b[abc][12]\b", text):
        score += 0.10

    # 4. Explicit skills/requirements section (0.0–0.15)
    _req_signals = [
        "requirements", "anforderungen", "qualifications", "qualifikationen",
        "your profile", "ihr profil", "we require", "you have", "you bring",
        "sie bringen", "must have", "experience with", "erfahrung mit", "kenntnisse",
    ]
    req_hits = sum(1 for sig in _req_signals if sig in text)
    score += min(0.15, req_hits * 0.05)

    # 5. Structured sections (0.0–0.15)
    _section_markers = [
        "responsibilities", "aufgaben", "your tasks", "what you will do",
        "we offer", "wir bieten", "benefits", "key responsibilities",
        "about the role", "what we expect",
    ]
    section_hits = sum(1 for m in _section_markers if m in text)
    score += min(0.15, section_hits * 0.05)

    # 6. Application / contact info (0.0–0.10)
    _apply_signals = [
        "apply", "bewerben", "postuler", "candidature",
        "send your cv", "send your resume", "contact us",
        "application deadline", "bewerbungsfrist", "@",
    ]
    if any(sig in text for sig in _apply_signals):
        score += 0.10

    return min(1.0, score)
