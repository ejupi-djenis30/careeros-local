"""
SwissDevJobs API Client.

Client for swissdevjobs.ch fetching via the jobsLight API and retrieving details via jobWithUrl.
"""

import asyncio
import logging
import time
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.providers.jobs.base import JobProvider as BaseJobProvider
from backend.providers.jobs.exceptions import (
    ProviderError,
    ResponseParseError,
)
from backend.providers.jobs.models import (
    JobSearchRequest,
    JobSearchResponse,
    ProviderCapabilities,
    ProviderHealth,
    ProviderStatus,
)

# Import extracted logic
from backend.providers.jobs.swissdevjobs.filters import filter_jobs
from backend.providers.jobs.swissdevjobs.transformer import transform_job_data

logger = logging.getLogger(__name__)

API_BASE_URL = "https://swissdevjobs.ch/api"

class SwissDevJobsProvider(BaseJobProvider):
    """
    SwissDevJobs HTML/API Provider.

    Usage:
        provider = SwissDevJobsProvider()
        response = await provider.search(JobSearchRequest(
            query="React",
            location="Zürich",
        ))
    """

    def __init__(self, include_raw_data: bool = False):
        self._include_raw_data = include_raw_data
        self._client: httpx.AsyncClient | None = None
        self._light_jobs_cache: Any = None
        self._cache_time: float = 0
        self._cache_lock: asyncio.Lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "swissdevjobs"

    @property
    def display_name(self) -> str:
        return "SwissDevJobs.ch"

    def get_provider_info(self) -> "ProviderInfo":  # noqa: F821
        from backend.providers.jobs.models import ProviderInfo
        return ProviderInfo(
            name=self.name,
            description="Exclusive job board for Software Engineers and IT professionals in Switzerland. Do NOT use this for non-IT jobs (e.g. HR, marketing, medical).",
            domain="swissdevjobs.ch",
            accepted_domains=["it"],
        )

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_radius_search=True,
            supports_canton_filter=False,
            supports_profession_codes=False,
            supports_language_skills=False,
            supports_company_filter=True,
            supports_work_forms=True,
            max_page_size=50,
            supported_languages=["en", "de"],
            supported_sort_orders=["date_desc"],
        )

    async def __aenter__(self) -> "SwissDevJobsProvider":
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search(self, request: JobSearchRequest) -> JobSearchResponse:
        """Search for jobs on swissdevjobs.ch."""
        start_time = time.time()

        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

        try:
            # Step 1: Fetch the bulk list (with simple 1-hour cache across the session)
            async with self._cache_lock:
                if self._light_jobs_cache is None or time.time() - self._cache_time > 3600:
                    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
                    async def fetch_light_jobs():
                        resp = await self._client.get(f"{API_BASE_URL}/jobsLight")
                        resp.raise_for_status()
                        return resp.json()

                    self._light_jobs_cache = await fetch_light_jobs()
                    self._cache_time = time.time()

                all_jobs_light = self._light_jobs_cache
            if not isinstance(all_jobs_light, list):
                 raise ResponseParseError(self.name, "Expected a list from jobsLight API")

            # Step 2: Use extracted filters to process jobs
            filtered_jobs = filter_jobs(all_jobs_light, request)

            # Step 3: Pagination
            page = request.page
            page_size = request.page_size
            total_count = len(filtered_jobs)
            start_idx = page * page_size
            end_idx = start_idx + page_size

            page_items = filtered_jobs[start_idx:end_idx]

            # Step 4: Fetch details for the paginated items and transform (Parallelized with sem)
            hydrated_jobs = []
            sem = asyncio.Semaphore(5) # Concurrent fetching limit

            @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
            async def fetch_job_details_with_retry(job_url_slug):
                detail_res = await self._client.get(f"{API_BASE_URL}/jobWithUrl/{job_url_slug}")
                detail_res.raise_for_status()
                detail_data = detail_res.json()
                if isinstance(detail_data, list) and len(detail_data) > 0:
                    detail_data = detail_data[0]
                return detail_data

            async def fetch_job_details(light_job):
                 job_url_slug = light_job.get("jobUrl")
                 if not job_url_slug:
                     return None

                 async with sem:
                     try:
                         detail_data = await fetch_job_details_with_retry(job_url_slug)
                         job_listing = transform_job_data(
                             detail_data,
                             light_job,
                             self.name,
                             self._include_raw_data
                         )
                         return job_listing
                     except Exception as e:
                         logger.warning(f"Failed to fetch details for {job_url_slug} on {self.name} after retries: {e}")
                 return None

            tasks = [fetch_job_details(job) for job in page_items]
            results = await asyncio.gather(*tasks)

            for job_listing in results:
                if job_listing:
                    hydrated_jobs.append(job_listing)

            elapsed_ms = int((time.time() - start_time) * 1000)

            return JobSearchResponse(
                items=hydrated_jobs,
                total_count=total_count,
                page=page,
                page_size=page_size,
                total_pages=(total_count + page_size - 1) // page_size if page_size > 0 else 1,
                source=self.name,
                search_time_ms=elapsed_ms,
                request=request,
            )

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise ProviderError(self.name, f"Search failed: {e}") from e

    async def health_check(self) -> ProviderHealth:
        """Check if swissdevjobs.ch API is accessible."""
        start_time = time.time()
        should_close = False

        if not self._client:
            self._client = httpx.AsyncClient(timeout=10.0)
            should_close = True

        try:
            response = await self._client.get(f"{API_BASE_URL}/jobsLight")
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                return ProviderHealth(
                    provider=self.name,
                    status=ProviderStatus.HEALTHY,
                    latency_ms=latency_ms,
                    message="API accessible",
                )
            else:
                return ProviderHealth(
                    provider=self.name,
                    status=ProviderStatus.DEGRADED,
                    latency_ms=latency_ms,
                    message=f"HTTP {response.status_code}",
                )
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return ProviderHealth(
                provider=self.name,
                status=ProviderStatus.UNAVAILABLE,
                latency_ms=latency_ms,
                message=str(e),
            )
        finally:
            if should_close:
                await self.close()
