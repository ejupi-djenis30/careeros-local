from __future__ import annotations

from backend.providers.configuration.client import DeclarativeJobProvider
from backend.providers.configuration.packs import bundled_provider_pack
from backend.providers.configuration.registry import configured_provider_registry
from backend.providers.configuration.schemas import ProviderStateUpdate
from backend.providers.configuration.service import ProviderConfigurationService
from tests.backend.providers.configuration.helpers import json_provider_payload


def test_registry_adds_only_enabled_owned_custom_providers(db_session, test_user) -> None:
    service = ProviderConfigurationService(db_session)
    enabled = json_provider_payload()
    disabled = json_provider_payload(
        key="disabled_jobs",
        display_name="Disabled Jobs",
        enabled=False,
    )
    service.create(test_user.id, enabled)
    service.create(test_user.id, disabled)
    builtin = object()

    providers, installed_names = configured_provider_registry(
        db_session,
        test_user.id,
        builtins={"local_db": builtin},
    )

    assert installed_names == {"example_jobs"}
    assert set(providers) == {"local_db", "example_jobs"}
    assert providers["local_db"] is builtin
    assert isinstance(providers["example_jobs"], DeclarativeJobProvider)
    assert "disabled_jobs" not in providers


def test_native_adapters_are_absent_until_imported_and_enabled(
    db_session, test_user, monkeypatch
) -> None:
    service = ProviderConfigurationService(db_session)
    local = object()

    initial, _ = configured_provider_registry(
        db_session,
        test_user.id,
        builtins={"local_db": local},
    )
    assert initial == {"local_db": local}

    result = service.import_document(
        test_user.id,
        bundled_provider_pack("careeros.switzerland.core"),
        activate=False,
    )
    disabled, _ = configured_provider_registry(
        db_session,
        test_user.id,
        builtins={"local_db": local},
    )
    assert disabled == {"local_db": local}

    sentinel = object()
    monkeypatch.setattr(
        "backend.providers.configuration.registry.create_imported_native_provider",
        lambda **_kwargs: sentinel,
    )
    service.set_enabled(
        test_user.id,
        result.imported[0].id,
        ProviderStateUpdate(expected_revision=1, enabled=True),
    )
    enabled, installed_names = configured_provider_registry(
        db_session,
        test_user.id,
        builtins={"local_db": local},
    )

    assert enabled == {"local_db": local, "job_room": sentinel}
    assert installed_names == {"job_room"}
