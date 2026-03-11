"""
Adecco API Client.

Client for adecco.com/api/data/jobs fetching summarized jobs and detailed descriptions.
"""

import logging
import time
from typing import Any
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

import httpx

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
from backend.providers.jobs.base import JobProvider as BaseJobProvider

from backend.providers.jobs.adecco.filters import build_query_string
from backend.providers.jobs.adecco.transformer import transform_job_data

logger = logging.getLogger(__name__)

API_BASE_URL = "https://www.adecco.com/api/data/jobs"

# Adecco's Solr API expects these specific GUIDs to filter the response aggregations.
# If omitted or incorrect, some facets or metadata might not be returned properly.
ADECCO_FILTER_DISPLAY_IDS = "{7FEB8D10-300F-4942-AA2D-D54B994541E7}|{153DFF72-744A-440B-A2ED-DBAA6BC4C978}|{8DFDA1D6-96EB-4552-BDCB-F70FA9A5ADE5}|{93137178-D7CE-47F4-BA91-D70F4F77D5C1}"


class AdeccoProvider(BaseJobProvider):
    """
    Adecco Switzerland HTTP API Provider.
    """

    def __init__(self, include_raw_data: bool = False):
        self._include_raw_data = include_raw_data
        self._client: httpx.AsyncClient | None = None
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.adecco.com",
            "Referer": "https://www.adecco.com/en-ch/job-search",
        }

    @property
    def name(self) -> str:
        return "adecco"

    @property
    def display_name(self) -> str:
        return "Adecco.ch"

    def get_provider_info(self) -> "ProviderInfo":
        from backend.providers.jobs.models import ProviderInfo
        return ProviderInfo(
            name=self.name,
            description="Generalist job board covering all sectors in Switzerland. Adecco acts as an agency for many roles.",
            domain="adecco.ch",
            accepted_domains=["*"],
        )

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_radius_search=False,
            supports_canton_filter=False,
            supports_profession_codes=False,
            supports_language_skills=False,
            supports_company_filter=False,
            supports_work_forms=False,
            max_page_size=10,  # API enforces 10 items per page
            supported_languages=["en", "de"],
            supported_sort_orders=["date_desc", "relevance"],
        )

    async def __aenter__(self) -> "AdeccoProvider":
        self._client = httpx.AsyncClient(timeout=30.0, headers=self._headers)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search(self, request: JobSearchRequest) -> JobSearchResponse:
        """Search for jobs on Adecco."""
        start_time = time.time()
        
        should_close = False
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0, headers=self._headers)
            should_close = True

        try:
            # 1. Build Query Payload
            payload = {
                "queryString": build_query_string(request),
                "filtersToDisplay": ADECCO_FILTER_DISPLAY_IDS,
                "range": request.page * 10,  # Fixed page size is 10
                "siteName": "adecco",
                "brand": "adecco",
                "countryCode": "CH",
                "languageCode": "de-CH" if request.language == "de" else "en-CH",
            }

            # 2. Fetch Summarized Jobs
            @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
            async def fetch_jobs():
                resp = await self._client.post(f"{API_BASE_URL}/summarized", json=payload)
                resp.raise_for_status()
                return resp.json()

            summary_data = await fetch_jobs()
            
            if not isinstance(summary_data, dict) or "jobs" not in summary_data:
                raise ResponseParseError(self.name, "Unexpected response format from summarized API")

            jobs_light = summary_data["jobs"]
            total_count = summary_data.get("pagination", {}).get("total", len(jobs_light))

            # 3. Fetch Full Details
            hydrated_jobs = []
            sem = asyncio.Semaphore(5)

            @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
            async def fetch_job_details_with_retry(job_id: str, lang_code: str):
                detail_url = f"{API_BASE_URL}/job-description-details/{job_id}/adecco/CH/{lang_code}/job-details"
                detail_res = await self._client.get(detail_url)
                if detail_res.status_code == 200:
                    return detail_res.json()
                elif detail_res.status_code == 204:
                    # No detailed content available
                    return None
                detail_res.raise_for_status()

            async def process_job(light_job):
                job_id = light_job.get("jobId")
                if not job_id:
                    return None
                
                lang_code = payload["languageCode"]
                async with sem:
                    try:
                        detail_data = await fetch_job_details_with_retry(job_id, lang_code)
                        job_listing = transform_job_data(
                            light_job,
                            detail_data,
                            self.name,
                            self._include_raw_data
                        )
                        return job_listing
                    except Exception as e:
                        logger.warning(f"Failed to fetch details for {job_id} on {self.name}: {e}")
                        # Fallback to transform without details if detail fetch fails
                        try:
                            return transform_job_data(light_job, None, self.name, self._include_raw_data)
                        except Exception:
                            return None

            tasks = [process_job(job) for job in jobs_light]
            results = await asyncio.gather(*tasks)

            for job_listing in results:
                if job_listing:
                    job_listing.source = self.name
                    hydrated_jobs.append(job_listing)

            elapsed_ms = int((time.time() - start_time) * 1000)

            return JobSearchResponse(
                items=hydrated_jobs,
                total_count=total_count,
                page=request.page,
                page_size=10,  # Fixed internally by Adecco
                total_pages=(total_count + 9) // 10,
                source=self.name,
                search_time_ms=elapsed_ms,
                request=request,
            )

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise ProviderError(self.name, f"Search failed: {e}") from e
        finally:
            if should_close and self._client:
                await self.close()

    async def health_check(self) -> ProviderHealth:
        """Check if Adecco API is accessible."""
        start_time = time.time()
        should_close = False
        
        if not self._client:
            self._client = httpx.AsyncClient(timeout=10.0, headers=self._headers)
            should_close = True

        try:
            # Send a minimal valid search to check health
            payload = {
                "queryString": "&location:Switzerland&q=test",
                "filtersToDisplay": "{}",
                "range": 0,
                "siteName": "adecco",
                "brand": "adecco",
                "countryCode": "CH",
                "languageCode": "en-CH",
            }
            response = await self._client.post(f"{API_BASE_URL}/summarized", json=payload)
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
