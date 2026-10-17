"""Provider credentials remain bound to their explicitly configured HTTP origin."""

import httpx
import pytest

from backend.providers.configuration.client import DeclarativeJobProvider
from backend.providers.configuration.schemas import (
    PRESERVE_SECRET,
    REDACTED_SECRET,
    ProviderConfigurationUpdate,
)
from backend.providers.configuration.service import (
    ProviderConfigurationError,
    ProviderConfigurationService,
    _provider_origin,
    materialize_configuration,
)
from backend.providers.jobs.models import JobSearchRequest
from tests.backend.providers.configuration.helpers import json_provider_payload


def test_api_rejects_cross_origin_secret_preservation_without_disclosing_or_changing_credentials(client, auth_headers):
    payload = json_provider_payload().model_dump(mode="json")
    created = client.post("/api/v1/job-providers", headers=auth_headers, json=payload)
    assert created.status_code == 201
    provider_id = created.json()["id"]
    payload["expected_revision"] = 1
    payload["request"].update(base_url="https://different-provider.example.org", headers={"X-API-Key": PRESERVE_SECRET})
    rejected = client.put(f"/api/v1/job-providers/{provider_id}", headers=auth_headers, json=payload)
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "secret_origin_changed"
    assert rejected.headers["cache-control"].startswith("no-store")
    assert "test-provider-secret" not in rejected.text
    assert "different-provider.example.org" not in rejected.text
    after = client.get(f"/api/v1/job-providers/{provider_id}", headers=auth_headers).json()
    assert after["revision"] == 1
    assert after["request"]["base_url"] == "https://jobs.example.com"
    assert after["request"]["headers"] == {"X-API-Key": REDACTED_SECRET}


@pytest.mark.parametrize("marker", [PRESERVE_SECRET, REDACTED_SECRET])
@pytest.mark.parametrize("destination", ["https://different-provider.example.org", "https://93.184.216.34"])
def test_origin_change_cannot_preserve_previously_configured_headers(db_session, test_user, marker, destination):
    service = ProviderConfigurationService(db_session)
    created = service.create(test_user.id, json_provider_payload())
    update = json_provider_payload().model_dump()
    update["expected_revision"] = 1
    update["request"].update(base_url=destination, headers={"X-API-Key": marker})
    with pytest.raises(ProviderConfigurationError) as error:
        service.update(test_user.id, created.id, ProviderConfigurationUpdate.model_validate(update))
    assert error.value.code == "secret_origin_changed"
    assert "test-provider-secret" not in str(error.value)
    assert destination not in str(error.value)
    row = service.get_row(test_user.id, created.id)
    assert row.revision == 1
    assert row.request_config["base_url"] == "https://jobs.example.com"
    assert row.request_config["headers"] == {"X-API-Key": "test-provider-secret"}


def test_origin_change_requires_explicit_header_removal_instead_of_omitted_field(db_session, test_user):
    service = ProviderConfigurationService(db_session)
    created = service.create(test_user.id, json_provider_payload())
    update = json_provider_payload().model_dump()
    update["expected_revision"] = 1
    update["request"]["base_url"] = "https://different-provider.example.org"
    update["request"].pop("headers")
    with pytest.raises(ProviderConfigurationError) as error:
        service.update(test_user.id, created.id, ProviderConfigurationUpdate.model_validate(update))
    assert error.value.code == "secret_origin_changed"
    assert service.get(test_user.id, created.id).revision == 1


@pytest.mark.parametrize("marker", [PRESERVE_SECRET, REDACTED_SECRET])
def test_normalized_same_origin_keeps_explicit_secret_preservation(db_session, test_user, marker):
    service = ProviderConfigurationService(db_session)
    created = service.create(test_user.id, json_provider_payload())
    update = json_provider_payload().model_dump()
    update["expected_revision"] = 1
    update["request"].update(base_url="https://JOBS.EXAMPLE.COM:443/", headers={"X-API-Key": marker})
    saved = service.update(test_user.id, created.id, ProviderConfigurationUpdate.model_validate(update))
    assert saved.revision == 2
    assert saved.request.headers["X-API-Key"] == REDACTED_SECRET
    assert service.get_row(test_user.id, created.id).request_config["headers"]["X-API-Key"] == "test-provider-secret"


@pytest.mark.parametrize("candidate, same", [
    ("https://JOBS.EXAMPLE.COM:443/", True),
    ("http://jobs.example.com", False),
    ("https://jobs.example.com:8443", False),
    ("https://jobs.example.com.", False),
    ("https://different-provider.example.org", False),
])
def test_origin_identity_includes_scheme_canonical_host_and_effective_port(candidate, same):
    assert (_provider_origin("https://jobs.example.com") == _provider_origin(candidate)) is same


def test_idna_origin_identity_matches_actual_http_client_without_transitional_aliases():
    assert _provider_origin("https://bücher.example") == _provider_origin("https://xn--bcher-kva.example")
    assert _provider_origin("https://faß.example") != _provider_origin("https://fass.example")


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", [{}, {"X-API-Key": "new-origin-explicit-secret"}, {"x-api-key": "new-origin-explicit-secret"}])
async def test_changed_origin_request_only_sends_explicit_new_headers(db_session, test_user, monkeypatch, replacement):
    service = ProviderConfigurationService(db_session)
    created = service.create(test_user.id, json_provider_payload())
    update = json_provider_payload().model_dump()
    update["expected_revision"] = 1
    update["request"].update(base_url="https://different-provider.example.org", headers=replacement)
    saved = service.update(test_user.id, created.id, ProviderConfigurationUpdate.model_validate(update))
    assert saved.revision == 2

    async def resolved(_base_url):
        return ("93.184.216.34",)

    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"data": {"total": 0, "jobs": []}})

    monkeypatch.setattr("backend.providers.configuration.transport.resolve_public_destination", resolved)
    original = httpx.AsyncClient
    monkeypatch.setattr("backend.providers.configuration.transport.httpx.AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    provider = DeclarativeJobProvider(materialize_configuration(service.get_row(test_user.id, created.id)))
    try:
        await provider.search(JobSearchRequest())
    finally:
        await provider.close()
    assert len(seen) == 1
    assert seen[0].headers["Host"] == "different-provider.example.org"
    assert "test-provider-secret" not in str(seen[0].headers)
    assert seen[0].headers.get("X-API-Key") == next(iter(replacement.values()), None)
