import logging
import time
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.providers.jobs.base import JobProvider
from backend.providers.jobs.models import (
    JobSearchRequest,
    JobSearchResponse,
    JobListing,
    ProviderInfo,
    JobLocation,
    EmploymentDetails
)
from backend.services.utils import haversine_distance
from backend.models import ScrapedJob

logger = logging.getLogger(__name__)

class LocalDbProvider(JobProvider):
    def __init__(self, db: Session):
        self.db = db

    def name(self) -> str:
        return "local_db"

    def get_provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            name="local_db",
            description="Searches the local application database for previously scraped jobs.",
            domain="internal",
            accepted_domains=["local", "db-only"],
        )

    def _db_job_to_listing(self, db_job: ScrapedJob, distance_km: float = None) -> JobListing:
        # Reconstruct EmploymentInfo
        employment = None
        if db_job.workload:
            # Typical format "80-100%" or "100%"
            w_str = db_job.workload.replace("%", "").strip()
            if "-" in w_str:
                parts = w_str.split("-")
                employment = EmploymentDetails(
                    workload_min=int(parts[0]),
                    workload_max=int(parts[1])
                )
            elif w_str.isdigit():
                employment = EmploymentDetails(
                    workload_min=int(w_str),
                    workload_max=int(w_str)
                )

        location = None
        if db_job.location:
            location = JobLocation(city=db_job.location)
            
        return JobListing(
            id=db_job.platform_job_id,
            title=db_job.title,
            company={"name": db_job.company} if db_job.company else None,
            source=db_job.platform,
            location=location,
            employment=employment,
            external_url=db_job.external_url,
            raw_data=db_job.raw_metadata or {},
        )

    async def search(self, request: JobSearchRequest) -> JobSearchResponse:
        logger.info(f"[{self.name()}] Starting search for '{request.query}' in '{request.location}'")
        start_time = time.time()

        # Start building the ORM query
        q = self.db.query(ScrapedJob)
        
        # 1. Keywords filtering (ILIKE)
        if request.query:
            query_terms = request.query.split(" ")
            for term in query_terms:
                term = term.strip()
                if not term:
                    continue
                ilike_term = f"%{term}%"
                q = q.filter(
                    or_(
                        ScrapedJob.title.ilike(ilike_term),
                        ScrapedJob.description.ilike(ilike_term),
                        ScrapedJob.company.ilike(ilike_term)
                    )
                )

        # 2. Location filtering
        if request.location:
            ilike_city = f"%{request.location}%"
            q = q.filter(ScrapedJob.location.ilike(ilike_city))

        # Get total count before pagination
        total_count = q.count()

        # 3. Pagination (Local limit)
        q = q.limit(request.page_size)

        scraped_jobs = q.all()

        results = []
        for db_job in scraped_jobs:
            results.append(self._db_job_to_listing(db_job))

        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.info(f"[{self.name()}] Found {len(results)} internal jobs in {elapsed_ms}ms")
        
        return JobSearchResponse(
            items=results,
            total_count=total_count,
            page=request.page,
            page_size=request.page_size,
            total_pages=max(1, (total_count + request.page_size - 1) // request.page_size),
            source=self.name(),
            search_time_ms=elapsed_ms,
            request=request,
        )
