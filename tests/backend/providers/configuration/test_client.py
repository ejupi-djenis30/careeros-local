from __future__ import annotations

import socket

import httpx
import pytest

from backend.providers.configuration.client import DeclarativeJobProvider
from backend.providers.configuration.network_policy import (
    UnsafeProviderDestination,
    resolve_public_destination,
)
from backend.providers.configuration.schemas import ProviderConfigurationCreate
from backend.providers.jobs.exceptions import ResponseParseError
from backend.providers.jobs.models import JobSearchRequest
from tests.backend.providers.configuration.helpers import json_provider_payload


async def _public_destination(_base_url: str) -> tuple[str, ...]:
    return ("203.0.113.10",)


@pytest.mark.asyncio
async def test_json_adapter_renders_request_and_maps_canonical_jobs(monkeypatch) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            request=request,
            json={
                "data": {
                    "total": 1,
                    "jobs": [
                        {
                            "id": "job-1",
                            "role": "Platform Engineer",
                            "company": {"name": "Example AG"},
                            "location": {"city": "Zürich"},
                            "description": "Build reliable local systems",
                            "url": "/roles/job-1",
                            "apply_url": "https://apply.example.com/job-1",
                            "posted_at": "2026-08-01T10:00:00Z",
                        }
                    ],
                }
            },
        )

    monkeypatch.setattr(
        "backend.providers.configuration.client.resolve_public_destination",
        _public_destination,
    )
    raw_configuration = json_provider_payload().model_dump()
    raw_configuration["request"]["query_params"]["page"] = "{page_one_based}"
    provider = DeclarativeJobProvider(ProviderConfigurationCreate.model_validate(raw_configuration))
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await provider.search(
            JobSearchRequest(
                query="platform engineer",
                location="Zürich",
                language="de",
                page=0,
                page_size=10,
            )
        )
    finally:
        await provider.close()

    assert len(seen) == 1
    assert seen[0].url.path == "/api/jobs"
    assert seen[0].url.params["q"] == "platform engineer"
    assert seen[0].url.params["where"] == "Zürich"
    assert seen[0].url.params["page"] == "1"
    assert result.total_count == 1
    assert result.total_pages == 1
    assert result.items[0].title == "Platform Engineer"
    assert result.items[0].company.name == "Example AG"
    assert result.items[0].external_url == "https://jobs.example.com/roles/job-1"
    assert result.items[0].application.form_url == "https://apply.example.com/job-1"
    assert result.items[0].raw_data is None


@pytest.mark.asyncio
async def test_html_adapter_uses_bounded_selector_subset(monkeypatch) -> None:
    raw = json_provider_payload().model_dump()
    raw.update({"key": "html_jobs", "adapter_kind": "html"})
    raw["extraction"] = {
        "items_path": None,
        "total_path": None,
        "item_selector": "article.job-card",
        "fields": {
            "id": {"source": "a.apply", "attribute": "href"},
            "title": {"source": "h2.title"},
            "company": {"source": ".company"},
            "location": {"source": ".location"},
            "url": {"source": "a.apply", "attribute": "href"},
        },
    }
    configuration = ProviderConfigurationCreate.model_validate(raw)
    html = b"""
        <main><article class="job-card">
          <h2 class="title">Security Engineer</h2>
          <span class="company">Example GmbH</span>
          <span class="location">Bern</span>
          <a class="apply" href="/jobs/security">Apply</a>
        </article></main>
    """

    monkeypatch.setattr(
        "backend.providers.configuration.client.resolve_public_destination",
        _public_destination,
    )
    provider = DeclarativeJobProvider(configuration)
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, content=html)
        )
    )
    try:
        result = await provider.search(JobSearchRequest(page_size=5))
    finally:
        await provider.close()

    assert [item.title for item in result.items] == ["Security Engineer"]
    assert result.items[0].id == "/jobs/security"
    assert result.items[0].external_url == "https://jobs.example.com/jobs/security"


@pytest.mark.asyncio
async def test_json_adapter_rejects_nonfinite_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.providers.configuration.client.resolve_public_destination",
        _public_destination,
    )
    provider = DeclarativeJobProvider(json_provider_payload())
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                content=b'{"data":{"total":1,"jobs":[NaN]}}',
            )
        )
    )
    try:
        with pytest.raises(ResponseParseError):
            await provider.search(JobSearchRequest())
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_json_adapter_drops_untrusted_private_links_and_invalid_email(monkeypatch) -> None:
    raw = json_provider_payload().model_dump()
    raw["extraction"]["fields"]["application_email"] = {"source": "apply_email"}
    configuration = ProviderConfigurationCreate.model_validate(raw)
    monkeypatch.setattr(
        "backend.providers.configuration.client.resolve_public_destination",
        _public_destination,
    )
    provider = DeclarativeJobProvider(configuration)
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                json={
                    "data": {
                        "total": 1,
                        "jobs": [
                            {
                                "id": "unsafe-links",
                                "role": "Security Engineer",
                                "url": "https://127.0.0.1/internal",
                                "apply_url": "https://localhost/apply",
                                "apply_email": "not an email",
                            }
                        ],
                    }
                },
            )
        )
    )
    try:
        result = await provider.search(JobSearchRequest())
    finally:
        await provider.close()

    assert result.items[0].external_url is None
    assert result.items[0].application is None


@pytest.mark.asyncio
async def test_dns_rebinding_guard_rejects_any_private_answer(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ],
    )

    with pytest.raises(UnsafeProviderDestination, match="outside the public network"):
        await resolve_public_destination("https://jobs.example.com")
