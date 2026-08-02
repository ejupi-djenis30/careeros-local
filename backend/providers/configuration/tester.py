"""One-request redacted provider diagnostics shared by desktop and MCP."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.providers.configuration.client import DeclarativeJobProvider
from backend.providers.configuration.native import create_imported_native_provider
from backend.providers.configuration.schemas import (
    ProviderCapabilitiesConfig,
    ProviderTestRequest,
    ProviderTestView,
)
from backend.providers.configuration.service import (
    ProviderConfigurationService,
    materialize_configuration,
)
from backend.providers.jobs.models import JobSearchRequest


async def test_provider_configuration(
    db: Session,
    *,
    user_id: int,
    configuration_id: str,
    request: ProviderTestRequest,
) -> ProviderTestView:
    row = ProviderConfigurationService(db).get_row(user_id, configuration_id)
    provider: Any
    if row.adapter_kind == "native":
        provider = create_imported_native_provider(
            adapter_id=row.native_adapter_id or "",
            key=row.key,
            display_name=row.display_name,
            description=row.description,
            capabilities=ProviderCapabilitiesConfig.model_validate(row.capabilities_config),
        )
        page_size = min(5, provider.capabilities.max_page_size)
        provider_key = row.key
    else:
        configuration = materialize_configuration(row)
        provider = DeclarativeJobProvider(configuration.model_copy(update={"enabled": True}))
        page_size = min(5, configuration.request.page_size)
        provider_key = configuration.key
    try:
        result = await provider.search(
            JobSearchRequest(
                query=request.query,
                location=request.location,
                language=request.language,
                page=0,
                page_size=page_size,
            )
        )
    finally:
        await provider.close()
    sample = [
        {
            "id": item.id,
            "title": item.title,
            "company": item.company.name if item.company else None,
            "location": item.location.city if item.location else None,
            "url": item.external_url,
        }
        for item in result.items[:5]
    ]
    return ProviderTestView(
        provider_key=provider_key,
        returned_count=len(sample),
        sample=sample,
        diagnostics=[],
    )
