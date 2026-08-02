from __future__ import annotations

from typing import Any

from backend.providers.configuration.schemas import ProviderConfigurationCreate


def json_provider_payload(**overrides: Any) -> ProviderConfigurationCreate:
    payload: dict[str, Any] = {
        "key": "example_jobs",
        "display_name": "Example Jobs",
        "description": "Public engineering roles",
        "adapter_kind": "json",
        "enabled": True,
        "request": {
            "base_url": "https://jobs.example.com",
            "path_template": "/api/jobs",
            "method": "GET",
            "query_params": {
                "q": "{query}",
                "where": "{location}",
                "page": "{page}",
                "limit": "{page_size}",
            },
            "headers": {"X-API-Key": "test-provider-secret"},
            "timeout_seconds": 10,
            "max_response_bytes": 100_000,
            "max_pages": 3,
            "page_size": 20,
            "throttle_ms": 0,
            "retries": 0,
        },
        "extraction": {
            "items_path": "data.jobs",
            "total_path": "data.total",
            "item_selector": None,
            "fields": {
                "id": {"source": "id"},
                "title": {"source": "role"},
                "company": {"source": "company.name"},
                "location": {"source": "location.city"},
                "description": {"source": "description"},
                "url": {"source": "url"},
                "application_url": {"source": "apply_url"},
                "posted_at": {"source": "posted_at"},
            },
        },
        "capabilities": {
            "accepted_domains": ["it"],
            "supported_languages": ["en", "de"],
        },
    }
    payload.update(overrides)
    return ProviderConfigurationCreate.model_validate(payload)
