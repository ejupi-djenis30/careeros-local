import logging
from backend.providers.jobs.models import JobSearchRequest, SortOrder, RadiusSearchRequest, Coordinates, ContractType

logger = logging.getLogger(__name__)

def build_search_request(profile, query: str, profession_codes: list[str] = None) -> JobSearchRequest:
    """Create a JobSearchRequest from profile settings and a keyword query."""
    workload_min, workload_max = 0, 100
    if profile.workload_filter:
        parts = profile.workload_filter.replace("%", "").split("-")
        try:
            workload_min = int(parts[0])
            workload_max = int(parts[1]) if len(parts) > 1 else int(parts[0])
        except ValueError:
            pass

    radius_request = None
    if profile.latitude and profile.longitude:
        # Default to 50km if not specified, or use profile preference if available
        dist = 50 
        if hasattr(profile, 'max_distance') and profile.max_distance:
             dist = int(profile.max_distance)
        
        radius_request = RadiusSearchRequest(
            geo_point=Coordinates(lat=profile.latitude, lon=profile.longitude),
            distance=dist
        )

    contract_type_mapping = {
        "permanent": ContractType.PERMANENT,
        "temporary": ContractType.TEMPORARY,
        "any": ContractType.ANY
    }
    
    contract_val = getattr(profile, "contract_type", "any")
    if not contract_val:
        contract_val = "any"
        
    c_type = contract_type_mapping.get(contract_val.lower(), ContractType.ANY)

    return JobSearchRequest(
        query=query,
        location=profile.location_filter or "",
        posted_within_days=profile.posted_within_days or 30,
        workload_min=workload_min,
        workload_max=workload_max,
        contract_type=c_type,
        page_size=50,
        sort=SortOrder.DATE_DESC,
        radius_search=radius_request,
        communal_codes=[], # Clear communal codes if using radius to avoid conflict? usually they can coexist or radius overrides.
        profession_codes=profession_codes or []
    )
