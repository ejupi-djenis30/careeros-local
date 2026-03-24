import logging
from typing import Any

from backend.providers.jobs.models import JobSearchRequest, ContractType
from backend.services.utils import haversine_distance

logger = logging.getLogger(__name__)

def filter_jobs(all_jobs: list[dict[str, Any]], request: JobSearchRequest) -> list[dict[str, Any]]:
    """
    Applies in-memory filters to a list of job search results from SwissDevJobs.
    """
    filtered_jobs = []
    
    # Extract basic search criteria
    query = request.query.lower() if request.query else ""
    location_query = request.location.lower() if request.location else ""
    
    for job in all_jobs:
        # 1. Filter by keyword (Tokenized Match)
        if query:
            title = job.get("name", "").lower()
            techs = " ".join([t.lower() for t in job.get("technologies", [])])
            tags = " ".join([t.lower() for t in job.get("filterTags", [])])
            combined_text = f"{title} {techs} {tags}"
            
            tokens = query.split()
            match = all(token in combined_text for token in tokens)
            if not match:
                continue
        
        # 2. Filter by location text simply
        if location_query and not request.radius_search:
            city = job.get("actualCity", "").lower()
            cat = job.get("cityCategory", "").lower()
            if location_query not in city and location_query not in cat:
                continue
        
        # 3. Filter by distance if specified
        if request.radius_search:
            lat = job.get("latitude")
            lon = job.get("longitude")
            if lat and lon:
                dist = haversine_distance(
                    request.radius_search.geo_point.lat,
                    request.radius_search.geo_point.lon,
                    float(lat), float(lon)
                )
                if dist > request.radius_search.distance:
                    continue
            else:
                continue # Skip jobs with no location when radius search is active
                
        # 4. Filter by company Name
        if request.company_name:
            company = job.get("company", "").lower()
            if request.company_name.lower() not in company:
                continue
                
        # 5. Filter by Workload
        job_type = job.get("jobType", "").lower()
        if "part-time" in job_type and request.workload_min >= 90:
            continue # Exclude part time if looking for >=90%
        if "full-time" in job_type and request.workload_max <= 80:
            continue # Exclude full time if looking for <=80%
            
        # 6. Filter by Language
        if request.language_skills:
            req_langs = [ls.language_code.lower() for ls in request.language_skills]
            job_lang = job.get("language", "").lower()
            lang_map = {"en": "english", "de": "german", "fr": "french", "it": "italian"}
            allowed_job_langs = [lang_map.get(code, code) for code in req_langs]
            if job_lang and job_lang not in allowed_job_langs:
                continue
                
        # 7. Filter by WorkForm (remote/home_office)
        if request.work_forms:
            wf_values = [wf.value for wf in request.work_forms]
            job_workplace = job.get("workplace", "").lower()
            if "home_office" in wf_values:
                if job_workplace not in ["remote", "hybrid"]:
                    continue

        # 8. Filter by Contract Type
        if request.contract_type != ContractType.ANY:
            # SwissDevJobs exposes temporary vs permanent info mostly in jobType or tags
            tags_lower = [t.lower() for t in job.get("filterTags", [])]
            is_temp = "freelance" in job_type or "freelance" in tags_lower or "temporary" in job_type or "consulting" in job_type or "contractor" in tags_lower
            
            if request.contract_type == ContractType.PERMANENT and is_temp:
                continue
            if request.contract_type == ContractType.TEMPORARY and not is_temp:
                 continue

        filtered_jobs.append(job)

    return filtered_jobs
