"""Runtime adapter for strict declarative JSON and HTML job providers."""

from __future__ import annotations

import asyncio
import json
import math
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import httpx

from backend.applications.schemas import normalize_application_email
from backend.providers.configuration.html_extract import (
    HtmlExtractionError,
    parse_html,
    select_all,
    select_one,
    text_content,
)
from backend.providers.configuration.network_policy import (
    UnsafeProviderDestination,
    resolve_public_destination,
    validate_destination_literal,
)
from backend.providers.configuration.schemas import (
    ProviderConfigurationInput,
    ProviderFieldMapping,
)
from backend.providers.jobs.base import JobProvider
from backend.providers.jobs.exceptions import ProviderError, ResponseParseError
from backend.providers.jobs.http_policy import (
    assert_bounded_provider_response,
    is_retryable_provider_http_error,
    provider_response_hooks,
)
from backend.providers.jobs.models import (
    ApplicationChannel,
    CompanyInfo,
    EmploymentDetails,
    JobDescription,
    JobListing,
    JobLocation,
    JobSearchRequest,
    JobSearchResponse,
    ProviderCapabilities,
    ProviderInfo,
)

_TEMPLATE_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
MAX_PARSED_ITEMS = 200
MAX_TOTAL_COUNT = 1_000_000


def _template_values(request: JobSearchRequest) -> dict[str, str]:
    return {
        "query": request.query,
        "location": request.location,
        "language": request.language,
        "page": str(request.page),
        "page_one_based": str(request.page + 1),
        "page_size": str(request.page_size),
        "offset": str(request.page * request.page_size),
        "workload_min": str(request.workload_min),
        "workload_max": str(request.workload_max),
    }


def _render_string(value: str, variables: dict[str, str], *, path: bool = False) -> str:
    return _TEMPLATE_RE.sub(
        lambda match: (
            quote(variables[match.group(1)], safe="") if path else variables[match.group(1)]
        ),
        value,
    )


def _render_json(value: Any, variables: dict[str, str]) -> Any:
    if isinstance(value, str):
        return _render_string(value, variables)
    if isinstance(value, list):
        return [_render_json(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: _render_json(item, variables) for key, item in value.items()}
    return value


def _json_value(value: Any, path: str) -> Any:
    current = value
    normalized = path[2:] if path.startswith("$.") else path
    if normalized == "$":
        return current
    for part in normalized.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _safe_text(value: Any, *, maximum: int = 20_000) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, str | int | float):
        text = str(value)
    else:
        return ""
    return " ".join(text.split())[:maximum]


def _safe_url(value: str, base_url: str) -> str | None:
    if not value:
        return None
    candidate = urljoin(f"{base_url}/", value)
    parsed = urlsplit(candidate)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or len(candidate) > 2_048
    ):
        return None
    try:
        validate_destination_literal(candidate)
    except (UnsafeProviderDestination, ValueError):
        return None
    return candidate


def _bounded_int(value: str, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, parsed))


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class DeclarativeJobProvider(JobProvider):
    def __init__(self, configuration: ProviderConfigurationInput) -> None:
        if not configuration.enabled:
            raise ValueError("A disabled declarative provider cannot execute")
        self.configuration = configuration
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return self.configuration.key

    @property
    def throttle_delay(self) -> float:
        return self.configuration.request.throttle_ms / 1_000

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            max_page_size=self.configuration.request.page_size,
            supported_languages=self.configuration.capabilities.supported_languages,
            supported_sort_orders=["date_desc", "relevance"],
        )

    def get_provider_info(self) -> ProviderInfo:
        hostname = urlsplit(self.configuration.request.base_url).hostname or self.name
        return ProviderInfo(
            name=self.name,
            description=self.configuration.description or self.configuration.display_name,
            domain=hostname,
            accepted_domains=self.configuration.capabilities.accepted_domains,
        )

    def _ensure_client(self) -> httpx.AsyncClient:
        request_config = self.configuration.request
        if self._client is None or self._client.is_closed:
            headers = {
                "Accept-Encoding": "identity",
                "Accept": "application/json"
                if self.configuration.adapter_kind == "json"
                else "text/html",
                "User-Agent": "CareerOS-Local/1 declarative-job-provider",
                **request_config.headers,
            }
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=request_config.timeout_seconds,
                follow_redirects=False,
                trust_env=False,
                event_hooks=provider_response_hooks(
                    self.name, max_bytes=request_config.max_response_bytes
                ),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, request: JobSearchRequest) -> httpx.Response:
        config = self.configuration.request
        variables = _template_values(request)
        path = _render_string(config.path_template, variables, path=True)
        url = f"{config.base_url}{path}"
        params = {
            key: _render_string(value, variables) for key, value in config.query_params.items()
        }
        json_body = (
            _render_json(config.json_body, variables) if config.json_body is not None else None
        )
        last_error: Exception | None = None
        for attempt in range(config.retries + 1):
            await resolve_public_destination(config.base_url)
            try:
                response = await self._ensure_client().request(
                    config.method,
                    url,
                    params=params,
                    json=json_body,
                )
                assert_bounded_provider_response(
                    response, self.name, max_bytes=config.max_response_bytes
                )
                response.raise_for_status()
                return response
            except Exception as exc:
                last_error = exc
                if attempt >= config.retries or not is_retryable_provider_http_error(exc):
                    break
                await asyncio.sleep(min(4.0, 0.5 * (2**attempt)))
        raise ProviderError(self.name, "Provider request failed") from last_error

    def _mapped_json(self, item: dict[str, Any], mapping: ProviderFieldMapping) -> str:
        value = _json_value(item, mapping.source)
        return _safe_text(value if value is not None else mapping.default)

    def _mapped_html(self, item: Any, mapping: ProviderFieldMapping) -> str:
        node = select_one(item, mapping.source)
        if node is None:
            return _safe_text(mapping.default)
        if mapping.attribute is not None:
            return _safe_text(node.attrs.get(mapping.attribute.casefold(), mapping.default))
        return text_content(node) or _safe_text(mapping.default)

    def _listing(self, fields: dict[str, str], request: JobSearchRequest) -> JobListing | None:
        identifier = fields.get("id", "")[:500]
        title = fields.get("title", "")[:500]
        if not identifier or not title:
            return None
        description = fields.get("description", "")[:20_000]
        company = fields.get("company", "")[:500]
        location = fields.get("location", "")[:500]
        country_code = fields.get("country_code", "CH")[:3].upper() or "CH"
        workload_min = _bounded_int(
            fields.get("workload_min", "100"), default=100, minimum=0, maximum=100
        )
        workload_max = _bounded_int(
            fields.get("workload_max", "100"), default=100, minimum=workload_min, maximum=100
        )
        application_url = _safe_url(
            fields.get("application_url", ""), self.configuration.request.base_url
        )
        try:
            application_email = normalize_application_email(
                fields.get("application_email", "")[:320] or None
            )
        except ValueError:
            application_email = None
        return JobListing(
            id=identifier,
            external_reference=identifier,
            source=self.name,
            title=title,
            descriptions=[
                JobDescription(
                    language_code=request.language,
                    title=title,
                    description=description,
                )
            ],
            external_url=_safe_url(fields.get("url", ""), self.configuration.request.base_url),
            company=CompanyInfo(name=company) if company else None,
            location=JobLocation(city=location, country_code=country_code) if location else None,
            employment=EmploymentDetails(workload_min=workload_min, workload_max=workload_max),
            application=(
                ApplicationChannel(email=application_email, form_url=application_url)
                if application_email or application_url
                else None
            ),
            created_at=_parse_datetime(fields.get("posted_at", "")),
            raw_data=None,
        )

    def _parse_json(
        self, response: httpx.Response, request: JobSearchRequest
    ) -> tuple[list[JobListing], int | None]:
        try:
            payload = json.loads(
                response.content,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ResponseParseError(self.name, "Provider request failed") from exc
        raw_items = _json_value(payload, self.configuration.extraction.items_path or "$")
        if not isinstance(raw_items, list) or len(raw_items) > MAX_PARSED_ITEMS:
            raise ResponseParseError(self.name, "Provider request failed")
        listings: list[JobListing] = []
        for raw_item in raw_items[: request.page_size]:
            if not isinstance(raw_item, dict):
                raise ResponseParseError(self.name, "Provider request failed")
            fields = {
                name: self._mapped_json(raw_item, mapping)
                for name, mapping in self.configuration.extraction.fields.items()
            }
            if listing := self._listing(fields, request):
                listings.append(listing)
        total_value = (
            _json_value(payload, self.configuration.extraction.total_path)
            if self.configuration.extraction.total_path
            else None
        )
        total = None
        if total_value is not None:
            if (
                isinstance(total_value, bool)
                or not isinstance(total_value, int)
                or not 0 <= total_value <= MAX_TOTAL_COUNT
            ):
                raise ResponseParseError(self.name, "Provider request failed")
            total = total_value
        return listings, total

    def _parse_html(
        self, response: httpx.Response, request: JobSearchRequest
    ) -> tuple[list[JobListing], None]:
        try:
            document = parse_html(response.text)
            items = select_all(
                document,
                self.configuration.extraction.item_selector or "",
                limit=MAX_PARSED_ITEMS + 1,
            )
        except (UnicodeDecodeError, HtmlExtractionError) as exc:
            raise ResponseParseError(self.name, "Provider request failed") from exc
        if len(items) > MAX_PARSED_ITEMS:
            raise ResponseParseError(self.name, "Provider request failed")
        listings: list[JobListing] = []
        for item in items[: request.page_size]:
            fields = {
                name: self._mapped_html(item, mapping)
                for name, mapping in self.configuration.extraction.fields.items()
            }
            if listing := self._listing(fields, request):
                listings.append(listing)
        return listings, None

    async def search(self, request: JobSearchRequest) -> JobSearchResponse:
        config = self.configuration.request
        if request.page >= config.max_pages:
            return JobSearchResponse(
                items=[],
                total_count=0,
                page=request.page,
                page_size=request.page_size,
                total_pages=config.max_pages,
                source=self.name,
                search_time_ms=0,
                request=request,
            )
        started = time.monotonic()
        response = await self._request(request)
        if self.configuration.adapter_kind == "json":
            items, declared_total = self._parse_json(response, request)
        else:
            items, declared_total = self._parse_html(response, request)
        if declared_total is not None:
            total_count = declared_total
            total_pages = min(config.max_pages, math.ceil(total_count / request.page_size))
        else:
            total_count = request.page * request.page_size + len(items)
            total_pages = request.page + 1 if len(items) < request.page_size else config.max_pages
        return JobSearchResponse(
            items=items,
            total_count=total_count,
            page=request.page,
            page_size=request.page_size,
            total_pages=max(1, total_pages),
            source=self.name,
            search_time_ms=int((time.monotonic() - started) * 1_000),
            request=request,
        )
