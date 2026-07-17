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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# ─── Lazy import of embedding tier (Phase 1) ─────────────────────────────────
# Imported lazily inside semantic_skills_score() so this module stays importable
# without downloading a model or depending on a machine-learning package.

logger = logging.getLogger(__name__)

_INVALID_LISTING_ID_TOKENS = {
    "none",
    "null",
    "unknown",
    "n/a",
    "na",
    "undefined",
}

_TRACKING_QUERY_PARAM_NAMES = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "mkt_tok",
    "ref",
    "ref_src",
    "yclid",
}
_TRACKING_QUERY_PARAM_PREFIXES = ("utm_",)


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
    for _alias in _entry.get("aliases") or []:
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
    "js": "javascript",
    "javascript": "javascript",
    "ecmascript": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "react.js": "react",
    "reactjs": "react",
    "react": "react",
    "vue.js": "vue",
    "vuejs": "vue",
    "vue": "vue",
    "angular.js": "angular",
    "angularjs": "angular",
    "angular": "angular",
    "node.js": "nodejs",
    "nodejs": "nodejs",
    "node": "nodejs",
    "next.js": "nextjs",
    "nextjs": "nextjs",
    "nuxt.js": "nuxtjs",
    "nuxtjs": "nuxtjs",
    # Python / ML
    "python": "python",
    "py": "python",
    "ml": "machine learning",
    "machine learning": "machine learning",
    "ai": "artificial intelligence",
    "artificial intelligence": "artificial intelligence",
    "dl": "deep learning",
    "deep learning": "deep learning",
    "sklearn": "scikit-learn",
    "scikit-learn": "scikit-learn",
    "tf": "tensorflow",
    "tensorflow": "tensorflow",
    "pytorch": "pytorch",
    "torch": "pytorch",
    # Data / DB
    "sql": "sql",
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "mysql": "mysql",
    "mssql": "sql server",
    "sql server": "sql server",
    "mongodb": "mongodb",
    "mongo": "mongodb",
    "elasticsearch": "elasticsearch",
    "elastic": "elasticsearch",
    # Cloud / DevOps
    "aws": "aws",
    "amazon web services": "aws",
    "gcp": "gcp",
    "google cloud": "gcp",
    "azure": "azure",
    "microsoft azure": "azure",
    "k8s": "kubernetes",
    "kubernetes": "kubernetes",
    "docker": "docker",
    "ci/cd": "cicd",
    "cicd": "cicd",
    "devops": "devops",
    # Java / JVM
    "java": "java",
    "kotlin": "kotlin",
    "scala": "scala",
    "spring": "spring",
    "spring boot": "spring boot",
    # .NET
    "c#": "csharp",
    "csharp": "csharp",
    ".net": "dotnet",
    "dotnet": "dotnet",
    # Other languages
    "go": "golang",
    "golang": "golang",
    "rust": "rust",
    "ruby": "ruby",
    "php": "php",
    "swift": "swift",
    "c++": "cpp",
    "cpp": "cpp",
    "c": "c",
    # Manual / physical work
    "staplerfahrer": "forklift",
    "gabelstapler": "forklift",
    "forklift": "forklift",
    "führerschein": "driving license",
    "driving license": "driving license",
    "führerschein b": "driving license b",
    "driving license b": "driving license b",
    # Hospitality
    "housekeeping": "housekeeping",
    "zimmerreinigung": "housekeeping",
    "küche": "kitchen",
    "kitchen": "kitchen",
    "gastro": "gastronomy",
    # Transferable / management skills (multilingual)
    "project management": "project management",
    "projektleitung": "project management",
    "projektmanagement": "project management",
    "gestion de projet": "project management",
    "gestione del progetto": "project management",
    "team leadership": "team leadership",
    "teamführung": "team leadership",
    "führung": "leadership",
    "leadership": "leadership",
    "kommunikation": "communication",
    "communication": "communication",
    "teamwork": "teamwork",
    "teamarbeit": "teamwork",
    "customer service": "customer service",
    "kundendienst": "customer service",
    "kundenbetreuung": "customer service",
    "service client": "customer service",
    "problem solving": "problem solving",
    "problemlösung": "problem solving",
    "organisation": "organisation",
    "organization": "organisation",
    "time management": "time management",
    "zeitmanagement": "time management",
    "accounting": "accounting",
    "buchhaltung": "accounting",
    "rechnungswesen": "accounting",
    "comptabilité": "accounting",
    "contabilità": "accounting",
    # Manual / logistics / warehousing
    "lagermitarbeiter": "warehouse worker",
    "lagerist": "warehouse worker",
    "warehouse worker": "warehouse worker",
    "warehouse": "warehouse",
    "montage": "assembly",
    "monteur": "assembly technician",
    "assembly": "assembly",
    "lieferant": "delivery",
    "lieferfahrer": "delivery driver",
    "delivery driver": "delivery driver",
    "fahrer": "driver",
    "driver": "driver",
    "reinigung": "cleaning",
    "cleaning": "cleaning",
    "haushaltsführung": "housekeeping",
    "hilfsarbeiter": "general helper",
    "aushilfe": "general helper",
    "handwerk": "skilled trade",
    "handwerker": "skilled tradesperson",
    "elektrik": "electrical work",
    "elektriker": "electrician",
    "electrician": "electrician",
    "sanitär": "plumbing",
    "klempner": "plumber",
    "plumber": "plumber",
    "maler": "painting",
    "painter": "painting",
    # Office / administrative
    "ms office": "microsoft office",
    "microsoft office": "microsoft office",
    "excel": "excel",
    "word": "word",
    "powerpoint": "powerpoint",
    "sap": "sap",
    "erp": "erp",
    "verwaltung": "administration",
    "administration": "administration",
    "datenerfassung": "data entry",
    "data entry": "data entry",
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
        if any(
            _word_bounded_substring(jc, pc) or _word_bounded_substring(pc, jc)
            for pc in profile_canonical
            if pc
        ):
            matched += 1
            continue
        # Tier 3: raw token substring with word boundaries
        job_raw = normalized_text_token(jc)
        if any(
            _word_bounded_substring(job_raw, pt) or _word_bounded_substring(pt, job_raw)
            for pt in profile_raw_tokens
            if pt
        ):
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


def normalize_listing_identifier(value: Any) -> str:
    """Return a clean listing identifier token or an empty string when unusable."""
    if value is None:
        return ""
    token = str(value).strip()
    if not token:
        return ""
    if token.lower() in _INVALID_LISTING_ID_TOKENS:
        return ""
    return token


def _is_tracking_query_param(name: str) -> bool:
    token = str(name or "").strip().lower()
    if not token:
        return False
    return token in _TRACKING_QUERY_PARAM_NAMES or any(
        token.startswith(prefix) for prefix in _TRACKING_QUERY_PARAM_PREFIXES
    )


def _canonicalize_listing_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    if "://" not in raw and raw.lower().startswith("www."):
        raw = f"https://{raw}"

    parsed = urlsplit(raw)
    if not parsed.scheme and not parsed.netloc:
        return raw.lower().rstrip("/")

    hostname = (parsed.hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    netloc = hostname
    if parsed.port is not None:
        is_default_port = (parsed.scheme.lower() == "http" and parsed.port == 80) or (
            parsed.scheme.lower() == "https" and parsed.port == 443
        )
        if not is_default_port:
            netloc = f"{netloc}:{parsed.port}"

    path = re.sub(r"/{2,}", "/", (parsed.path or "").strip()).lower() or "/"
    if path != "/":
        path = path.rstrip("/")

    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        normalized_key = key.strip().lower()
        if _is_tracking_query_param(normalized_key):
            continue
        query_items.append((normalized_key, (value or "").strip().lower()))
    query_items.sort()
    query = urlencode(query_items, doseq=True)

    canonical = urlunsplit(("", netloc, path, query, ""))
    return canonical.lstrip("//")


def listing_identity_key(listing) -> Optional[str]:
    """Return a ``platform:platform_id`` dedup key, or *None* if unavailable."""
    platform = getattr(listing, "source", None) or getattr(listing, "platform", None)
    platform_id = normalize_listing_identifier(
        getattr(listing, "id", None) or getattr(listing, "platform_job_id", None)
    )
    if platform and platform_id:
        return f"{platform}:{platform_id}"
    return None


def listing_url_token(listing) -> str:
    """Return the normalised external URL for URL-based deduplication."""
    url = getattr(listing, "external_url", None) or getattr(listing, "url", None) or ""
    return _canonicalize_listing_url(url)


def listing_fuzzy_key(listing) -> str:
    """Return a ``normalized_title::normalized_company`` key for fuzzy dedup."""
    title = normalized_text_token(getattr(listing, "title", ""))
    company = normalized_text_token(extract_company_name(listing))
    if not title and not company:
        return ""
    return f"{title}::{company}"


def listing_description_fingerprint(listing) -> Optional[str]:
    """Return a SHA-256 fingerprint of the first 500 normalised chars of the description.

    Used as Tier-4 deduplication: catches cross-provider reposts where the
    identity key and fuzzy key differ but the body text is virtually identical
    (e.g., the same opening posted on both JobRoom and StepStone).

    Returns *None* if the description is too short to be meaningful (<50 chars),
    preventing false-positive collisions on stub listings.
    """
    import hashlib

    desc_text: str = ""
    descs = getattr(listing, "descriptions", None)
    if descs:
        first = descs[0]
        desc_text = (
            first.description
            if hasattr(first, "description")
            else (first.get("description", "") if isinstance(first, dict) else "")
        ) or ""
    if not desc_text:
        desc_text = getattr(listing, "description", None) or ""

    if len(desc_text.strip()) < 50:
        return None

    # Strip HTML tags, lowercase, collapse whitespace, take first 500 chars.
    clean = re.sub(r"<[^>]+>", " ", desc_text)
    clean = re.sub(r"\s+", " ", clean.lower().strip())
    clean = clean[:500]
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()


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

    # Cross-reference title-inferred seniority with description experience requirements.
    # "Associate Software Engineer" (title=mid) with "10+ years required" (desc) → upgrade to senior.
    if experience_values:
        max_exp = max(experience_values)
        if max_exp >= 7 and seniority in (None, "mid"):
            seniority = "senior"
        elif max_exp >= 3 and seniority is None:
            seniority = "mid"

    # Heuristic role_type from title keywords (confidence 0.35 — overwritten by LLM later).
    # PRIORITY ORDER MATTERS: check managerial before domain-specific types so that
    # "Warehouse Manager" → managerial (not manual) and "Senior Engineer" → technical (not manual).
    role_type: Optional[str] = None
    _ROLE_TYPE_PRIORITY = [
        (
            "managerial",
            [
                "manager",
                "head of",
                "director",
                "chief",
                "vp ",
                "vice president",
                "leiter",
                "leiterin",
                "führungskraft",
                "teamleiter",
                "teamleiterin",
            ],
        ),
        (
            "technical",
            [
                "engineer",
                "developer",
                "entwickler",
                "ingenieur",
                "programmer",
                "analyst",
                "devops",
                "architect",
            ],
        ),
        (
            "administrative",
            [
                "administrator",
                "secretary",
                "receptionist",
                "sachbearbeiter",
                "assistant",
                "koordinator",
                "buchhalter",
            ],
        ),
        (
            "service",
            [
                "customer service",
                "waitress",
                "waiter",
                "kellner",
                "servicemitarbeiter",
                "barista",
            ],
        ),
        (
            "manual",
            [
                "warehouse",
                "lager",
                "cleaning",
                "reinigung",
                "delivery",
                "driver",
                "fahrer",
                "packer",
                "sortierer",
                "lagermitarbeiter",
                "construction",
                "bauarbeiter",
                "helper",
                "hilfsarbeiter",
                "courier",
                "kurier",
                "forklift",
                "gabelstapler",
            ],
        ),
    ]
    for rt, keywords in _ROLE_TYPE_PRIORITY:
        if any(kw in title_lower for kw in keywords):
            role_type = rt
            break

    salary_max = extract_salary_max_chf(listing)
    remote = listing_is_remote(listing)

    # ─── Heuristic: career_changer_friendly (confidence 0.35) ────────────
    desc_lower = (desc_text or "").lower()
    _career_changer_signals = [
        "quereinsteiger",
        "quereinstieg",
        "career changer",
        "career change",
        "training provided",
        "einarbeitung",
        "keine erfahrung",
        "no experience required",
        "no experience needed",
        "will train",
        "we train",
        "wir bilden aus",
        "auch ohne erfahrung",
        "reconversion",
        "reconversion professionnelle",
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
        ("heavy lifting", "heavy lifting"),
        ("schweres heben", "heavy lifting"),
        ("körperlich", "physically demanding"),
        ("physically demanding", "physically demanding"),
        ("stehen", "prolonged standing"),
        ("standing", "prolonged standing"),
        ("outdoor", "outdoor work"),
        ("im freien", "outdoor work"),
        ("heben", "lifting"),
        ("lifting", "lifting"),
        ("tragen", "carrying"),
        ("carrying", "carrying"),
    ]
    physical_requirements = list(
        {canonical for signal, canonical in _physical_signals if signal in desc_lower}
    )

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
        "normalized_career_changer_friendly": career_changer_friendly
        if career_changer_friendly
        else None,
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


def semantic_skills_score(job_skills: List[str], profile_skills: List[str]) -> float:
    """Weighted semantic skill overlap using the skill taxonomy + embeddings.

    Four-tier matching strategy (Phase 1 upgrade):
    1. Exact canonical match → weight 1.0
    2. Alias match → weight 1.0 (resolved via _ALIAS_TO_CANONICAL)
    3. Taxonomy-weighted related skill → weight from taxonomy (0.0–1.0)
    4. Deterministic local similarity → similarity weight if above threshold
    5. String containment fallback → weight 0.3 (reduced from 0.5 for precision)

    Returns a float 0.0–1.0 representing the *weighted* coverage of the job's
    required skills with the candidate's profile skills.
    """
    if not job_skills or not profile_skills:
        return 0.0

    # Lazy imports for embedding tier — avoids hard dependency at module load time
    _emb_available = False
    _emb_threshold = 0.65
    _best_embedding_match = None
    try:
        from backend.core.config import settings as _settings

        if getattr(_settings, "SKILL_EMBEDDING_ENABLED", True):
            from backend.services.search.skill_embeddings import (  # type: ignore
                best_embedding_match as _best_embedding_match,
            )
            from backend.services.search.skill_embeddings import (
                is_available as _emb_is_available,
            )

            _emb_available = _emb_is_available()
            _emb_threshold = float(getattr(_settings, "SKILL_EMBEDDING_THRESHOLD", 0.65))
    except Exception:
        pass

    profile_canonical_set = {
        _ALIAS_TO_CANONICAL.get(normalized_text_token(s), normalized_text_token(s))
        for s in profile_skills
        if s
    }
    # Build a plain list for embedding comparison (use raw tokens, not canonical only)
    profile_raw_list: List[str] = [normalized_text_token(s) for s in profile_skills if s]

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

        # Tier 2.5 (Phase 1): embedding cosine similarity
        if _emb_available and _best_embedding_match is not None:
            emb_score = _best_embedding_match(js, profile_raw_list, threshold=_emb_threshold)
            if emb_score > 0.0:
                matched_weight += emb_score
                continue

        # Tier 3: string containment fallback (reduced weight 0.3 for precision)
        job_raw = normalized_text_token(js)
        for prof_canon in profile_canonical_set:
            if prof_canon and (
                _word_bounded_substring(job_raw, prof_canon)
                or _word_bounded_substring(prof_canon, job_raw)
            ):
                matched_weight += 0.3
                break

    return matched_weight / total_weight if total_weight > 0 else 0.0


# ─── Structured pre-score ─────────────────────────────────────────────────────


def compute_prescore(
    job_norm: Dict[str, Any],
    profile_norm: Dict[str, Any],
    preference_signals: Optional[Dict[str, Any]] = None,
) -> float:
    """Compute a continuous pre-score (0–100) from normalized structured fields.

    This runs BEFORE the expensive LLM MATCH step and acts as a lightweight gate.
    It only uses fields available after normalization.

    Score breakdown (total max ~105):
    - Domain alignment (20 pts)
    - Seniority fit (15 pts)
    - Semantic skill overlap (0–25 pts, domain-aware weight)
    - Experience years fit (15 pts)
    - Entry barrier vs. qualifications (10 pts)
    - Language requirements (10 pts)
    - Qualification level match (5 pts)
    - Posting quality bonus/penalty (−8 to +5 pts)
    - User preference alignment (up to +5 bonus / −5 penalty, gated)
    """
    score = 0.0

    def job_value(field: str):
        value = job_norm.get(field)
        return value if value is not None else job_norm.get(f"normalized_{field}")

    try:
        from backend.data.domain_affinity import get_domain_affinity  # type: ignore
    except Exception:
        get_domain_affinity = None  # type: ignore

    # 1. Domain alignment (0–20 pts)
    job_domain = str(job_value("domain") or "").lower().strip()
    profile_domains = (
        profile_norm.get("target_domains")
        or profile_norm.get("normalized_domains")
        or profile_norm.get("intent_domain")
        or profile_norm.get("domain")
        or []
    )
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
    job_seniority = str(job_value("seniority") or "").lower()
    profile_seniority = (
        profile_norm.get("intent_seniority")
        or profile_norm.get("target_seniority")
        or profile_norm.get("seniority")
        or ""
    ).lower()
    _SENIORITY_SCORES: Dict[Tuple[str, str], float] = {
        ("junior", "junior"): 1.0,
        ("mid", "mid"): 1.0,
        ("senior", "senior"): 1.0,
        ("junior", "mid"): 0.6,
        ("mid", "junior"): 0.6,
        ("mid", "senior"): 0.6,
        ("senior", "mid"): 0.5,
        ("senior", "junior"): 0.1,
        ("junior", "senior"): 0.2,
    }
    if job_seniority and profile_seniority:
        seniority_fit = _SENIORITY_SCORES.get((job_seniority, profile_seniority), 0.5)
        score += seniority_fit * 15.0
    else:
        score += 7.5  # neutral

    # 3. Semantic skill overlap (0–25 pts, domain-aware weight)
    # Manual and service roles rarely list technical skills — penalising a qualified
    # warehouse worker for not having Python is counterproductive.  Reduce the skill
    # maximum for non-technical role types and redistribute to experience/entry-barrier.
    job_role_type_for_skills = str(job_value("role_type") or "").lower().strip()
    _SKILL_MAX_BY_ROLE_TYPE: Dict[str, float] = {
        "manual": 10.0,
        "service": 15.0,
        "technical": 25.0,
        "professional": 25.0,
        "managerial": 20.0,
        "administrative": 18.0,
        "creative": 20.0,
    }
    skill_max = _SKILL_MAX_BY_ROLE_TYPE.get(job_role_type_for_skills, 25.0)
    skill_neutral = skill_max / 2.0  # neutral when data is missing

    job_skills: List[str] = job_value("required_skills") or []
    profile_skills: List[str] = (
        profile_norm.get("intent_skills")
        or profile_norm.get("skills")
        or profile_norm.get("normalized_skills")
        or []
    )
    if job_skills and profile_skills:
        sem_score = semantic_skills_score(job_skills, profile_skills)
        score += sem_score * skill_max
    else:
        score += skill_neutral  # neutral if missing

    # 4. Experience years fit (0–15 pts)
    job_exp_min = job_value("experience_min_years")
    job_exp_max = job_value("experience_max_years")
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
    job_barrier = str(job_value("entry_barrier") or "").lower()
    profile_qualification = (
        profile_norm.get("intent_qualification_level")
        or profile_norm.get("qualification_level")
        or profile_norm.get("normalized_qualification_level")
        or ""
    ).lower()
    _BARRIER_QUAL_FIT: Dict[Tuple[str, str], float] = {
        ("none", "none"): 1.0,
        ("none", "low"): 1.0,
        ("none", "medium"): 1.0,
        ("none", "high"): 1.0,
        ("low", "none"): 0.8,
        ("low", "low"): 1.0,
        ("low", "medium"): 1.0,
        ("low", "high"): 1.0,
        ("medium", "none"): 0.4,
        ("medium", "low"): 0.7,
        ("medium", "medium"): 1.0,
        ("medium", "high"): 1.0,
        ("high", "none"): 0.1,
        ("high", "low"): 0.4,
        ("high", "medium"): 0.8,
        ("high", "high"): 1.0,
    }
    if job_barrier and profile_qualification:
        fit = _BARRIER_QUAL_FIT.get((job_barrier, profile_qualification), 0.5)
        score += fit * 10.0
    else:
        score += 5.0  # neutral

    # 6. Language requirements (0–10 pts)
    job_langs: List[Dict] = job_value("required_languages") or []
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
    job_qual = str(job_value("qualification_level") or "").lower()
    if profile_qualification and job_qual:
        _QUAL_RANK = {
            "none": 0,
            "low": 1,
            "medium": 2,
            "high": 3,
            "bachelor": 2,
            "master": 3,
            "phd": 4,
        }
        p_rank = _QUAL_RANK.get(profile_qualification, 1)
        j_rank = _QUAL_RANK.get(job_qual, 1)
        if p_rank >= j_rank:
            score += 5.0
        else:
            score += max(0.0, 5.0 - (j_rank - p_rank) * 2.0)
    else:
        score += 2.5  # neutral

    # 8. Posting quality bonus/penalty (−8 to +5 pts)
    # High-quality postings (clear requirements, salary, structure) are more reliable
    # for matching.  Low-quality / template / spam postings deserve a prescore penalty
    # because MATCH analysis will be less accurate on thin descriptions.
    posting_quality = job_norm.get("posting_quality")
    if posting_quality is not None:
        try:
            pq = float(posting_quality)
            if pq >= 0.6:
                score += 5.0  # well-structured, informative posting
            elif pq < 0.3:
                score -= 8.0  # sparse / template / spam posting
            # between 0.3 and 0.6: no adjustment (neutral)
        except (TypeError, ValueError):
            pass

    # 9. User preference alignment (−5 to +5 pts bonus, gated by signal_count)
    try:
        from backend.core.config import settings as _cfg

        if (
            _cfg.PREFERENCE_PRESCORE_ENABLED
            and preference_signals
            and preference_signals.get("signal_count", 0) >= _cfg.PREFERENCE_MIN_SIGNAL_COUNT
        ):
            pref_delta = 0.0
            job_domain = str(job_value("domain") or "").lower().strip()
            job_seniority = str(job_value("seniority") or "").lower().strip()
            job_skills_set = {s.lower() for s in (job_value("required_skills") or [])}

            # +3 if domain is in top preferred domains
            preferred_domains = [
                d.lower() for d in (preference_signals.get("preferred_domains") or [])
            ]
            avoided_domains = [d.lower() for d in (preference_signals.get("avoided_domains") or [])]
            if job_domain and job_domain in preferred_domains[:3]:
                pref_delta += 3.0
            elif job_domain and job_domain in avoided_domains:
                pref_delta -= 4.0  # penalise consistently-avoided domains

            # +2 if seniority is preferred
            preferred_seniority = [
                s.lower() for s in (preference_signals.get("preferred_seniority") or [])
            ]
            if job_seniority and job_seniority in preferred_seniority:
                pref_delta += 2.0

            # +2 if ≥2 preferred skills overlap
            preferred_skills = {
                s.lower() for s in (preference_signals.get("preferred_skills") or [])
            }
            overlap = job_skills_set & preferred_skills
            if len(overlap) >= 2:
                pref_delta += min(2.0, len(overlap) * 0.5)

            # Progressive dealbreaker escalation: penalise based on repeat dismissal tiers
            # Tier 1 (≥3): −3 pts · Tier 2 (≥6): −5 pts · Tier 3 (≥10): −8 pts
            # Only applied when the current job actually matches the dismissed pattern.
            try:
                tier1 = int(getattr(_cfg, "DEALBREAKER_ESCALATION_TIER1", 3))
                tier2 = int(getattr(_cfg, "DEALBREAKER_ESCALATION_TIER2", 6))
                tier3 = int(getattr(_cfg, "DEALBREAKER_ESCALATION_TIER3", 10))
            except Exception:
                tier1, tier2, tier3 = 3, 6, 10

            dealbreakers = preference_signals.get("dealbreaker_patterns") or {}
            for signal, count in dealbreakers.items():
                if count < tier1:
                    continue
                penalty = -3.0 if count < tier2 else (-5.0 if count < tier3 else -8.0)
                if (
                    signal == "too_senior"
                    and job_seniority == "senior"
                    and profile_seniority in ("junior", "mid")
                ):
                    pref_delta += penalty
                elif (
                    signal == "too_junior"
                    and job_seniority == "junior"
                    and profile_seniority in ("senior", "mid")
                ):
                    pref_delta += penalty
                elif signal == "wrong_domain" and job_domain and job_domain in avoided_domains:
                    pref_delta += penalty

            score += max(-5.0, min(5.0, pref_delta))
    except Exception:
        pass  # preference injection is a bonus — never block scoring

    return min(100.0, max(0.0, score))


# ─── Swiss implicit language inference ───────────────────────────────────────

# Canton → primary administrative language code (ISO 639-1)
_CANTON_LANGUAGE_MAP: Dict[str, str] = {
    # German-speaking cantons
    "zurich": "de",
    "zürich": "de",
    "zh": "de",
    "bern": "de",
    "be": "de",
    "lucerne": "de",
    "luzern": "de",
    "lu": "de",
    "uri": "de",
    "ur": "de",
    "schwyz": "de",
    "sz": "de",
    "obwalden": "de",
    "ow": "de",
    "nidwalden": "de",
    "nw": "de",
    "glarus": "de",
    "gl": "de",
    "zug": "de",
    "zg": "de",
    "solothurn": "de",
    "so": "de",
    "basel-stadt": "de",
    "basel": "de",
    "bs": "de",
    "basel-landschaft": "de",
    "baselland": "de",
    "bl": "de",
    "schaffhausen": "de",
    "sh": "de",
    "appenzell": "de",
    "ar": "de",
    "ai": "de",
    "st. gallen": "de",
    "st gallen": "de",
    "sg": "de",
    "graubünden": "de",
    "graubuenden": "de",
    "gr": "de",
    "aargau": "de",
    "ag": "de",
    "thurgau": "de",
    "tg": "de",
    # French-speaking cantons (Romandy)
    "geneva": "fr",
    "genève": "fr",
    "genf": "fr",
    "ge": "fr",
    "vaud": "fr",
    "vd": "fr",
    "neuchâtel": "fr",
    "neuchatel": "fr",
    "ne": "fr",
    "jura": "fr",
    "ju": "fr",
    "fribourg": "fr",
    "freiburg": "fr",
    "fr": "fr",
    # Italian-speaking canton
    "ticino": "it",
    "ti": "it",
    # Valais / Wallis: bilingual (de/fr) — default German
    "valais": "fr",
    "wallis": "de",
    "vs": "de",
}

_CITY_LANGUAGE_MAP: Dict[str, str] = {
    "zürich": "de",
    "zurich": "de",
    "bern": "de",
    "basel": "de",
    "winterthur": "de",
    "lucerne": "de",
    "luzern": "de",
    "st. gallen": "de",
    "biel": "de",
    "thun": "de",
    "köniz": "de",
    "uster": "de",
    "genf": "fr",
    "geneva": "fr",
    "genève": "fr",
    "lausanne": "fr",
    "fribourg": "fr",
    "biel/bienne": "fr",
    "lugano": "it",
    "bellinzona": "it",
    "locarno": "it",
}


def infer_implicit_language(location_str: Optional[str]) -> Optional[str]:
    """Infer the predominant spoken language from a Swiss location string.

    Returns an ISO 639-1 language code ("de", "fr", "it") or None when the
    location cannot be mapped.  Used by the MATCH prompt as a soft tiebreaker
    when the job posting does not explicitly list language requirements.

    The heuristic is city-first, then canton-name matching. Only active when
    ``SWISS_IMPLICIT_LANGUAGE_ENABLED`` is True (default).
    """
    try:
        from backend.core.config import settings as _cfg

        if not _cfg.SWISS_IMPLICIT_LANGUAGE_ENABLED:
            return None
    except Exception:
        return None

    if not location_str:
        return None

    text = location_str.lower().strip()

    # City lookup (highest precision) — use word boundaries to avoid
    # partial-word false positives (e.g. "bern" inside "berlin").
    for city, lang in _CITY_LANGUAGE_MAP.items():
        if re.search(r"\b" + re.escape(city) + r"\b", text):
            return lang

    # Canton lookup
    for canton, lang in _CANTON_LANGUAGE_MAP.items():
        if re.search(r"\b" + re.escape(canton) + r"\b", text):
            return lang

    return None


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
        r"chf\s*\d",
        r"\d+\s*chf",
        r"salary",
        r"lohn",
        r"gehalt",
        r"salaire",
        r"\d+[kK]\s*[-\u2013]\s*\d+[kK]",
        r"\bcompensation\b",
        r"\bverg.tung\b",
        r"per\s+(?:year|month|annum|jahr|monat)",
        r"j.hrlich",
        r"monatlich",
    ]
    if any(re.search(p, text) for p in _salary_patterns):
        score += 0.20

    # 3. CEFR language levels (0.0–0.10)
    if re.search(r"\b[abc][12]\b", text):
        score += 0.10

    # 4. Explicit skills/requirements section (0.0–0.15)
    _req_signals = [
        "requirements",
        "anforderungen",
        "qualifications",
        "qualifikationen",
        "your profile",
        "ihr profil",
        "we require",
        "you have",
        "you bring",
        "sie bringen",
        "must have",
        "experience with",
        "erfahrung mit",
        "kenntnisse",
    ]
    req_hits = sum(1 for sig in _req_signals if sig in text)
    score += min(0.15, req_hits * 0.05)

    # 5. Structured sections (0.0–0.15)
    _section_markers = [
        "responsibilities",
        "aufgaben",
        "your tasks",
        "what you will do",
        "we offer",
        "wir bieten",
        "benefits",
        "key responsibilities",
        "about the role",
        "what we expect",
    ]
    section_hits = sum(1 for m in _section_markers if m in text)
    score += min(0.15, section_hits * 0.05)

    # 6. Application / contact info (0.0–0.10)
    _apply_signals = [
        "apply",
        "bewerben",
        "postuler",
        "candidature",
        "send your cv",
        "send your resume",
        "contact us",
        "application deadline",
        "bewerbungsfrist",
        "@",
    ]
    if any(sig in text for sig in _apply_signals):
        score += 0.10

    return min(1.0, score)
