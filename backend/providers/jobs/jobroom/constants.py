"""
Constants for Job-Room API integration.

Contains endpoints, headers, and configuration for job-room.ch scraping.
"""

# =============================================================================
# API Endpoints
# =============================================================================

BASE_URL = "https://www.job-room.ch"
API_BASE = "https://www.job-room.ch/jobadservice/api/jobAdvertisements"
SEARCH_ENDPOINT = f"{API_BASE}/_search"

# Language parameter encoding (base64)
LANGUAGE_PARAMS = {
    "en": "ZW4=",
    "de": "ZGU=",
    "fr": "ZnI=",
    "it": "aXQ=",
}

# =============================================================================
# Request Headers (Chrome Simulation)
# =============================================================================

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
}

# =============================================================================
# API Configuration
# =============================================================================

MAX_PAGE_SIZE = 100
DEFAULT_ONLINE_SINCE = 30

CSRF_COOKIE_NAME = "XSRF-TOKEN"
CSRF_HEADER_NAME = "X-XSRF-TOKEN"

# =============================================================================
# Swiss Canton Codes
# =============================================================================

CANTON_CODES = {
    "AG": "Aargau",
    "AI": "Appenzell Innerrhoden",
    "AR": "Appenzell Ausserrhoden",
    "BE": "Bern",
    "BL": "Basel-Landschaft",
    "BS": "Basel-Stadt",
    "FR": "Fribourg",
    "GE": "Geneva",
    "GL": "Glarus",
    "GR": "Graubünden",
    "JU": "Jura",
    "LU": "Lucerne",
    "NE": "Neuchâtel",
    "NW": "Nidwalden",
    "OW": "Obwalden",
    "SG": "St. Gallen",
    "SH": "Schaffhausen",
    "SO": "Solothurn",
    "SZ": "Schwyz",
    "TG": "Thurgau",
    "TI": "Ticino",
    "UR": "Uri",
    "VD": "Vaud",
    "VS": "Valais",
    "ZG": "Zug",
    "ZH": "Zürich",
}
