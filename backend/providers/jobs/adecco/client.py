"""
Adecco API Client.

Client for adecco.com/api/data/jobs fetching summarized jobs and detailed descriptions.
"""

import logging
import time
from typing import Any, Callable
import asyncio
import random
import email.utils
from datetime import datetime, timezone

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

from backend.providers.jobs.adecco.filters import build_query_string, filter_jobs
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
    
    # Class-level global semaphore to throttle all concurrent Adecco requests
    # regardless of how many parallel searches (queries) are running.
    # This prevents SEARCH_CONCURRENCY=3 from spawning 6+ detail requests.
    _global_sem = asyncio.Semaphore(2)

    def __init__(self, include_raw_data: bool = False):
        self._include_raw_data = include_raw_data
        self._client: httpx.AsyncClient | None = None
        
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
        ]
        
        self._headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,de-CH;q=0.8,de;q=0.7",
            "Origin": "https://www.adecco.com",
            "Referer": "https://www.adecco.com/en-ch/job-search",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive"
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
            supports_radius_search=True,
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

    def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily create and return the shared HTTP client.
        The client is kept alive for the provider's lifetime to avoid
        race conditions when multiple concurrent searches share this instance."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0, headers=self._headers)
        return self._client

    async def _execute_with_retry(self, func: Callable, *args, max_retries: int = 10, **kwargs) -> httpx.Response:
        """Execute HTTP request with 429-aware retry logic and exponential backoff.
        This completely replaces the generic @retry from tenacity for Adecco's specifics."""
        for attempt in range(max_retries):
            try:
                response = await func(*args, **kwargs)
                if response.status_code == 429:
                    raise httpx.HTTPStatusError("429 Too Many Requests", request=response.request, response=response)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 429 and attempt < max_retries - 1:
                    retry_after = e.response.headers.get("Retry-After")
                    sleep_time = None
                    if retry_after:
                        if retry_after.isdigit():
                            sleep_time = int(retry_after)
                        else:
                            try:
                                dt = email.utils.parsedate_to_datetime(retry_after)
                                sleep_time = max(0, (dt - datetime.now(timezone.utc)).total_seconds())
                            except (TypeError, ValueError):
                                pass
                    
                    if sleep_time is None:
                        # Stricter backoff for 429 than other errors: 4s, then 8s
                        sleep_time = random.uniform(4.0, 7.0) * (attempt + 1)
                    
                    logger.warning(f"Adecco 429 Too Many Requests. Retrying in {sleep_time:.1f}s (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(sleep_time)
                    continue
                # Retry on transient server errors
                elif status in (500, 502, 503, 504) and attempt < max_retries - 1:
                    sleep_time = random.uniform(2.0, 5.0) * (attempt + 1)
                    logger.warning(f"Adecco {status} Error. Retrying in {sleep_time:.1f}s (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(sleep_time)
                    continue
                raise
            except (httpx.RequestError, asyncio.TimeoutError) as e:
                if attempt < max_retries - 1:
                    sleep_time = random.uniform(2.0, 5.0) * (attempt + 1)
                    logger.warning(f"Adecco transient error {type(e).__name__}. Retrying in {sleep_time:.1f}s (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(sleep_time)
                    continue
                raise
        # Fallback to raising the ProviderError if loop somehow finishes without raising
        raise ProviderError(self.name, "Max retries exceeded")

    async def search(self, request: JobSearchRequest) -> JobSearchResponse:
        """Search for jobs on Adecco."""
        start_time = time.time()
        client = self._ensure_client()

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
            async with self._global_sem:
                resp = await self._execute_with_retry(
                    client.post,
                    f"{API_BASE_URL}/summarized",
                    json=payload,
                    max_retries=10
                )
            summary_data = resp.json()
            
            if not isinstance(summary_data, dict) or "jobs" not in summary_data:
                raise ResponseParseError(self.name, "Unexpected response format from summarized API")

            jobs_light = summary_data["jobs"]
            total_count = summary_data.get("pagination", {}).get("total", len(jobs_light))

            # 3. Fetch Full Details
            hydrated_jobs = []

            async def process_job(light_job):
                job_id = light_job.get("jobId")
                if not job_id:
                    return None
                
                lang_code = payload["languageCode"]
                
                # Random delay BEFORE fetching details to spread out requests
                # without wasting a concurrency slot in the global semaphore
                await asyncio.sleep(random.uniform(1.0, 2.5))
                
                async with self._global_sem:
                    try:
                        detail_url = f"{API_BASE_URL}/job-description-details/{job_id}/adecco/CH/{lang_code}/job-details"
                        
                        detail_data = None
                        try:
                            # Use custom retry executing routine
                            detail_res = await self._execute_with_retry(
                                client.get,
                                detail_url,
                                max_retries=10
                            )
                            if detail_res.status_code == 200:
                                detail_data = detail_res.json()
                            elif detail_res.status_code == 204:
                                detail_data = None
                        except httpx.HTTPStatusError as he:
                            if he.response.status_code == 404:
                                detail_data = None
                            else:
                                raise

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

            # 4. Apply In-Memory Filters (Contract Type, Workload, etc.)
            successfully_hydrated_count = len(hydrated_jobs)
            hydrated_jobs = filter_jobs(hydrated_jobs, request)
            
            # Update total_count based on how many valid jobs were filtered out
            if len(hydrated_jobs) < successfully_hydrated_count:
                diff = successfully_hydrated_count - len(hydrated_jobs)
                total_count = max(0, total_count - diff)

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
            from backend.providers.jobs.exceptions import format_provider_error
            err_msg = format_provider_error(e)
            logger.error(f"Search failed: {err_msg}")
            raise ProviderError(self.name, err_msg) from e

    async def health_check(self) -> ProviderHealth:
        """Check if Adecco API is accessible."""
        start_time = time.time()
        client = self._ensure_client()

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
            
            async with self._global_sem:
                response = await client.post(f"{API_BASE_URL}/summarized", json=payload)
                
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
