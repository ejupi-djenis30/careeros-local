"""Build a fresh user-scoped provider registry for each search run."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from sqlalchemy.orm import Session

from backend.providers.configuration.client import DeclarativeJobProvider
from backend.providers.configuration.native import (
    NativeAdapterError,
    create_imported_native_provider,
)
from backend.providers.configuration.schemas import ProviderCapabilitiesConfig
from backend.providers.configuration.service import (
    ProviderConfigurationError,
    ProviderConfigurationService,
    materialize_configuration,
)

logger = logging.getLogger(__name__)


def configured_provider_registry(
    db: Session,
    user_id: int,
    *,
    builtins: Mapping[str, Any],
) -> tuple[dict[str, Any], set[str]]:
    """Return local sources plus enabled, explicitly installed provider adapters."""

    providers = dict(builtins)
    custom_names: set[str] = set()
    invalid_count = 0
    for row in ProviderConfigurationService(db).rows(user_id, enabled_only=True):
        try:
            if row.adapter_kind == "native":
                provider = create_imported_native_provider(
                    adapter_id=row.native_adapter_id or "",
                    key=row.key,
                    display_name=row.display_name,
                    description=row.description,
                    capabilities=ProviderCapabilitiesConfig.model_validate(
                        row.capabilities_config
                    ),
                )
                providers[row.key] = provider
                custom_names.add(row.key)
            else:
                configuration = materialize_configuration(row)
                providers[configuration.key] = DeclarativeJobProvider(configuration)
                custom_names.add(configuration.key)
        except (ProviderConfigurationError, NativeAdapterError, ValueError):
            invalid_count += 1
    if invalid_count:
        logger.warning(
            "Skipped invalid user provider configurations count=%d",
            invalid_count,
        )
    return providers, custom_names
