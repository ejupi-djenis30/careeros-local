import logging
import time
from typing import Dict, List

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Curated list of common Swiss AVAM profession codes
# Keys are AVAM codes (as strings), values are lists of normalized job titles in various languages.
# Note: These are representative codes. JobRoom API expects valid AVAM codes.
# 27114 is often generic IT, 27114004 is software engineer etc.
AVAM_MAPPING: Dict[str, List[str]] = {
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

    def __init__(self):
        self._static_cache = AVAM_MAPPING
        self._api_cache: Dict[str, tuple[List[str], float]] = {}
        # TTL of 24h (86400 seconds)
        self._ttl_seconds = 86400
        # Max entries in the live-API cache before LRU eviction
        self._api_cache_max_size = 2048
        self._client = httpx.AsyncClient(timeout=2.0)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, min=0.5, max=1))
    async def _fetch_from_api(self, title: str) -> List[str]:
        """Live lookup directly against federal database API."""
        url = f"https://www.job-room.ch/job-board-api/public/occupations?prefix={title}&language=en"
        response = await self._client.get(url)
        response.raise_for_status()

        results = response.json()
        codes = set()
        for occ in results:
            if occ.get("type") == "AVAM" and occ.get("code"):
                codes.add(str(occ.get("code")))

        return list(codes)

    async def resolve(self, title: str) -> List[str]:
        """
        Takes a job title/occupation string and returns a list of matching AVAM codes.
        Checks static dictionary first, falls back to API, and caches the result.
        """
        if not title:
            return []

        normalized = title.lower().strip()

        # 1. Check L1 Static Cache
        matches = set()
        for code, aliases in self._static_cache.items():
            for alias in aliases:
                # Basic token intersection or substring matching
                if alias in normalized or normalized in alias:
                    matches.add(code)

        result = list(matches)
        if result:
            logger.debug("Mapped occupation using static AVAM cache code_count=%d", len(result))
            return result

        # 2. Check L2 TTL API Cache
        if normalized in self._api_cache:
            cache_codes, timestamp = self._api_cache[normalized]
            if time.time() - timestamp < self._ttl_seconds:
                logger.debug(
                    "Mapped occupation using dynamic AVAM cache code_count=%d", len(cache_codes)
                )
                return cache_codes

        # 3. L3 Live API Fallback
        try:
            api_codes = await self._fetch_from_api(title)
            if api_codes:
                logger.info("Mapped occupation using AVAM API code_count=%d", len(api_codes))
            else:
                logger.debug("AVAM API returned no occupation mapping")
            # Cache result (including empty) to prevent re-querying dead-ends; evict oldest if at capacity
            if len(self._api_cache) >= self._api_cache_max_size:
                self._api_cache.pop(next(iter(self._api_cache)))
            self._api_cache[normalized] = (api_codes, time.time())
            if api_codes:
                return api_codes
        except Exception as exc:
            logger.warning(
                "AVAM occupation mapping failed exception_type=%s", type(exc).__name__
            )

        return []


avam_mapper = AVAMProfessionMapper()
