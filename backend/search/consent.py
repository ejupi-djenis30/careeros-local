from __future__ import annotations

from collections.abc import Iterable

from backend.providers.configuration.schemas import ProviderConfigurationView

LOCAL_JOB_SOURCE = "local_db"


def consent_audit_record(
    configured_names: set[str], enabled_names: set[str]
) -> dict[str, list[str]]:
    """Return a content-free diagnostic record containing source identifiers only."""
    return {
        "enabled": sorted(enabled_names),
        "disabled": sorted(configured_names - enabled_names),
    }


def public_job_source_catalog(
    installed: Iterable[ProviderConfigurationView] = (),
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = [
        {
            "key": LOCAL_JOB_SOURCE,
            "label": "Archivio locale",
            "description": "Annunci già presenti nel Career Vault; nessun accesso di rete",
            "network": False,
            "available": True,
            "consented": True,
        }
    ]
    result.extend(
        {
            "key": provider.key,
            "label": provider.display_name,
            "description": provider.description,
            "network": True,
            "available": True,
            "consented": provider.enabled,
        }
        for provider in installed
    )
    return result
