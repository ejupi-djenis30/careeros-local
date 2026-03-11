"""
Query string builder for Adecco API.
"""
from backend.providers.jobs.models import JobSearchRequest, SortOrder, ContractType, WorkForm

def build_query_string(request: JobSearchRequest) -> str:
    """
    Constructs the `queryString` field for the Adecco POST payload.
    Example: "&location:Zurich, Switzerland&q=Software Engineer&sort=score desc"
    """
    parts = []

    # Location
    if request.location:
        parts.append(f"&location:{request.location}")
        
    # Radius (Distance)
    if request.radius and request.radius > 0:
        # Adecco uses &d=XX for radius in km
        parts.append(f"&d={request.radius}")

    # Query / Keyword
    if request.query:
        parts.append(f"&q={request.query}")
    else:
        # If no query, we need to supply * to browse all
        # To avoid giant un-filterable lists we might pass empty, but usually Adecco expects something.
        pass

    # Contract Type
    if request.contract_type == ContractType.PERMANENT:
        parts.append("&contractType=PERM")
    elif request.contract_type == ContractType.TEMPORARY:
        parts.append("&contractType=TEMP")

    # Work Forms (Remote)
    if request.work_forms and WorkForm.HOME_OFFICE in request.work_forms:
        parts.append("&workType=remote")

    # Sort
    if request.sort == SortOrder.DATE_DESC:
        parts.append("&sort=date desc")
    elif request.sort == SortOrder.DATE_ASC:
        parts.append("&sort=date asc")
    elif request.sort == SortOrder.RELEVANCE:
        parts.append("&sort=score desc")
    else:
        parts.append("&sort=date desc")

    # The API format expects these directly concatenated in a single string, e.g.
    # &location:Zurich&q=Developer&sort=date desc
    return "".join(parts)
