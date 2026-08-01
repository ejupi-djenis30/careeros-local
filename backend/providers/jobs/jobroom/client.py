"""
Job-Room API Client.

Production-grade client for job-room.ch with:
- Full support for all API filters
- CSRF token handling for Angular security bypass
- Browser fingerprint simulation
- Multiple execution modes
"""

import asyncio
import logging
import time
from typing import Any, cast
from urllib.parse import quote

from backend.core.diagnostics import FailureCode, diagnose_failure, log_failure
from backend.providers.jobs.base import (
    JobProvider as BaseJobProvider,
)
from backend.providers.jobs.exceptions import (
    ProviderError,
    ResponseParseError,
)
from backend.providers.jobs.jobroom.constants import (
    API_BASE,
    BASE_URL,
    LANGUAGE_PARAMS,
)
from backend.providers.jobs.jobroom.mapper import BFSLocationMapper
from backend.providers.jobs.jobroom.request_builder import build_search_payload, build_search_url
from backend.providers.jobs.jobroom.transformer import transform_job_data
from backend.providers.jobs.models import (
    JobListing,
    JobSearchRequest,
    JobSearchResponse,
    ProviderCapabilities,
    ProviderHealth,
    ProviderInfo,
    ProviderStatus,
)

# ProviderCapabilities, ProviderHealth, ProviderStatus are now in models.py
from backend.providers.jobs.session import ExecutionMode, ScraperSession

logger = logging.getLogger(__name__)


class JobRoomProvider(BaseJobProvider):
    """
    Job-room.ch API provider.

    Implements the BaseJobProvider interface for accessing Swiss federal
    job portal data. Supports all available filters and handles the
    Angular CSRF security mechanism.

    Usage:
        async with JobRoomProvider() as provider:
            response = await provider.search(JobSearchRequest(
                query="Software Engineer",
                location="Zürich",
                workload_min=80
            ))

            for job in response.items:
                print(f"{job.title} at {job.company.name}")
    """

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.STEALTH,
        include_raw_data: bool = False,
    ):
        self._mode = mode
        self._include_raw_data = include_raw_data
        self._session: ScraperSession | None = None
        self._mapper = BFSLocationMapper()
        self._csrf_initialized = False
        self._session_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "job_room"

    @property
    def display_name(self) -> str:
        return "Job-Room.ch (SECO)"

    def get_provider_info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            description="Generalist Swiss federal job portal. Contains jobs across all industries and professions (IT, construction, hospitality, medical, etc.). Good default choice.",
            domain="job-room.ch",
            accepted_domains=["*"],
        )

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_radius_search=True,
            supports_canton_filter=True,
            supports_profession_codes=True,
            supports_language_skills=True,
            supports_company_filter=True,
            supports_work_forms=True,
            max_page_size=100,
            supported_languages=["en", "de", "fr", "it"],
            supported_sort_orders=["date_desc", "date_asc", "relevance"],
        )

    async def __aenter__(self) -> "JobRoomProvider":
        await self._init_session()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def _init_session(self) -> None:
        """Initialize HTTP session with CSRF token."""
        if self._session is not None and self._csrf_initialized:
            return

        async with self._session_lock:
            if self._session is not None and self._csrf_initialized:
                return

            session = self._session or ScraperSession(
                mode=self._mode,
                base_url=BASE_URL,
                provider=self.name,
            )
            try:
                await session.start()
                await session.refresh_csrf_token(BASE_URL)
            except BaseException:
                # A partially initialized client must not survive cancellation or
                # a failed CSRF bootstrap and get reused by the next operation.
                self._session = None
                self._csrf_initialized = False
                try:
                    await session.close()
                except Exception as cleanup_error:
                    diagnostic = diagnose_failure(
                        cleanup_error,
                        FailureCode.PROVIDER_REQUEST_FAILED,
                    )
                    log_failure(logger, diagnostic, level=logging.WARNING)
                raise

            self._session = session
            self._csrf_initialized = True

    async def close(self) -> None:
        """Close provider resources."""
        async with self._session_lock:
            session = self._session
            self._session = None
            self._csrf_initialized = False
            if session is not None:
                await session.close()

    def _parse_search_response(
        self,
        data: Any,
        *,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Validate the untrusted provider envelope before transforming jobs."""

        jobs: Any
        if isinstance(data, list):
            jobs = data
            total_count: Any = len(jobs)
        elif isinstance(data, dict):
            jobs = data.get("content", data.get("jobAdvertisements", []))
            total_count = data.get("totalElements", len(jobs) if isinstance(jobs, list) else 0)
        else:
            raise ResponseParseError(
                self.name,
                f"Unexpected response format: {type(data).__name__}",
            )

        if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
            raise ResponseParseError(self.name, "Expected a list of job objects")
        if len(jobs) > page_size:
            raise ResponseParseError(
                self.name,
                "Provider returned more jobs than the requested page size",
            )
        if (
            not isinstance(total_count, int)
            or isinstance(total_count, bool)
            or total_count < len(jobs)
        ):
            raise ResponseParseError(self.name, "Provider returned an invalid total count")

        return cast(list[dict[str, Any]], jobs), total_count

    # =========================================================================
    # Search Implementation
    # =========================================================================

    async def search(self, request: JobSearchRequest) -> JobSearchResponse:
        """Search for jobs on job-room.ch with all available filters."""
        await self._init_session()
        start_time = time.time()

        payload = build_search_payload(request, self._mapper)

        if self._session is None:
            raise ProviderError(self.name, "Session not initialized")
        url = build_search_url(request)

        try:
            response = await self._session.with_retry_csrf(
                method="POST",
                url=url,
                csrf_refresh_url=BASE_URL,
                json=payload,
            )

            data = response.json()

            jobs, total_count = self._parse_search_response(
                data,
                page_size=request.page_size,
            )

            transformed = [
                transform_job_data(job, self.name, self._include_raw_data) for job in jobs
            ]
            items = [item for item in transformed if item is not None]

            elapsed_ms = int((time.time() - start_time) * 1000)

            return JobSearchResponse(
                items=items,
                total_count=total_count,
                page=request.page,
                page_size=request.page_size,
                total_pages=(total_count + request.page_size - 1) // request.page_size,
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

    # =========================================================================
    # Job Details Implementation
    # =========================================================================

    async def get_details(self, job_id: str, language: str = "en") -> JobListing:
        """Get full details for a specific job."""
        if not isinstance(job_id, str):
            raise ProviderError(self.name, "Invalid job identifier")
        normalized_job_id = job_id.strip()
        if not normalized_job_id or len(normalized_job_id) > 256:
            raise ProviderError(self.name, "Invalid job identifier")

        await self._init_session()
        if self._session is None:
            raise ProviderError(self.name, "Session not initialized")

        lang_param = LANGUAGE_PARAMS.get(language, "ZW4=")
        url = f"{API_BASE}/{quote(normalized_job_id, safe='')}?_ng={lang_param}"

        try:
            response = await self._session.with_retry_csrf(
                method="GET",
                url=url,
                csrf_refresh_url=BASE_URL,
            )

            data = response.json()
            listing = transform_job_data(
                {"jobAdvertisement": data}, self.name, self._include_raw_data
            )
            if listing is None:
                raise ResponseParseError(self.name, "Job details request failed")
            return listing

        except Exception as error:
            diagnostic = diagnose_failure(error, FailureCode.PROVIDER_DETAIL_FAILED)
            log_failure(logger, diagnostic)
            raise ProviderError(
                self.name,
                "Job details request failed",
                diagnostic=diagnostic,
            ) from error

    # =========================================================================
    # Health Check
    # =========================================================================

    async def health_check(self) -> ProviderHealth:
        """Check if job-room.ch is accessible."""
        start_time = time.time()

        try:
            await self._init_session()
            if self._session is None:
                raise ProviderError(self.name, "Session not initialized")

            response = await self._session.get(BASE_URL)
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
