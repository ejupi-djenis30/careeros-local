"""Closed factory for reviewed native adapters activated by imported rows."""

from __future__ import annotations

import inspect
from typing import Any

from backend.providers.configuration.schemas import ProviderCapabilitiesConfig
from backend.providers.jobs.base import JobProvider
from backend.providers.jobs.models import (
    JobSearchRequest,
    JobSearchResponse,
    ProviderCapabilities,
    ProviderInfo,
)

NATIVE_ADAPTER_IDS = frozenset({"job_room", "swissdevjobs", "adecco"})


class NativeAdapterError(ValueError):
    """A provider document referenced no reviewed application adapter."""


def validate_native_adapter_id(adapter_id: str) -> str:
    if adapter_id not in NATIVE_ADAPTER_IDS:
        raise NativeAdapterError("Provider document references an unknown native adapter")
    return adapter_id


def _instantiate_native_adapter(adapter_id: str) -> JobProvider:
    """Instantiate through explicit branches; never load a document-supplied module or path."""

    validate_native_adapter_id(adapter_id)
    if adapter_id == "job_room":
        from backend.providers.jobs.jobroom.client import JobRoomProvider

        return JobRoomProvider()
    if adapter_id == "swissdevjobs":
        from backend.providers.jobs.swissdevjobs.client import SwissDevJobsProvider

        return SwissDevJobsProvider()
    if adapter_id == "adecco":
        from backend.providers.jobs.adecco.client import AdeccoProvider

        return AdeccoProvider()
    raise NativeAdapterError("Provider document references an unavailable native adapter")


class ImportedNativeJobProvider(JobProvider):
    """Apply imported metadata and capabilities to a reviewed native implementation."""

    def __init__(
        self,
        *,
        adapter_id: str,
        key: str,
        display_name: str,
        description: str,
        capabilities: ProviderCapabilitiesConfig,
    ) -> None:
        if key != adapter_id:
            raise NativeAdapterError("Native provider key does not match its adapter")
        self._key = key
        self._display_name = display_name
        self._description = description
        self._configured_capabilities = capabilities
        self._inner = _instantiate_native_adapter(adapter_id)

    @property
    def name(self) -> str:
        return self._key

    @property
    def throttle_delay(self) -> float:
        return self._inner.throttle_delay

    @property
    def capabilities(self) -> ProviderCapabilities:
        inner = getattr(self._inner, "capabilities", ProviderCapabilities())
        return inner.model_copy(
            update={"supported_languages": self._configured_capabilities.supported_languages}
        )

    def get_provider_info(self) -> ProviderInfo:
        inner = self._inner.get_provider_info()
        return ProviderInfo(
            name=self._key,
            description=self._description or self._display_name,
            domain=inner.domain,
            accepted_domains=self._configured_capabilities.accepted_domains,
        )

    async def search(self, request: JobSearchRequest) -> JobSearchResponse:
        result = await self._inner.search(request)
        items = [item.model_copy(update={"source": self._key}) for item in result.items]
        return result.model_copy(update={"source": self._key, "items": items})

    async def close(self) -> None:
        closer = getattr(self._inner, "close", None)
        if closer is None:
            return
        result: Any = closer()
        if inspect.isawaitable(result):
            await result


def create_imported_native_provider(
    *,
    adapter_id: str,
    key: str,
    display_name: str,
    description: str,
    capabilities: ProviderCapabilitiesConfig,
) -> ImportedNativeJobProvider:
    return ImportedNativeJobProvider(
        adapter_id=adapter_id,
        key=key,
        display_name=display_name,
        description=description,
        capabilities=capabilities,
    )
