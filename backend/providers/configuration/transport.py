"""Bounded HTTP transport for explicitly consented declarative providers."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import quote

import httpx

from backend.providers.configuration.network_policy import resolve_public_destination
from backend.providers.configuration.schemas import ProviderConfigurationInput
from backend.providers.jobs.exceptions import ProviderError
from backend.providers.jobs.http_policy import (
    assert_bounded_provider_response,
    is_retryable_provider_http_error,
    provider_response_hooks,
)
from backend.providers.jobs.models import JobSearchRequest

_TEMPLATE_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


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


class DeclarativeTransport:
    def __init__(self, configuration: ProviderConfigurationInput) -> None:
        if not configuration.enabled:
            raise ValueError("A disabled declarative provider cannot execute")
        self.configuration = configuration
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return self.configuration.key

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
            addresses = await resolve_public_destination(config.base_url)
            logical_url = httpx.URL(url)
            # Connect to the validated numeric address. Keeping the original hostname in
            # Host and TLS SNI preserves certificate verification without a second DNS
            # lookup that could rebind to a private destination after validation.
            pinned_url = logical_url.copy_with(host=addresses[attempt % len(addresses)])
            try:
                response = await self._ensure_client().request(
                    config.method,
                    pinned_url,
                    params=params,
                    json=json_body,
                    headers={"Host": logical_url.netloc.decode("ascii")},
                    extensions={"sni_hostname": logical_url.host},
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
