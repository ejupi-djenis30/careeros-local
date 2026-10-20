"""Build a fresh user-scoped provider registry for each search run."""

from __future__ import annotations

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


def configured_provider_registry(
    db: Session,
    user_id: int,
    *,
    builtins: Mapping[str, Any],
) -> tuple[dict[str, Any], set[str]]:
    """Return local sources plus enabled, explicitly installed provider adapters."""

    providers = {name: provider for name, provider in builtins.items() if name == "local_db"}
    custom_names: set[str] = set()
    for row in ProviderConfigurationService(db).rows(user_id, enabled_only=True):
        try:
            if row.adapter_kind == "native":
                provider = create_imported_native_provider(
                    adapter_id=row.native_adapter_id or "",
                    key=row.key,
                    display_name=row.display_name,
                    description=row.description,
                    capabilities=ProviderCapabilitiesConfig.model_validate(row.capabilities_config),
                )
                providers[row.key] = provider
                custom_names.add(row.key)
            else:
                configuration = materialize_configuration(row)
                providers[configuration.key] = DeclarativeJobProvider(configuration)
                custom_names.add(configuration.key)
        except (ProviderConfigurationError, NativeAdapterError, ValueError) as exc:
            raise ProviderConfigurationError(
                "invalid_stored_configuration", "Enabled provider configuration is invalid"
            ) from exc
    return providers, custom_names
