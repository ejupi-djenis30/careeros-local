"""
Adecco API Client.

Client for adecco.com/api/data/jobs fetching summarized jobs and detailed descriptions.
"""

import asyncio
import email.utils
import logging
import random
import time
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from backend.core.config import settings
from backend.core.diagnostics import FailureCode, diagnose_failure, log_failure
from backend.providers.jobs.adecco.filters import build_query_string, filter_jobs
from backend.providers.jobs.adecco.transformer import transform_job_data
from backend.providers.jobs.base import JobProvider as BaseJobProvider
from backend.providers.jobs.exceptions import (
    ProviderError,
    ResponseParseError,
)
from backend.providers.jobs.http_policy import (
    MAX_PROVIDER_RESPONSE_BYTES,
    assert_bounded_provider_response,
    provider_response_hooks,
)
from backend.providers.jobs.models import (
    ContractType,
    JobSearchRequest,
    JobSearchResponse,
    ProviderCapabilities,
    ProviderHealth,
    ProviderStatus,
)

logger = logging.getLogger(__name__)

API_BASE_URL = "https://www.adecco.com/api/data/jobs"
MAX_RETRY_DELAY_SECONDS = 30.0

# Adecco's Solr API expects these specific GUIDs to filter the response aggregations.
# If omitted or incorrect, some facets or metadata might not be returned properly.
ADECCO_FILTER_DISPLAY_IDS = "{7FEB8D10-300F-4942-AA2D-D54B994541E7}|{153DFF72-744A-440B-A2ED-DBAA6BC4C978}|{8DFDA1D6-96EB-4552-BDCB-F70FA9A5ADE5}|{93137178-D7CE-47F4-BA91-D70F4F77D5C1}"


class AdeccoProvider(BaseJobProvider):
    """
    Adecco Switzerland HTTP API Provider.
    """

    # Lazily-initialized semaphore to ensure it binds to the running event loop,
    # not the import-time loop (which can differ in tests or worker restarts).
    _global_sem: asyncio.Semaphore | None = None
    _global_sem_limit: int | None = None
    _global_sem_loop: asyncio.AbstractEventLoop | None = None
    _MAX_RESPONSE_BYTES = MAX_PROVIDER_RESPONSE_BYTES

    @classmethod
    def _get_semaphore(cls) -> asyncio.Semaphore:
        """Return the class-level semaphore, creating it on the current event loop if needed."""
        desired_limit = max(1, int(getattr(settings, "ADECCO_DETAIL_CONCURRENCY", 4) or 4))
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if (
            cls._global_sem is None
            or cls._global_sem_limit != desired_limit
            or (current_loop is not None and cls._global_sem_loop is not current_loop)
        ):
            cls._global_sem = asyncio.Semaphore(desired_limit)
            cls._global_sem_limit = desired_limit
            cls._global_sem_loop = current_loop
        return cls._global_sem

    def __init__(self, include_raw_data: bool = False):
        self._include_raw_data = include_raw_data
        self._client: httpx.AsyncClient | None = None

        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
        ]

        self._headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "identity",
            "Accept-Language": "en-US,en;q=0.9,de-CH;q=0.8,de;q=0.7",
            "Origin": "https://www.adecco.com",
            "Referer": "https://www.adecco.com/en-ch/job-search",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
        }

    @property
    def name(self) -> str:
        return "adecco"

    @property
    def throttle_delay(self) -> float:
        """Adecco API rate-limits aggressive crawling; pause 1 second between pages."""
        return 1.0

    @property
    def display_name(self) -> str:
        return "Adecco.ch"

    def get_provider_info(self) -> Any:
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
        self._ensure_client()
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
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers=self._headers,
                follow_redirects=False,
                trust_env=False,
                event_hooks=provider_response_hooks(
                    self.name,
                    max_bytes=self._MAX_RESPONSE_BYTES,
                ),
            )
        return self._client

    @staticmethod
    def _should_prefilter_light_jobs(request: JobSearchRequest) -> bool:
        return (
            request.contract_type != ContractType.ANY
            or request.workload_min > 0
            or request.workload_max < 100
            or bool(request.work_forms)
        )

    def _passes_light_filters(self, light_job: dict[str, Any], request: JobSearchRequest) -> bool:
        preview_listing = transform_job_data(light_job, None, self.name, False)
        if preview_listing is None:
            return True
        return bool(filter_jobs([preview_listing], request))

    async def _execute_with_retry(
        self,
        func: Callable,
        *args,
        max_retries: int = 10,
        sem: asyncio.Semaphore | None = None,
        **kwargs,
    ) -> httpx.Response:
        """Execute HTTP request with 429-aware retry logic and exponential backoff.

        ``sem``: if provided, the semaphore is acquired only around the raw HTTP
        call itself.  Backoff sleeps happen *outside* the semaphore so that other
        concurrent requests are not blocked while we wait to retry a 429.

        This completely replaces the generic @retry from tenacity for Adecco's specifics."""
        for attempt in range(max_retries):
            try:
                if sem is not None:
                    async with sem:
                        response = await func(*args, **kwargs)
                else:
                    response = await func(*args, **kwargs)
                assert_bounded_provider_response(
                    response,
                    self.name,
                    max_bytes=self._MAX_RESPONSE_BYTES,
                )
                if response.status_code == 429:
                    raise httpx.HTTPStatusError(
                        "429 Too Many Requests", request=response.request, response=response
                    )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 429 and attempt < max_retries - 1:
                    retry_after = e.response.headers.get("Retry-After")
                    sleep_time = None
                    if retry_after:
                        if retry_after.isascii() and retry_after.isdigit():
                            sleep_time = (
                                MAX_RETRY_DELAY_SECONDS
                                if len(retry_after) > 10
                                else min(MAX_RETRY_DELAY_SECONDS, float(retry_after))
                            )
                        else:
                            try:
                                dt = email.utils.parsedate_to_datetime(retry_after)
                                sleep_time = min(
                                    MAX_RETRY_DELAY_SECONDS,
                                    max(0, (dt - datetime.now(timezone.utc)).total_seconds()),
                                )
                            except (OverflowError, TypeError, ValueError) as parse_error:
                                diagnostic = diagnose_failure(
                                    parse_error,
                                    FailureCode.PROVIDER_RETRY_HEADER_INVALID,
                                )
                                log_failure(logger, diagnostic, level=logging.WARNING)

                    if sleep_time is None:
                        # Stricter backoff for 429 than other errors: 4s, then 8s, capped at 30s
                        sleep_time = min(
                            MAX_RETRY_DELAY_SECONDS,
                            random.uniform(4.0, 7.0) * (attempt + 1),
                        )

                    logger.warning(
                        "Adecco rate_limited retry_seconds=%.1f attempt=%d max_attempts=%d",
                        sleep_time,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(sleep_time)
                    continue
                # Retry on transient server errors
                elif status in (500, 502, 503, 504) and attempt < max_retries - 1:
                    sleep_time = min(
                        MAX_RETRY_DELAY_SECONDS,
                        random.uniform(2.0, 5.0) * (attempt + 1),
                    )
                    logger.warning(
                        "Adecco transient_http_status=%d retry_seconds=%.1f "
                        "attempt=%d max_attempts=%d",
                        status,
                        sleep_time,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(sleep_time)
                    continue
                raise
            except (httpx.RequestError, asyncio.TimeoutError) as e:
                if attempt < max_retries - 1:
                    sleep_time = min(
                        MAX_RETRY_DELAY_SECONDS,
                        random.uniform(2.0, 5.0) * (attempt + 1),
                    )
                    diagnostic = diagnose_failure(e, FailureCode.PROVIDER_REQUEST_FAILED)
                    log_failure(logger, diagnostic, level=logging.WARNING)
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

            # 2. Fetch Summarized Jobs — semaphore is passed INTO _execute_with_retry
            # so it is released during backoff sleeps and not held for up to 28 seconds.
            resp = await self._execute_with_retry(
                client.post,
                f"{API_BASE_URL}/summarized",
                json=payload,
                max_retries=10,
                sem=self._get_semaphore(),
            )
            summary_data = resp.json()

            if not isinstance(summary_data, dict) or "jobs" not in summary_data:
                raise ResponseParseError(
                    self.name, "Unexpected response format from summarized API"
                )

            jobs_light = summary_data["jobs"]
            total_count = summary_data.get("pagination", {}).get("total", len(jobs_light))
            should_prefilter = self._should_prefilter_light_jobs(request)
            prefilter_skip = object()

            # 3. Fetch Full Details
            hydrated_jobs = []

            async def process_job(light_job):
                job_id = light_job.get("jobId")
                if not job_id:
                    return None

                if should_prefilter and not self._passes_light_filters(light_job, request):
                    return prefilter_skip

                lang_code = payload["languageCode"]

                try:
                    detail_url = f"{API_BASE_URL}/job-description-details/{job_id}/adecco/CH/{lang_code}/job-details"

                    detail_data = None
                    try:
                        # Semaphore passed into _execute_with_retry so it is released
                        # during backoff sleeps (not held for up to 28 seconds).
                        detail_res = await self._execute_with_retry(
                            client.get,
                            detail_url,
                            max_retries=10,
                            sem=self._get_semaphore(),
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
                        light_job, detail_data, self.name, self._include_raw_data
                    )
                    return job_listing
                except Exception as error:
                    diagnostic = diagnose_failure(error, FailureCode.PROVIDER_DETAIL_FAILED)
                    log_failure(logger, diagnostic, level=logging.WARNING)
                    # Fallback to transform without details if detail fetch fails
                    try:
                        return transform_job_data(
                            light_job, None, self.name, self._include_raw_data
                        )
                    except Exception as error:
                        diagnostic = diagnose_failure(
                            error,
                            FailureCode.PROVIDER_TRANSFORM_FAILED,
                        )
                        log_failure(logger, diagnostic, level=logging.WARNING)
                        return None

            tasks = [process_job(job) for job in jobs_light]
            results = await asyncio.gather(*tasks)
            skipped_light_filtered = 0

            for job_listing in results:
                if job_listing is prefilter_skip:
                    skipped_light_filtered += 1
                    continue
                if job_listing:
                    job_listing.source = self.name
                    hydrated_jobs.append(job_listing)

            if skipped_light_filtered:
                total_count = max(0, total_count - skipped_light_filtered)

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

        except Exception as error:
            diagnostic = diagnose_failure(error, FailureCode.PROVIDER_REQUEST_FAILED)
            log_failure(logger, diagnostic)
            raise ProviderError(
                self.name,
                "Search failed",
                diagnostic=diagnostic,
            ) from error

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

            async with self._get_semaphore():
                response = await client.post(f"{API_BASE_URL}/summarized", json=payload)
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
