"""
Query string builder and in-memory filters for Adecco API.
"""
from typing import List
from backend.providers.jobs.models import JobSearchRequest, SortOrder, ContractType, JobListing

def build_query_string(request: JobSearchRequest) -> str:
    """
    Constructs the `queryString` field for the Adecco POST payload.
    Example: "&location:Zurich, Switzerland&q=Software Engineer&sort=score desc"
    
    Includes only parameters supported by Adecco's Solr query string.
    Note: contractType and workType are NOT supported in queryString for this API.
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

    # Sort
    if request.sort == SortOrder.DATE_DESC:
        parts.append("&sort=date desc")
    elif request.sort == SortOrder.DATE_ASC:
        parts.append("&sort=date asc")
    elif request.sort == SortOrder.RELEVANCE:
        parts.append("&sort=score desc")
    else:
        parts.append("&sort=date desc")

    return "".join(parts)

def filter_jobs(jobs: List[JobListing], request: JobSearchRequest) -> List[JobListing]:
    """
    Apply in-memory filters for fields not supported by Adecco server-side.
    """
    filtered = []
    
    # Pre-calculate filter values
    req_contract = request.contract_type
    req_workforms = [wf.value if hasattr(wf, 'value') else str(wf) for wf in request.work_forms]
    has_remote_filter = "home_office" in req_workforms or "remote" in req_workforms
    
    for job in jobs:
        emp = job.employment
        if not emp:
            filtered.append(job)
            continue
            
        # 1. Contract Type Filter
        # Adecco transform sets is_permanent = (contractTypeId == "PERM")
        if req_contract == ContractType.PERMANENT and not emp.is_permanent:
            continue
        if req_contract == ContractType.TEMPORARY and emp.is_permanent:
            continue
            
        # 2. Workload Filter
        if request.workload_min > 0:
            # If job max is less than our min, exclude
            if emp.workload_max < request.workload_min:
                continue
        if request.workload_max < 100:
            # If job min is more than our max, exclude
            if emp.workload_min > request.workload_max:
                continue
                
        # 3. Work Forms Filter (Remote)
        if has_remote_filter:
            # Check if job is remote (Adecco transform checks light_job.get("isRemote"))
            is_remote = "remote" in emp.work_forms
            if not is_remote:
                continue
                
        filtered.append(job)
        
    return filtered
