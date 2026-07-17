"""
Job-Room API Client.

Production-grade client for job-room.ch with:
- Full support for all API filters
- CSRF token handling for Angular security bypass
- Browser fingerprint simulation
- Multiple execution modes
"""

import logging
import time
from typing import Any, cast

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
        if self._session is None:
            self._session = ScraperSession(
                mode=self._mode,
                base_url=BASE_URL,
            )
            await self._session.start()

        if self._session and not self._csrf_initialized:
            await self._session.refresh_csrf_token(BASE_URL)
            self._csrf_initialized = True

    async def close(self) -> None:
        """Close provider resources."""
        if self._session:
            await self._session.close()
            self._session = None
            self._csrf_initialized = False

    # =========================================================================
    # Search Implementation
    # =========================================================================

    async def search(self, request: JobSearchRequest) -> JobSearchResponse:
        """Search for jobs on job-room.ch with all available filters."""
        await self._init_session()
        start_time = time.time()

        payload = build_search_payload(request, self._mapper)

        if self._session is None:
            raise ProviderError(self.name, "Session not initialized — _init_session() failed")
        url = build_search_url(request)

        try:
            response = await self._session.with_retry_csrf(
                method="POST",
                url=url,
                csrf_refresh_url=BASE_URL,
                json=payload,
            )

            data = response.json()

            if isinstance(data, list):
                jobs = data
                total_count = len(jobs)
            elif isinstance(data, dict):
                jobs = cast(list[Any], data.get("content", data.get("jobAdvertisements", [])))
                total_count = data.get("totalElements", len(jobs))
            else:
                raise ResponseParseError(self.name, f"Unexpected response format: {type(data)}")

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

        except Exception as e:
            from backend.providers.jobs.exceptions import format_provider_error

            err_msg = format_provider_error(e)
            logger.error(f"Search failed: {err_msg}")
            raise ProviderError(self.name, err_msg) from e

    # =========================================================================
    # Job Details Implementation
    # =========================================================================

    async def get_details(self, job_id: str, language: str = "en") -> JobListing:
        """Get full details for a specific job."""
        await self._init_session()
        if self._session is None:
            raise ProviderError(self.name, "Session not initialized — _init_session() failed")

        lang_param = LANGUAGE_PARAMS.get(language, "ZW4=")
        url = f"{API_BASE}/{job_id}?_ng={lang_param}"

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
                raise ResponseParseError(
                    self.name,
                    f"Could not transform job-room details for id={job_id}",
                )
            return listing

        except Exception as e:
            from backend.providers.jobs.exceptions import format_provider_error

            err_msg = format_provider_error(e)
            logger.error(f"Failed to get job details: {err_msg}")
            raise ProviderError(self.name, err_msg) from e

    # =========================================================================
    # Health Check
    # =========================================================================

    async def health_check(self) -> ProviderHealth:
        """Check if job-room.ch is accessible."""
        start_time = time.time()

        try:
            await self._init_session()
            if self._session is None:
                raise ProviderError(self.name, "Session not initialized — _init_session() failed")

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

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return ProviderHealth(
                provider=self.name,
                status=ProviderStatus.UNAVAILABLE,
                latency_ms=latency_ms,
                message=str(e),
            )
