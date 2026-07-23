import logging
from typing import Any

from backend.providers.jobs.jobroom.constants import LANGUAGE_PARAMS, SEARCH_ENDPOINT
from backend.providers.jobs.jobroom.mapper import BFSLocationMapper
from backend.providers.jobs.models import ContractType, JobSearchRequest, SortOrder

logger = logging.getLogger(__name__)


def build_search_payload(request: JobSearchRequest, mapper: BFSLocationMapper) -> dict[str, Any]:
    """Build the API request payload with all filters for job-room.ch."""
    communal_codes = list(request.communal_codes)
    if request.location:
        resolved = mapper.resolve_safe(request.location)
        communal_codes.extend(resolved)

    keywords: list[str] = list(request.keywords)
    if request.query:
        keywords.append(request.query)

    permanent: bool | None = None
    if request.contract_type == ContractType.PERMANENT:
        permanent = True
    elif request.contract_type == ContractType.TEMPORARY:
        permanent = False

    radius_search = None
    if request.radius_search:
        radius_search = {
            "geoPoint": {
                "lat": request.radius_search.geo_point.lat,
                "lon": request.radius_search.geo_point.lon,
            },
            "distance": request.radius_search.distance,
        }

    # request.work_forms logic is evaluated but not used in the original
    # We maintain this behavior or improve it if needed.

    language_skills = []
    for ls in request.language_skills:
        skill = {"languageIsoCode": ls.language_code}
        if ls.spoken_level:
            skill["spokenLevel"] = ls.spoken_level.value
        if ls.written_level:
            skill["writtenLevel"] = ls.written_level.value
        language_skills.append(skill)

    payload: dict[str, Any] = {
        "workloadPercentageMin": request.workload_min,
        "workloadPercentageMax": request.workload_max,
        "permanent": permanent,
        "companyName": request.company_name,
        "onlineSince": request.posted_within_days,
        "displayRestricted": request.display_restricted,
        "professionCodes": [{"type": "AVAM", "value": code} for code in request.profession_codes],
        "keywords": keywords if keywords else [],
        "communalCodes": communal_codes if communal_codes else [],
        "cantonCodes": list(request.canton_codes) if request.canton_codes else [],
    }

    if radius_search:
        payload["radiusSearchRequest"] = radius_search

    logger.debug(
        "Built search payload fields=%d keywords=%d communal_codes=%d",
        len(payload),
        len(keywords),
        len(communal_codes),
    )
    return payload


def build_search_url(request: JobSearchRequest) -> str:
    """Build search URL with query parameters."""
    sort_map = {
        SortOrder.DATE_DESC: "date_desc",
        SortOrder.DATE_ASC: "date_asc",
        SortOrder.RELEVANCE: "relevance",
    }
    sort = sort_map.get(request.sort, "date_desc")
    lang_param = LANGUAGE_PARAMS.get(request.language, "ZW4=")

    url = (
        f"{SEARCH_ENDPOINT}"
        f"?page={request.page}"
        f"&size={request.page_size}"
        f"&sort={sort}"
        f"&_ng={lang_param}"
    )

    return url
