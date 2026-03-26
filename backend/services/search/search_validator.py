import logging

from backend.providers.jobs.models import (
    ContractType,
    Coordinates,
    JobSearchRequest,
    RadiusSearchRequest,
    SortOrder,
)
from backend.services.search.profile_preferences import get_profile_preference
from backend.services.search.query_contracts import (
    canonicalize_query_text,
    supported_request_language,
)

logger = logging.getLogger(__name__)


def _string_attr(value, default: str = "") -> str:
    if isinstance(value, str):
        return value
    return default


def _optional_int_attr(value, default=None):
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            return default
    return default

def build_search_request(
    profile,
    query: str,
    profession_codes: list[str] | None = None,
    *,
    language: str = "en",
    page_size: int = 50,
    provider=None,
) -> JobSearchRequest:
    """Create a JobSearchRequest from profile settings and a keyword query."""
    workload_min, workload_max = 0, 100
    hard_workload_min = _optional_int_attr(get_profile_preference(profile, "workload_min", None), None)
    hard_workload_max = _optional_int_attr(get_profile_preference(profile, "workload_max", None), None)

    if hard_workload_min is not None or hard_workload_max is not None:
        workload_min = hard_workload_min if hard_workload_min is not None else 0
        workload_max = hard_workload_max if hard_workload_max is not None else 100
    else:
        workload_filter = _string_attr(getattr(profile, "workload_filter", ""), "")
        if workload_filter:
            parts = workload_filter.replace("%", "").split("-")
            try:
                workload_min = int(parts[0])
                workload_max = int(parts[1]) if len(parts) > 1 else int(parts[0])
            except ValueError:
                pass

    radius_request = None
    latitude = getattr(profile, "latitude", None)
    longitude = getattr(profile, "longitude", None)
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        # Default to 50km if not specified, or use profile preference if available
        dist = 50
        hard_max_distance = _optional_int_attr(get_profile_preference(profile, "hard_max_distance_km", None), None)
        max_distance = _optional_int_attr(getattr(profile, "max_distance", None), 50)
        if hard_max_distance is not None:
            max_distance = hard_max_distance
        if max_distance:
             dist = max_distance

        radius_request = RadiusSearchRequest(
            geo_point=Coordinates(lat=latitude, lon=longitude),
            distance=dist
        )

    contract_type_mapping = {
        "permanent": ContractType.PERMANENT,
        "temporary": ContractType.TEMPORARY,
        "any": ContractType.ANY
    }

    contract_val = _string_attr(getattr(profile, "contract_type", "any"), "any")
    if not contract_val:
        contract_val = "any"

    c_type = contract_type_mapping.get(contract_val.lower(), ContractType.ANY)
    normalized_query = canonicalize_query_text(query)
    request_language = supported_request_language(language, provider) if provider else language
    location_filter = _string_attr(getattr(profile, "location_filter", ""), "")
    posted_within_days = _optional_int_attr(getattr(profile, "posted_within_days", None), 30)

    return JobSearchRequest(
        query=normalized_query,
        location=location_filter,
        posted_within_days=posted_within_days,
        workload_min=workload_min,
        workload_max=workload_max,
        contract_type=c_type,
        page_size=page_size,
        sort=SortOrder.DATE_DESC,
        radius_search=radius_request,
        communal_codes=[], # Clear communal codes if using radius to avoid conflict? usually they can coexist or radius overrides.
        profession_codes=profession_codes or [],
        keywords=[normalized_query] if normalized_query else [],
        language=request_language,
    )
