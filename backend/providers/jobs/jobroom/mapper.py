"""
BFS Location Mapper for Swiss municipalities.

Maps city names and postal codes to Swiss Federal Statistical Office (BFS)
communal codes (Gemeindenummern) required by the job-room.ch API.
"""

import json
import logging
from pathlib import Path
from typing import Any, NamedTuple

from backend.providers.jobs.exceptions import LocationNotFoundError

logger = logging.getLogger(__name__)


class LocationInfo(NamedTuple):
    """Information about a Swiss location."""

    bfs_code: str
    city: str
    canton: str
    postal_codes: list[str]


# =============================================================================
# Built-in BFS Code Mapping
# =============================================================================

# Major Swiss cities and their BFS communal codes
MAJOR_CITIES_BFS = {
    # Zürich Canton (ZH)
    "zurich": ["261"],
    "zürich": ["261"],
    "winterthur": ["230"],
    "uster": ["198"],
    "dübendorf": ["191"],
    "dietikon": ["243"],
    "wetzikon": ["121"],
    "kloten": ["62"],
    "bülach": ["53"],
    "horgen": ["295"],
    "wallisellen": ["69"],
    "adliswil": ["241"],
    "regensdorf": ["96"],
    "opfikon": ["66"],
    "schlieren": ["247"],
    "thalwil": ["241"],
    # Bern Canton (BE)
    "bern": ["351"],
    "biel": ["371"],
    "bienne": ["371"],
    "thun": ["942"],
    "köniz": ["355"],
    "burgdorf": ["404"],
    "langenthal": ["329"],
    "ittigen": ["362"],
    "ostermundigen": ["363"],
    "muri bei bern": ["360"],
    "spiez": ["561"],
    "interlaken": ["581"],
    # Geneva Canton (GE)
    "geneva": ["6621"],
    "genève": ["6621"],
    "genf": ["6621"],
    "vernier": ["6643"],
    "lancy": ["6628"],
    "meyrin": ["6630"],
    "carouge": ["6608"],
    "onex": ["6633"],
    "thônex": ["6639"],
    "chêne-bougeries": ["6612"],
    # Basel Canton (BS/BL)
    "basel": ["2701"],
    "riehen": ["2703"],
    "allschwil": ["2761"],
    "reinach": ["2770"],
    "muttenz": ["2769"],
    "pratteln": ["2831"],
    "liestal": ["2829"],
    "binningen": ["2762"],
    # Vaud Canton (VD)
    "lausanne": ["5586"],
    "yverdon": ["5938"],
    "yverdon-les-bains": ["5938"],
    "montreux": ["5886"],
    "renens": ["5591"],
    "nyon": ["5724"],
    "vevey": ["5890"],
    "pully": ["5590"],
    "morges": ["5642"],
    # Lucerne Canton (LU)
    "lucerne": ["1061"],
    "luzern": ["1061"],
    "emmen": ["1024"],
    "kriens": ["1059"],
    "horw": ["1058"],
    "ebikon": ["1054"],
    "sursee": ["1103"],
    # St. Gallen Canton (SG)
    "st. gallen": ["3203"],
    "st gallen": ["3203"],
    "sankt gallen": ["3203"],
    "rapperswil-jona": ["3340"],
    "wil": ["3425"],
    "gossau": ["3443"],
    "herisau": ["3001"],
    # Aargau Canton (AG)
    "aarau": ["4001"],
    "baden": ["4021"],
    "wettingen": ["4045"],
    "zofingen": ["4289"],
    "brugg": ["4095"],
    "lenzburg": ["4201"],
    # Ticino Canton (TI)
    "lugano": ["5192"],
    "bellinzona": ["5002"],
    "locarno": ["5113"],
    "mendrisio": ["5254"],
    "chiasso": ["5250"],
    # Zug Canton (ZG)
    "zug": ["1711"],
    "baar": ["1701"],
    "cham": ["1702"],
    "steinhausen": ["1709"],
    # Fribourg Canton (FR)
    "fribourg": ["2196"],
    "freiburg": ["2196"],
    "bulle": ["2125"],
    "villars-sur-glâne": ["2206"],
    # Solothurn Canton (SO)
    "solothurn": ["2601"],
    "olten": ["2581"],
    "grenchen": ["2546"],
    # Thurgau Canton (TG)
    "frauenfeld": ["4566"],
    "kreuzlingen": ["4671"],
    "arbon": ["4416"],
    "amriswil": ["4461"],
    # Schaffhausen Canton (SH)
    "schaffhausen": ["2939"],
    "neuhausen am rheinfall": ["2937"],
    # Valais Canton (VS)
    "sion": ["6266"],
    "sitten": ["6266"],
    "martigny": ["6136"],
    "monthey": ["6153"],
    "brig-glis": ["6002"],
    "visp": ["6297"],
    # Neuchâtel Canton (NE)
    "neuchâtel": ["6458"],
    "la chaux-de-fonds": ["6421"],
    "le locle": ["6436"],
    # Graubünden Canton (GR)
    "chur": ["3901"],
    "davos": ["3851"],
    "st. moritz": ["3787"],
    # Jura Canton (JU)
    "delémont": ["6711"],
    "porrentruy": ["6803"],
    # Schwyz Canton (SZ)
    "schwyz": ["1372"],
    "freienbach": ["1332"],
    "einsiedeln": ["1331"],
    # Uri Canton (UR)
    "altdorf": ["1201"],
    # Obwalden Canton (OW)
    "sarnen": ["1407"],
    # Nidwalden Canton (NW)
    "stans": ["1509"],
    # Glarus Canton (GL)
    "glarus": ["1632"],
    # Appenzell (AI/AR)
    "appenzell": ["3101"],
    # Liechtenstein (for border workers)
    "vaduz": ["7001"],
}


# Postal code to BFS code mapping (common postal codes)
POSTAL_CODE_BFS = {
    # Zürich
    "8000": ["261"],
    "8001": ["261"],
    "8002": ["261"],
    "8003": ["261"],
    "8004": ["261"],
    "8005": ["261"],
    "8006": ["261"],
    "8008": ["261"],
    "8032": ["261"],
    "8037": ["261"],
    "8038": ["261"],
    "8041": ["261"],
    "8044": ["261"],
    "8045": ["261"],
    "8046": ["261"],
    "8047": ["261"],
    "8048": ["261"],
    "8049": ["261"],
    "8050": ["261"],
    "8051": ["261"],
    "8052": ["261"],
    "8053": ["261"],
    "8055": ["261"],
    "8057": ["261"],
    # Bern
    "3000": ["351"],
    "3001": ["351"],
    "3004": ["351"],
    "3005": ["351"],
    "3006": ["351"],
    "3007": ["351"],
    "3008": ["351"],
    "3010": ["351"],
    "3011": ["351"],
    "3012": ["351"],
    "3013": ["351"],
    "3014": ["351"],
    "3015": ["351"],
    # Geneva
    "1200": ["6621"],
    "1201": ["6621"],
    "1202": ["6621"],
    "1203": ["6621"],
    "1204": ["6621"],
    "1205": ["6621"],
    "1206": ["6621"],
    "1207": ["6621"],
    "1208": ["6621"],
    "1209": ["6621"],
    "1211": ["6621"],
    # Basel
    "4000": ["2701"],
    "4001": ["2701"],
    "4051": ["2701"],
    "4052": ["2701"],
    "4053": ["2701"],
    "4054": ["2701"],
    "4055": ["2701"],
    "4056": ["2701"],
    "4057": ["2701"],
    "4058": ["2701"],
    # Lausanne
    "1000": ["5586"],
    "1003": ["5586"],
    "1004": ["5586"],
    "1005": ["5586"],
    "1006": ["5586"],
    "1007": ["5586"],
    "1010": ["5586"],
    "1012": ["5586"],
    "1015": ["5586"],
    "1018": ["5586"],
    # Lucerne
    "6000": ["1061"],
    "6002": ["1061"],
    "6003": ["1061"],
    "6004": ["1061"],
    "6005": ["1061"],
    "6006": ["1061"],
    # St. Gallen
    "9000": ["3203"],
    "9001": ["3203"],
    "9004": ["3203"],
    "9006": ["3203"],
    "9007": ["3203"],
    "9008": ["3203"],
    "9010": ["3203"],
    "9011": ["3203"],
    "9012": ["3203"],
    "9014": ["3203"],
    # Lugano
    "6900": ["5192"],
    "6901": ["5192"],
    "6902": ["5192"],
    "6903": ["5192"],
    "6904": ["5192"],
    "6906": ["5192"],
    # Winterthur
    "8400": ["230"],
    "8401": ["230"],
    "8402": ["230"],
    "8404": ["230"],
    "8405": ["230"],
    "8406": ["230"],
    "8408": ["230"],
    "8409": ["230"],
    "8411": ["230"],
}


class BFSLocationMapper:
    """
    Maps Swiss locations to BFS communal codes.

    Supports city names (multilingual), postal codes, and external data files.

    Usage:
        mapper = BFSLocationMapper()
        codes = mapper.resolve("Zürich")  # Returns ["261"]
        codes = mapper.resolve("8000")    # Returns ["261"]
    """

    def __init__(self, data_path: Path | None = None):
        self._city_cache: dict[str, list[str]] = {}
        self._postal_cache: dict[str, list[str]] = {}
        self._extended_data: dict[str, Any] | None = None

        self._city_cache.update(MAJOR_CITIES_BFS)
        self._postal_cache.update(POSTAL_CODE_BFS)

        if data_path and data_path.exists():
            self._load_extended_data(data_path)

    def _load_extended_data(self, path: Path) -> None:
        """Load extended BFS data from JSON file."""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            if "cities" in data:
                self._city_cache.update(data["cities"])
            if "postal_codes" in data:
                self._postal_cache.update(data["postal_codes"])

            self._extended_data = data
            logger.info("Loaded extended BFS location data")

        except Exception as exc:
            logger.warning("BFS data load failed exception_type=%s", type(exc).__name__)

    def resolve(self, location: str) -> list[str]:
        """
        Resolve a location string to BFS communal codes.

        Raises:
            LocationNotFoundError: If location cannot be resolved
        """
        if not location:
            return []

        location = location.strip()
        normalized = location.lower()

        # Try as postal code first
        if location.isdigit() and len(location) == 4:
            codes = self._postal_cache.get(location)
            if codes:
                logger.debug("Resolved postal code to BFS code_count=%d", len(codes))
                return codes

        # Try as city name
        codes = self._city_cache.get(normalized)
        if codes:
            logger.debug("Resolved city to BFS code_count=%d", len(codes))
            return codes

        # Try partial match
        for city, bfs_codes in self._city_cache.items():
            if normalized in city or city in normalized:
                logger.debug("Resolved partial city match to BFS code_count=%d", len(bfs_codes))
                return bfs_codes

        logger.warning("Could not resolve requested location")
        raise LocationNotFoundError(location)

    def resolve_safe(self, location: str) -> list[str]:
        """Resolve location without raising exceptions."""
        try:
            return self.resolve(location)
        except LocationNotFoundError:
            return []

    def reverse_lookup(self, bfs_code: str) -> LocationInfo | None:
        """Get location info from BFS code."""
        for city, codes in self._city_cache.items():
            if bfs_code in codes:
                canton = self._guess_canton(bfs_code)
                return LocationInfo(
                    bfs_code=bfs_code,
                    city=city.title(),
                    canton=canton,
                    postal_codes=self._get_postal_codes_for_bfs(bfs_code),
                )
        return None

    def _guess_canton(self, bfs_code: str) -> str:
        """Guess canton from BFS code ranges."""
        code = int(bfs_code)
        if 1 <= code <= 300:
            return "ZH"
        elif 301 <= code <= 1000:
            return "BE"
        elif 1001 <= code <= 1200:
            return "LU"
        elif 1701 <= code <= 1720:
            return "ZG"
        elif 2701 <= code <= 2800:
            return "BS"
        elif 2761 <= code <= 2900:
            return "BL"
        elif 5001 <= code <= 5300:
            return "TI"
        elif 5500 <= code <= 6000:
            return "VD"
        elif 6600 <= code <= 6700:
            return "GE"
        else:
            return "??"

    def _get_postal_codes_for_bfs(self, bfs_code: str) -> list[str]:
        """Get all postal codes associated with a BFS code."""
        return [plz for plz, codes in self._postal_cache.items() if bfs_code in codes]

    def get_all_cities(self) -> list[str]:
        """Get list of all known city names."""
        return list(self._city_cache.keys())

    def get_canton_cities(self, canton_code: str) -> list[str]:
        """Get all cities in a canton."""
        return []
