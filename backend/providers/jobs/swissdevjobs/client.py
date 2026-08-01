"""
SwissDevJobs API Client.

Client for swissdevjobs.ch fetching via the jobsLight API and retrieving details via jobWithUrl.
"""

import asyncio
import logging
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from backend.core.diagnostics import FailureCode, diagnose_failure, log_failure
from backend.providers.jobs.base import JobProvider as BaseJobProvider
from backend.providers.jobs.exceptions import (
    ProviderError,
    ResponseParseError,
)
from backend.providers.jobs.http_policy import (
    MAX_PROVIDER_RESPONSE_BYTES,
    assert_bounded_provider_response,
    is_retryable_provider_http_error,
    provider_response_hooks,
)
from backend.providers.jobs.models import (
    JobSearchRequest,
    JobSearchResponse,
    ProviderCapabilities,
    ProviderHealth,
    ProviderInfo,
    ProviderStatus,
)

# Import extracted logic
from backend.providers.jobs.swissdevjobs.filters import filter_jobs
from backend.providers.jobs.swissdevjobs.transformer import transform_job_data

logger = logging.getLogger(__name__)

API_BASE_URL = "https://swissdevjobs.ch/api"


def _consume_task_exception(task: asyncio.Task[Any]) -> None:
    """Retrieve abandoned single-flight failures without changing await semantics."""

    if not task.cancelled():
        task.exception()


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

    _LIGHT_JOBS_CACHE_TTL_SECONDS = 3600.0
    _LIGHT_JOBS_MAX_ENTRIES = 10_000
    _DETAIL_JOBS_CACHE_TTL_SECONDS = 3600.0
    # Detail payloads can include long descriptions and raw provider fields.
    # Keep the hour-long reuse window without allowing a long-running desktop
    # process to retain every job that has ever been opened.
    _DETAIL_JOBS_CACHE_MAX_ENTRIES = 256
    _DETAIL_CONCURRENCY = 5
    _MAX_RESPONSE_BYTES = MAX_PROVIDER_RESPONSE_BYTES

    def __init__(self, include_raw_data: bool = False):
        self._include_raw_data = include_raw_data
        self._client: httpx.AsyncClient | None = None
        self._light_jobs_cache: list[dict[str, Any]] | None = None
        self._cache_time: float = 0
        self._cache_lock: asyncio.Lock = asyncio.Lock()
        self._detail_jobs_cache: dict[str, tuple[float, Any]] = {}
        self._detail_jobs_inflight: dict[str, asyncio.Task[Any]] = {}
        self._detail_cache_lock: asyncio.Lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "swissdevjobs"

    @property
    def display_name(self) -> str:
        return "SwissDevJobs.ch"

    def get_provider_info(self) -> ProviderInfo:
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
        self._ensure_client()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close HTTP client."""
        async with self._detail_cache_lock:
            inflight_tasks = list(set(self._detail_jobs_inflight.values()))
            self._detail_jobs_inflight.clear()
        for task in inflight_tasks:
            task.cancel()
        if inflight_tasks:
            await asyncio.gather(*inflight_tasks, return_exceptions=True)
        if self._client:
            await self._client.aclose()
            self._client = None
        self._light_jobs_cache = None
        self._cache_time = 0
        self._detail_jobs_cache.clear()
        self._detail_jobs_inflight.clear()

    def _new_client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=timeout,
            headers={"Accept-Encoding": "identity"},
            follow_redirects=False,
            trust_env=False,
            event_hooks=provider_response_hooks(
                self.name,
                max_bytes=self._MAX_RESPONSE_BYTES,
            ),
        )

    def _ensure_client(self, *, timeout: float = 30.0) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = self._new_client(timeout)
        return self._client

    @retry(
        retry=retry_if_exception(is_retryable_provider_http_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _fetch_light_jobs_with_retry(self) -> Any:
        client = self._ensure_client()
        resp = await client.get(f"{API_BASE_URL}/jobsLight")
        assert_bounded_provider_response(
            resp,
            self.name,
            max_bytes=self._MAX_RESPONSE_BYTES,
        )
        resp.raise_for_status()
        return resp.json()

    @retry(
        retry=retry_if_exception(is_retryable_provider_http_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _fetch_job_details_with_retry(self, job_url_slug: str) -> Any:
        client = self._ensure_client()
        detail_res = await client.get(f"{API_BASE_URL}/jobWithUrl/{job_url_slug}")
        assert_bounded_provider_response(
            detail_res,
            self.name,
            max_bytes=self._MAX_RESPONSE_BYTES,
        )
        detail_res.raise_for_status()
        detail_data = detail_res.json()
        if isinstance(detail_data, list):
            return detail_data[0] if detail_data else {}
        return detail_data

    async def _get_light_jobs(self) -> list[dict[str, Any]]:
        async with self._cache_lock:
            if (
                self._light_jobs_cache is None
                or time.monotonic() - self._cache_time > self._LIGHT_JOBS_CACHE_TTL_SECONDS
            ):
                fresh_jobs = await self._fetch_light_jobs_with_retry()
                if not isinstance(fresh_jobs, list) or any(
                    not isinstance(job, dict) for job in fresh_jobs
                ):
                    raise ResponseParseError(self.name, "Expected a list from jobsLight API")
                if len(fresh_jobs) > self._LIGHT_JOBS_MAX_ENTRIES:
                    raise ResponseParseError(
                        self.name,
                        "Provider response exceeded the safe item limit",
                    )
                self._light_jobs_cache = fresh_jobs
                self._cache_time = time.monotonic()

            all_jobs_light = self._light_jobs_cache

        if all_jobs_light is None:  # Defensive guard for future cache refactors.
            raise ResponseParseError(self.name, "Expected a list from jobsLight API")
        return all_jobs_light

    async def _fetch_and_cache_job_details(self, job_url_slug: str) -> Any:
        current_task = asyncio.current_task()
        try:
            detail_data = await self._fetch_job_details_with_retry(job_url_slug)
            async with self._detail_cache_lock:
                if self._detail_jobs_inflight.get(job_url_slug) is current_task:
                    self._detail_jobs_cache.pop(job_url_slug, None)
                    self._detail_jobs_cache[job_url_slug] = (
                        time.monotonic(),
                        detail_data,
                    )
                    while len(self._detail_jobs_cache) > self._DETAIL_JOBS_CACHE_MAX_ENTRIES:
                        oldest_slug = next(iter(self._detail_jobs_cache))
                        self._detail_jobs_cache.pop(oldest_slug)
            return detail_data
        finally:
            async with self._detail_cache_lock:
                if self._detail_jobs_inflight.get(job_url_slug) is current_task:
                    self._detail_jobs_inflight.pop(job_url_slug, None)

    async def _get_job_details(self, job_url_slug: str) -> Any:
        now = time.monotonic()
        async with self._detail_cache_lock:
            cached_entry = self._detail_jobs_cache.get(job_url_slug)
            if cached_entry is not None:
                cached_at, cached_detail = cached_entry
                if now - cached_at <= self._DETAIL_JOBS_CACHE_TTL_SECONDS:
                    # Dict insertion order gives us a compact LRU: refresh a
                    # hot entry so eviction prefers the least recently used.
                    self._detail_jobs_cache.pop(job_url_slug)
                    self._detail_jobs_cache[job_url_slug] = cached_entry
                    return cached_detail
                self._detail_jobs_cache.pop(job_url_slug, None)

            inflight_task = self._detail_jobs_inflight.get(job_url_slug)
            if inflight_task is None:
                inflight_task = asyncio.create_task(self._fetch_and_cache_job_details(job_url_slug))
                inflight_task.add_done_callback(_consume_task_exception)
                self._detail_jobs_inflight[job_url_slug] = inflight_task

        return await asyncio.shield(inflight_task)

    async def search(self, request: JobSearchRequest) -> JobSearchResponse:
        """Search for jobs on swissdevjobs.ch."""
        start_time = time.time()

        self._ensure_client()

        try:
            all_jobs_light = await self._get_light_jobs()

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
            sem = asyncio.Semaphore(self._DETAIL_CONCURRENCY)

            async def fetch_job_details(light_job):
                job_url_slug = light_job.get("jobUrl")
                if not job_url_slug:
                    return None

                async with sem:
                    try:
                        detail_data = await self._get_job_details(job_url_slug)
                        job_listing = transform_job_data(
                            detail_data, light_job, self.name, self._include_raw_data
                        )
                        return job_listing
                    except Exception as error:
                        diagnostic = diagnose_failure(
                            error,
                            FailureCode.PROVIDER_DETAIL_FAILED,
                        )
                        log_failure(logger, diagnostic, level=logging.WARNING)
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

        except Exception as error:
            diagnostic = diagnose_failure(error, FailureCode.PROVIDER_REQUEST_FAILED)
            log_failure(logger, diagnostic)
            raise ProviderError(
                self.name,
                "Search failed",
                diagnostic=diagnostic,
            ) from error

    async def health_check(self) -> ProviderHealth:
        """Check if swissdevjobs.ch API is accessible."""
        start_time = time.time()
        should_close = False

        if self._client is None or self._client.is_closed:
            should_close = True

        try:
            response = await self._ensure_client(timeout=10.0).get(
                f"{API_BASE_URL}/jobsLight",
                timeout=10.0,
            )
            assert_bounded_provider_response(
                response,
                self.name,
                max_bytes=self._MAX_RESPONSE_BYTES,
            )
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
        except Exception as error:
            latency_ms = int((time.time() - start_time) * 1000)
            diagnostic = diagnose_failure(error, FailureCode.PROVIDER_HEALTH_FAILED)
            log_failure(logger, diagnostic, level=logging.WARNING)
            return ProviderHealth(
                provider=self.name,
                status=ProviderStatus.UNAVAILABLE,
                latency_ms=latency_ms,
                message=diagnostic.public_message,
            )
        finally:
            if should_close:
                await self.close()
