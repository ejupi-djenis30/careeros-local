import logging
import time

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from backend.core.diagnostics import FailureCode, diagnose_failure, log_failure
from backend.providers.jobs.exceptions import ResponseParseError
from backend.providers.jobs.http_policy import (
    MAX_PROVIDER_RESPONSE_BYTES,
    assert_bounded_provider_response,
    is_retryable_provider_http_error,
    provider_response_hooks,
)

logger = logging.getLogger(__name__)

# Curated list of common Swiss AVAM profession codes
# Keys are AVAM codes (as strings), values are lists of normalized job titles in various languages.
# Note: These are representative codes. JobRoom API expects valid AVAM codes.
# 27114 is often generic IT, 27114004 is software engineer etc.
AVAM_MAPPING: dict[str, list[str]] = {
    # Software Engineering & IT
    "27114004": [
        "software engineer",
        "softwareentwickler",
        "ingénieur logiciel",
        "sviluppatore software",
        "software developer",
        "developer",
        "entwickler",
        "programmeur",
        "software",
        "programmer",
    ],
    "27114014": [
        "devops engineer",
        "devops-ingenieur",
        "devops",
        "site reliability engineer",
        "sre",
    ],
    "27114003": [
        "web developer",
        "webentwickler",
        "développeur web",
        "frontend developer",
        "backend developer",
        "fullstack developer",
        "full stack",
        "web",
    ],
    "27111001": [
        "system administrator",
        "systemadministrator",
        "administrateur système",
        "sysadmin",
        "it administrator",
        "system engineer",
        "it support",
    ],
    "27115001": [
        "data scientist",
        "data engineer",
        "datenwissenschaftler",
        "data analyst",
        "datenanalyst",
    ],
    "27113002": [
        "it project manager",
        "it projektleiter",
        "chef de projet it",
        "scrum master",
        "agile coach",
        "project manager",
    ],
    "27113003": [
        "it consultant",
        "it berater",
        "consultant en informatique",
        "business analyst",
        "consultant",
    ],
    "27114016": [
        "security engineer",
        "it security",
        "cyber security",
        "sicherheitsexperte",
        "security",
    ],
    "27114013": [
        "cloud engineer",
        "cloud architect",
        "aws engineer",
        "azure engineer",
        "cloud computing",
    ],
    # Finance & Management
    "33100": ["financial analyst", "finanzanalyst", "analyste financier", "finance"],
    "33101": ["accountant", "buchhalter", "comptable", "controller", "controlling"],
    "34101": ["sales manager", "sales", "verkauf", "account manager", "key account manager"],
    "41103": [
        "hr manager",
        "human resources",
        "personalverantwortlicher",
        "recruiter",
        "talent acquisition",
    ],
    "61002": ["marketing manager", "marketing", "digital marketing"],
    # Retail & Sales
    "52202": ["cashier", "kassierer", "caissier", "cassiere", "kasse"],
    "52201": [
        "shop assistant",
        "sales assistant",
        "verkäufer",
        "detailhandelsfachmann",
        "vendeur",
        "commesso",
        "retail",
    ],
    "52203": ["store manager", "filialleiter", "gérant de magasin", "direttore di negozio"],
    # Hospitality & Gastronomy
    "51202": [
        "waiter",
        "waitress",
        "kellner",
        "servicemitarbeiter",
        "serveur",
        "cameriere",
        "service",
    ],
    "51201": ["chef", "cook", "koch", "cuisinier", "cuoco", "küchenhilfe", "commis de cuisine"],
    "51101": ["receptionist", "rezeptionist", "réceptionniste", "reception"],
    "51301": ["bartender", "barkeeper", "barista", "barman"],
    # Construction & Manual Labor
    "71101": ["bricklayer", "mason", "maurer", "maçon", "muratore"],
    "71201": ["carpenter", "zimmermann", "schreiner", "charpentier", "falegname"],
    "71301": ["electrician", "elektriker", "électricien", "elettricista"],
    "71401": ["painter", "maler", "peintre", "pittore"],
    "71302": ["plumber", "sanitärinstallateur", "plombier", "idraulico"],
    "93101": [
        "unskilled worker",
        "laborer",
        "hilfsarbeiter",
        "bauarbeiter",
        "manoeuvre",
        "operaio edile",
        "construction worker",
    ],
    # Logistics & Transport
    "83201": [
        "warehouse worker",
        "lagerist",
        "logistiker",
        "magasinier",
        "magazziniere",
        "warehouse",
    ],
    "83301": [
        "driver",
        "chauffeur",
        "fahrer",
        "conducteur",
        "autista",
        "delivery driver",
        "kurier",
    ],
    "83302": ["forklift driver", "staplerfahrer", "cariste", "carrellista"],
    # Cleaning & Facility Management
    "91102": [
        "cleaner",
        "reinigungspersonal",
        "reinigungsmitarbeiter",
        "nettoyeur",
        "femme de ménage",
        "addetto alle pulizie",
        "cleaning",
    ],
    "91101": ["janitor", "hauswart", "concierge", "custode", "facility manager"],
    # Healthcare & Nursing
    "32201": [
        "nurse",
        "pflegefachfrau",
        "pflegefachkrankenschwester",
        "infirmière",
        "infermiere",
        "registered nurse",
    ],
    "53201": [
        "care assistant",
        "pflegehelfer",
        "aide-soignant",
        "operatore socio-sanitario",
        "caregiver",
    ],
    "32101": [
        "medical assistant",
        "medizinischer praxisassistent",
        "mpa",
        "assistante médicale",
        "assistente medico",
    ],
    # Manufacturing & Production
    "81001": [
        "production worker",
        "produktionsmitarbeiter",
        "ouvrier de production",
        "operaio di produzione",
        "factory worker",
        "assembler",
    ],
    "81002": [
        "machine operator",
        "maschinenführer",
        "opérateur de machine",
        "operatore di macchina",
    ],
    "72101": ["mechanic", "mechaniker", "mechanicien", "meccanico"],
    # Administration & Clerical
    "41101": [
        "clerk",
        "administrative assistant",
        "kaufmännischer angestellter",
        "employé de commerce",
        "impiegato di commercio",
        "admin assistant",
    ],
    "41201": ["secretary", "sekretär", "secrétaire", "segretario"],
    "42201": [
        "customer service",
        "kundendienst",
        "service client",
        "servizio clienti",
        "call center",
    ],
}


class AVAMProfessionMapper:
    """
    Maps textual occupation titles (as generated by the LLM planner)
    into Swiss AVAM profession codes for the JobRoom API.
    Uses a hybrid approach: static dictionary (L1) -> JobRoom API live lookup (L2).
    """

    _API_URL = "https://www.job-room.ch/job-board-api/public/occupations"
    _MAX_RESPONSE_BYTES = MAX_PROVIDER_RESPONSE_BYTES
    _MAX_RESULTS = 10_000

    def __init__(self) -> None:
        self._static_cache = AVAM_MAPPING
        self._api_cache: dict[str, tuple[tuple[str, ...], float]] = {}
        # TTL of 24h (86400 seconds)
        self._ttl_seconds = 86400
        # Max entries in the live-API cache before LRU eviction
        self._api_cache_max_size = 2048

    @retry(
        retry=retry_if_exception(is_retryable_provider_http_error),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=1),
        reraise=True,
    )
    async def _fetch_from_api(self, title: str) -> list[str]:
        """Live lookup directly against federal database API."""
        async with httpx.AsyncClient(
            timeout=2.0,
            headers={"Accept-Encoding": "identity"},
            follow_redirects=False,
            trust_env=False,
            event_hooks=provider_response_hooks(
                "job_room_avam",
                max_bytes=self._MAX_RESPONSE_BYTES,
            ),
        ) as client:
            response = await client.get(
                self._API_URL,
                params={"prefix": title, "language": "en"},
            )
            assert_bounded_provider_response(
                response,
                "job_room_avam",
                max_bytes=self._MAX_RESPONSE_BYTES,
            )
            response.raise_for_status()
            results = response.json()

        if not isinstance(results, list) or len(results) > self._MAX_RESULTS:
            raise ResponseParseError("job_room_avam", "Unexpected AVAM response format")
        codes: set[str] = set()
        for occ in results:
            if isinstance(occ, dict) and occ.get("type") == "AVAM" and occ.get("code"):
                codes.add(str(occ.get("code")))

        return sorted(codes)

    async def resolve(self, title: str) -> list[str]:
        """
        Takes a job title/occupation string and returns a list of matching AVAM codes.
        Checks static dictionary first, falls back to API, and caches the result.
        """
        normalized = title.casefold().strip()
        if not normalized:
            return []

        # 1. Check L1 Static Cache
        matches = set()
        for code, aliases in self._static_cache.items():
            for alias in aliases:
                # Basic token intersection or substring matching
                if alias in normalized or normalized in alias:
                    matches.add(code)

        result = sorted(matches)
        if result:
            logger.debug("Mapped occupation using static AVAM cache code_count=%d", len(result))
            return result

        # 2. Check L2 TTL API Cache
        cached_entry = self._api_cache.pop(normalized, None)
        if cached_entry is not None:
            cache_codes, timestamp = cached_entry
            if time.monotonic() - timestamp < self._ttl_seconds:
                self._api_cache[normalized] = cached_entry
                logger.debug(
                    "Mapped occupation using dynamic AVAM cache code_count=%d", len(cache_codes)
                )
                return list(cache_codes)

        # 3. L3 Live API Fallback
        try:
            api_codes = await self._fetch_from_api(title)
            if api_codes:
                logger.info("Mapped occupation using AVAM API code_count=%d", len(api_codes))
            else:
                logger.debug("AVAM API returned no occupation mapping")
            # Cache results (including empty dead-ends) and remove expired entries
            # before evicting the least recently used live entry.
            now = time.monotonic()
            expired = [
                key
                for key, (_, cached_at) in self._api_cache.items()
                if now - cached_at >= self._ttl_seconds
            ]
            for key in expired:
                self._api_cache.pop(key, None)
            self._api_cache.pop(normalized, None)
            while len(self._api_cache) >= self._api_cache_max_size:
                self._api_cache.pop(next(iter(self._api_cache)))
            self._api_cache[normalized] = (tuple(api_codes), now)
            if api_codes:
                return list(api_codes)
        except Exception as exc:
            diagnostic = diagnose_failure(exc, FailureCode.PROVIDER_REQUEST_FAILED)
            log_failure(logger, diagnostic, level=logging.WARNING)

        return []


avam_mapper = AVAMProfessionMapper()
