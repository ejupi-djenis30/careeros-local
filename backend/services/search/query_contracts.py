import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

PLAN_CACHE_VERSION = 3
PLAN_CACHE_PROVENANCE = "deterministic-explicit"

_LANGUAGE_ALIASES = {
    "english": "en",
    "en": "en",
    "de": "de",
    "deutsch": "de",
    "german": "de",
    "fr": "fr",
    "french": "fr",
    "francais": "fr",
    "français": "fr",
    "it": "it",
    "italian": "it",
    "italiano": "it",
    "es": "es",
    "spanish": "es",
    "espanol": "es",
    "español": "es",
    "pt": "pt",
    "portuguese": "pt",
    "portugues": "pt",
    "português": "pt",
    "pl": "pl",
    "polish": "pl",
    "polski": "pl",
    "ro": "ro",
    "romanian": "ro",
    "romana": "ro",
    "română": "ro",
}

_ROLE_HINTS = {
    "developer",
    "engineer",
    "architect",
    "manager",
    "specialist",
    "consultant",
    "analyst",
    "scientist",
    "administrator",
    "designer",
    "lead",
    "head",
    "director",
    "recruiter",
    "assistant",
    "technician",
    "operator",
    "devops",
    "backend",
    "frontend",
    "fullstack",
    "softwareentwickler",
    "entwickler",
    "ingenieur",
    "berater",
    "chef",
    "cuoco",
    "infermiere",
}

_SKILL_HINTS = {
    "python",
    "java",
    "javascript",
    "typescript",
    "react",
    "angular",
    "vue",
    "docker",
    "kubernetes",
    "aws",
    "azure",
    "gcp",
    "terraform",
    "ansible",
    "sql",
    "linux",
    "c#",
    "c++",
    "node",
    "node.js",
    "golang",
    "go",
    "rust",
    "sap",
    "salesforce",
    "excel",
    "customer service",
    "pulire",
    "trasportare",
}

_QUERY_NOISE_PATTERN = re.compile(
    r"(?<!\w)(m/w/d|f/m/d|m/f/d|\d{1,3}(?:-\d{1,3})?%)(?!\w)", re.IGNORECASE
)
_QUERY_CLEAN_PATTERN = re.compile(r"[^\w\s+#./-]")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_whitespace(value: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", (value or "").strip())


def sanitize_prompt_text(value: Any, *, max_chars: Optional[int] = None) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return text


def normalize_domain(value: Any) -> str:
    text = normalize_whitespace(str(value or "general").lower())
    text = text.replace("/", "-").replace("_", "-")
    text = re.sub(r"[^a-z0-9- ]", "", text)
    text = text.replace(" ", "-")
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "general"


def normalize_language(value: Any) -> str:
    text = normalize_whitespace(str(value or "en").lower())
    return _LANGUAGE_ALIASES.get(text, text[:2] or "en")


def canonicalize_query_text(query: Any) -> str:
    text = normalize_whitespace(str(query or ""))
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("`", "'")
    text = _QUERY_NOISE_PATTERN.sub(" ", text)
    text = _QUERY_CLEAN_PATTERN.sub(" ", text)
    text = normalize_whitespace(text)
    return text


def _coerce_optional_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None
    return None


def infer_search_type(query: Any) -> str:
    normalized = canonicalize_query_text(query).lower()
    if not normalized:
        return "keyword"

    if normalized in _SKILL_HINTS:
        return "keyword"

    tokens = [token for token in re.split(r"[\s./-]+", normalized) if token]
    joined = " ".join(tokens)
    if joined in _SKILL_HINTS:
        return "keyword"
    if any(token in _ROLE_HINTS for token in tokens):
        return "occupation"
    if any(token in _SKILL_HINTS for token in tokens):
        return "keyword"
    if len(tokens) >= 2:
        return "occupation"
    return "keyword"


def normalize_search_type(value: Any, query: Any = "") -> str:
    text = normalize_whitespace(str(value or "").lower())
    if text in {"occupation", "keyword"}:
        return text
    return infer_search_type(query)


def normalize_search_item(search: Any) -> Tuple[Optional[Dict[str, str]], str]:
    if not isinstance(search, dict):
        return None, "non_dict"

    query = canonicalize_query_text(search.get("query", ""))
    if not query:
        return None, "empty_query"

    normalized = {
        "query": query,
        "type": normalize_search_type(search.get("type"), query),
        "domain": normalize_domain(search.get("domain", "general")),
        "language": normalize_language(search.get("language", "en")),
    }
    return normalized, "ok"


def exact_query_fingerprint(search: Any) -> str:
    if isinstance(search, dict):
        normalized, _ = normalize_search_item(search)
        if not normalized:
            return ""
        return "|".join(
            [
                normalized.get("type", ""),
                normalized.get("language", ""),
                normalized.get("domain", ""),
                normalized.get("query", "").lower(),
            ]
        )

    query = canonicalize_query_text(search).lower()
    return query


def loose_query_fingerprint(search: Any) -> str:
    if isinstance(search, dict):
        normalized, _ = normalize_search_item(search)
        if not normalized:
            return ""
        query = normalized["query"].lower()
        prefix = "|".join([normalized["type"], normalized["language"], normalized["domain"]])
    else:
        query = canonicalize_query_text(search).lower()
        prefix = ""

    query = " ".join(
        sorted(token for token in re.split(r"[\s./-]+", query) if token)
    )
    return f"{prefix}|{query}".strip("|")


def compute_plan_input_fingerprint(
    profile: Dict[str, Any],
    *,
    max_queries: Optional[int],
    max_occupation_queries: Optional[int],
    max_keyword_queries: Optional[int],
) -> str:
    """Fingerprint only user-confirmed inputs that may shape provider queries.

    CV text and model-produced normalization deliberately do not participate in
    this contract.  A cache entry created from either source must never become a
    provider-facing query plan.
    """

    advanced_preferences = profile.get("advanced_preferences")
    if not isinstance(advanced_preferences, dict):
        advanced_preferences = {}
    preferred_domains = profile.get("preferred_domains")
    if preferred_domains is None:
        preferred_domains = advanced_preferences.get("preferred_domains")
    payload = {
        "role_description": sanitize_prompt_text(
            profile.get("role_description", ""), max_chars=4000
        ),
        "search_strategy": sanitize_prompt_text(profile.get("search_strategy", ""), max_chars=4000),
        "preferred_domains": sorted(
            normalize_domain(value)
            for value in preferred_domains or []
            if isinstance(value, str) and value.strip()
        ),
        "max_queries": _coerce_optional_int(max_queries),
        "max_occupation_queries": _coerce_optional_int(max_occupation_queries),
        "max_keyword_queries": _coerce_optional_int(max_keyword_queries),
    }
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_plan_cache_payload(
    searches: List[Dict[str, Any]],
    *,
    input_fingerprint: str,
    stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "version": PLAN_CACHE_VERSION,
        "provenance": PLAN_CACHE_PROVENANCE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_fingerprint": input_fingerprint,
        "stats": stats or {},
        "searches": searches,
    }


def unpack_plan_cache_payload(cached_queries: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    payload = cached_queries
    if isinstance(payload, str):
        payload = json.loads(payload)

    if isinstance(payload, list):
        return payload, {
            "version": 1,
            "provenance": None,
            "input_fingerprint": None,
            "stats": {},
        }

    if isinstance(payload, dict):
        searches = payload.get("searches", [])
        if isinstance(searches, list):
            meta = {
                "version": payload.get("version", 1),
                "provenance": payload.get("provenance"),
                "input_fingerprint": payload.get("input_fingerprint"),
                "generated_at": payload.get("generated_at"),
                "stats": payload.get("stats", {}),
            }
            return searches, meta

    return [], {
        "version": 0,
        "provenance": None,
        "input_fingerprint": None,
        "stats": {},
    }


def is_cached_plan_compatible(cache_meta: Dict[str, Any], input_fingerprint: str) -> bool:
    return (
        cache_meta.get("version") == PLAN_CACHE_VERSION
        and cache_meta.get("provenance") == PLAN_CACHE_PROVENANCE
        and cache_meta.get("input_fingerprint") == input_fingerprint
    )


def route_provider_names(
    search: Dict[str, Any],
    providers: Dict[str, Any],
    provider_infos: Dict[str, Any],
) -> List[str]:
    domain = normalize_domain(search.get("domain", "general"))
    query_type = normalize_search_type(search.get("type"), search.get("query", ""))

    compatible: List[str] = []
    for name, provider in providers.items():
        if not provider:
            continue
        info = provider_infos.get(name)
        accepted_domains = getattr(info, "accepted_domains", None)
        if accepted_domains is None and isinstance(info, dict):
            accepted_domains = info.get("accepted_domains")
        accepted_domains = accepted_domains or ["*"]
        if "*" in accepted_domains or domain in accepted_domains:
            compatible.append(name)

    def priority(name: str) -> tuple[int, str]:
        base = {
            "swissdevjobs": 10,
            "job_room": 20,
            "adecco": 30,
            "local_db": 40,
        }.get(name, 50)

        if domain == "it" and name == "swissdevjobs":
            base -= 5
        if query_type == "occupation" and name == "job_room":
            base -= 3
        if domain != "it" and name == "swissdevjobs":
            base += 20
        return base, name

    return sorted(compatible, key=priority)


def supported_request_language(search_language: Any, provider: Any) -> str:
    normalized = normalize_language(search_language)
    capabilities = getattr(provider, "capabilities", None)
    supported_languages: Iterable[str] = getattr(capabilities, "supported_languages", []) or []
    supported_languages = [normalize_language(item) for item in supported_languages]
    if normalized in supported_languages:
        return normalized
    if supported_languages:
        return next(iter(supported_languages))
    return normalized
