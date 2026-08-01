import logging
import re
from enum import Enum
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from backend.core.diagnostics import FailureCode, diagnose_failure, log_failure
from backend.providers.jobs.http_policy import (
    MAX_PROVIDER_RESPONSE_BYTES,
    assert_bounded_provider_response,
    is_retryable_provider_http_error,
    provider_response_hooks,
)

logger = logging.getLogger(__name__)


class ExecutionMode(str, Enum):
    STEALTH = "stealth"
    FAST = "fast"


class ScraperSession:
    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.FAST,
        base_url: Optional[str] = None,
        *,
        provider: str = "job_room",
        max_response_bytes: int = MAX_PROVIDER_RESPONSE_BYTES,
    ):
        self.mode = mode
        self.base_url = base_url
        self.provider = provider
        self.max_response_bytes = max_response_bytes
        self._response_hooks = provider_response_hooks(
            provider,
            max_bytes=max_response_bytes,
        )
        self.client: Optional[httpx.AsyncClient] = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "identity",
        }
        self.csrf_token: Optional[str] = None

    async def start(self):
        if self.client is not None and not self.client.is_closed:
            return
        self.client = httpx.AsyncClient(
            headers=self.headers,
            verify=True,
            follow_redirects=False,
            trust_env=False,
            timeout=30.0,
            event_hooks=self._response_hooks,
        )

    async def close(self):
        if self.client:
            await self.client.aclose()
            self.client = None

    async def get(self, url: str):
        if not self.client:
            await self.start()
        response = await self.client.get(self._provider_url(url))
        return assert_bounded_provider_response(
            response,
            self.provider,
            max_bytes=self.max_response_bytes,
        )

    def _provider_url(self, url: str) -> str:
        candidate = str(url).strip()
        base = str(self.base_url or "").strip()
        if (
            not candidate
            or not base
            or "\\" in candidate
            or re.search(r"[\x00-\x20\x7f]", candidate)
        ):
            raise ValueError("URL must remain on the configured HTTPS provider origin")
        try:
            parsed = urlsplit(candidate)
            configured = urlsplit(base)
            parsed_port = parsed.port or 443
            configured_port = configured.port or 443
        except ValueError as error:
            raise ValueError("URL must remain on the configured HTTPS provider origin") from error
        if (
            parsed.scheme.lower() != "https"
            or configured.scheme.lower() != "https"
            or not parsed.hostname
            or not configured.hostname
            or parsed.username is not None
            or parsed.password is not None
            or configured.username is not None
            or configured.password is not None
            or parsed.hostname.lower() != configured.hostname.lower()
            or parsed_port != configured_port
        ):
            raise ValueError("URL must remain on the configured HTTPS provider origin")
        return candidate

    async def refresh_csrf_token(self, url: str):
        """Fetch index page to get CSRF token (Angular app)."""
        # JobRoom uses X-XSRF-TOKEN header from cookies or similar.
        # usually Angular sets a cookie 'XSRF-TOKEN', client reads it and sends 'X-XSRF-TOKEN'.
        await self.get(url)
        # In many systems, just visiting the page sets the cookie.
        # Httpx client stores cookies automatically.
        # We might need to extract it manually if the client logic expects it in a header.

        # Check cookies
        for cookie in self.client.cookies.jar:
            if cookie.name == "XSRF-TOKEN":
                self.csrf_token = cookie.value
                self.client.headers["X-XSRF-TOKEN"] = self.csrf_token
                logger.info("CSRF Token refreshed")
                break

    @retry(
        retry=retry_if_exception(is_retryable_provider_http_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def with_retry_csrf(
        self,
        method: str,
        url: str,
        csrf_refresh_url: str,
        json: Optional[Dict[str, Any]] = None,
    ):
        request_url = self._provider_url(url)
        refresh_url = self._provider_url(csrf_refresh_url)
        if not self.client:
            await self.start()

        # Ensure we have CSRF if needed
        if method in ["POST", "PUT", "DELETE"] and not self.csrf_token:
            await self.refresh_csrf_token(refresh_url)

        try:
            response = await self.client.request(method, request_url, json=json)
            assert_bounded_provider_response(
                response,
                self.provider,
                max_bytes=self.max_response_bytes,
            )
            if response.status_code == 403 or response.status_code == 401:
                logger.warning("CSRF/Auth failed, retrying once...")
                await self.refresh_csrf_token(refresh_url)
                response = await self.client.request(method, request_url, json=json)
                assert_bounded_provider_response(
                    response,
                    self.provider,
                    max_bytes=self.max_response_bytes,
                )

            response.raise_for_status()
            return response
        except httpx.HTTPError as error:
            diagnostic = diagnose_failure(error, FailureCode.HTTP_REQUEST_FAILED)
            log_failure(logger, diagnostic)
            raise
