"""
Adecco API Client.
"""
import logging
import time
import asyncio
import random
import email.utils
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import httpx

from backend.providers.jobs.exceptions import ProviderError, ResponseParseError
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
ADECCO_FILTER_DISPLAY_IDS = "{7FEB8D10-300F-4942-AA2D-D54B994541E7}|{153DFF72-744A-440B-A2ED-DBAA6BC4C978}|{8DFDA1D6-96EB-4552-BDCB-F70FA9A5ADE5}|{93137178-D7CE-47F4-BA91-D70F4F77D5C1}"

class AdeccoProvider(BaseJobProvider):
    _global_sem = asyncio.Semaphore(2)

    def __init__(self, include_raw_data: bool = False):
        self._include_raw_data = include_raw_data
        self._client: httpx.AsyncClient | None = None
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,de-CH;q=0.8,de;q=0.7",
            "Origin": "https://www.adecco.com",
            "Referer": "https://www.adecco.com/en-ch/job-search",
            "Connection": "keep-alive"
        }

    @property
    def name(self) -> str:
        return "adecco"

    @property
    def display_name(self) -> str:
        return "Adecco.ch"

    def get_provider_info(self) -> Any:
        from backend.providers.jobs.models import ProviderInfo
        return ProviderInfo(
            name=self.name,
            description="Generalist job board covering all sectors in Switzerland.",
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
            max_page_size=10,
            supported_languages=["en", "de"],
            supported_sort_orders=["date_desc", "relevance"],
        )

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0, headers=self._headers)
        return self._client

    async def _execute_with_retry(self, func: Callable, *args, max_retries: int = 5, **kwargs) -> httpx.Response:
        for attempt in range(max_retries):
            try:
                response = await func(*args, **kwargs)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    await asyncio.sleep(retry_after)
                    continue
                response.raise_for_status()
                return response
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise e
        raise ProviderError(self.name, "Max retries exceeded")

    async def search(self, request: JobSearchRequest) -> JobSearchResponse:
        start_time = time.time()
        client = self._ensure_client()
        payload = {
            "queryString": build_query_string(request),
            "filtersToDisplay": ADECCO_FILTER_DISPLAY_IDS,
            "range": request.page * 10,
            "siteName": "adecco",
            "brand": "adecco",
            "countryCode": "CH",
            "languageCode": "de-CH" if request.language == "de" else "en-CH",
        }

        async with self._global_sem:
            resp = await self._execute_with_retry(client.post, f"{API_BASE_URL}/summarized", json=payload)
        
        summary_data = resp.json()
        jobs_light = summary_data.get("jobs", [])
        total_count = summary_data.get("pagination", {}).get("total", len(jobs_light))

        hydrated_jobs = []
        async def process_job(light_job):
            job_id = light_job.get("jobId")
            if not job_id: return None
            async with self._global_sem:
                try:
                    detail_url = f"{API_BASE_URL}/job-description-details/{job_id}/adecco/CH/{payload['languageCode']}/job-details"
                    detail_res = await self._execute_with_retry(client.get, detail_url)
                    detail_data = detail_res.json() if detail_res.status_code == 200 else None
                    return transform_job_data(light_job, detail_data, self.name, self._include_raw_data)
                except Exception:
                    return transform_job_data(light_job, None, self.name, self._include_raw_data)

        tasks = [process_job(job) for job in jobs_light]
        results = await asyncio.gather(*tasks)
        for job_listing in results:
            if job_listing: hydrated_jobs.append(job_listing)

        hydrated_jobs = filter_jobs(hydrated_jobs, request)
        elapsed_ms = int((time.time() - start_time) * 1000)

        return JobSearchResponse(
            items=hydrated_jobs,
            total_count=total_count,
            page=request.page,
            page_size=10,
            total_pages=(total_count + 9) // 10,
            source=self.name,
            search_time_ms=elapsed_ms,
            request=request,
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, status=ProviderStatus.HEALTHY, latency_ms=0)
