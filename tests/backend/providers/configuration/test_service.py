from __future__ import annotations

import pytest

from backend.providers.configuration.network_policy import UnsafeProviderDestination
from backend.providers.configuration.schemas import (
    PRESERVE_SECRET,
    REDACTED_SECRET,
    ProviderConfigurationUpdate,
    ProviderDocument,
)
from backend.providers.configuration.service import (
    ProviderConfigurationError,
    ProviderConfigurationService,
)
from tests.backend.providers.configuration.helpers import json_provider_payload


def test_crud_redacts_secrets_and_requires_expected_revision(db_session, test_user) -> None:
    service = ProviderConfigurationService(db_session)
    created = service.create(test_user.id, json_provider_payload())

    assert created.revision == 1
    assert created.has_secrets is True
    assert created.request.headers["X-API-Key"] == REDACTED_SECRET
    stored = service.get_row(test_user.id, created.id)
    assert stored.request_config["headers"]["X-API-Key"] == "test-provider-secret"

    update_data = created.model_dump(
        exclude={
            "id",
            "revision",
            "native_adapter_id",
            "source_pack_id",
            "source_pack_version",
            "has_secrets",
            "created_at",
            "updated_at",
        }
    )
    update_data["display_name"] = "Example Careers"
    update_data["request"]["headers"]["X-API-Key"] = PRESERVE_SECRET
    updated = service.update(
        test_user.id,
        created.id,
        ProviderConfigurationUpdate.model_validate({**update_data, "expected_revision": 1}),
    )

    assert updated.revision == 2
    assert updated.display_name == "Example Careers"
    assert service.get_row(test_user.id, created.id).request_config["headers"]["X-API-Key"] == (
        "test-provider-secret"
    )

    with pytest.raises(ProviderConfigurationError, match="reread") as conflict:
        service.update(
            test_user.id,
            created.id,
            ProviderConfigurationUpdate.model_validate(
                {**update_data, "expected_revision": 1}
            ),
        )
    assert conflict.value.code == "revision_conflict"

    with pytest.raises(ProviderConfigurationError) as delete_conflict:
        service.delete(test_user.id, created.id, expected_revision=1)
    assert delete_conflict.value.code == "revision_conflict"

    service.delete(test_user.id, created.id, expected_revision=2)
    with pytest.raises(ProviderConfigurationError) as missing:
        service.get(test_user.id, created.id)
    assert missing.value.code == "provider_not_found"


def test_new_provider_cannot_use_secret_preservation_marker(db_session, test_user) -> None:
    payload = json_provider_payload()
    request = payload.request.model_copy(
        update={"headers": {"Authorization": PRESERVE_SECRET}}
    )

    with pytest.raises(ProviderConfigurationError) as error:
        ProviderConfigurationService(db_session).create(
            test_user.id,
            payload.model_copy(update={"request": request}),
        )

    assert error.value.code == "invalid_secret_sentinel"


def test_all_custom_headers_are_redacted_even_with_innocuous_names(db_session, test_user) -> None:
    payload = json_provider_payload()
    request = payload.request.model_copy(update={"headers": {"X-Custom": "opaque-value"}})

    created = ProviderConfigurationService(db_session).create(
        test_user.id,
        payload.model_copy(update={"request": request}),
    )

    assert created.request.headers == {"X-Custom": REDACTED_SECRET}


@pytest.mark.parametrize(
    "base_url",
    [
        "https://127.0.0.1",
        "https://169.254.169.254",
        "https://service.local",
        "https://localhost",
    ],
)
def test_validation_rejects_private_destinations(db_session, base_url) -> None:
    payload = json_provider_payload()
    request = payload.request.model_copy(update={"base_url": base_url})

    with pytest.raises(UnsafeProviderDestination):
        ProviderConfigurationService(db_session).validate(
            payload.model_copy(update={"request": request})
        )


def test_json_paths_are_strictly_validated() -> None:
    payload = json_provider_payload().model_dump()
    payload["extraction"]["items_path"] = "data.jobs[0]"

    with pytest.raises(ValueError, match="dotted object paths"):
        json_provider_payload(extraction=payload["extraction"])


def test_import_rejects_unknown_native_adapter_without_partial_rows(
    db_session, test_user
) -> None:
    document = ProviderDocument.model_validate(
        {
            "kind": "provider",
            "format_version": 1,
            "provider": {
                "kind": "native",
                "adapter_id": "unreviewed_adapter",
                "key": "unreviewed_adapter",
                "display_name": "Unreviewed adapter",
                "capabilities": {
                    "accepted_domains": ["*"],
                    "supported_languages": ["en"],
                },
            },
        }
    )
    service = ProviderConfigurationService(db_session)

    with pytest.raises(ValueError, match="unknown native adapter"):
        service.import_document(test_user.id, document)

    assert service.list(test_user.id) == []
