from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from backend.core.config import settings
from backend.models import User
from backend.providers.configuration.models import JobProviderConfiguration
from backend.providers.configuration.packs import ProviderPackError, bundled_provider_pack
from backend.providers.configuration.registry import configured_provider_registry
from backend.providers.configuration.schemas import (
    ProviderConfigurationUpdate,
    ProviderStateUpdate,
    ProviderTestRequest,
)
from backend.providers.configuration.service import (
    ProviderConfigurationError,
    ProviderConfigurationService,
)
from backend.services.search_service import SearchService
from tests.backend.providers.configuration.helpers import json_provider_payload


@pytest.mark.parametrize("consent", [None, False, 1, "true"])
def test_test_request_requires_literal_explicit_network_consent(consent):
    payload = {} if consent is None else {"allow_network": consent}
    with pytest.raises(ValueError):
        ProviderTestRequest.model_validate(payload)


def test_provider_test_consent_is_per_request_without_enabling_search(client, auth_headers, monkeypatch):
    payload = json_provider_payload(enabled=False).model_dump(mode="json")
    created = client.post("/api/v1/job-providers", json=payload, headers=auth_headers).json()
    search = AsyncMock(return_value=type("Result", (), {"items": []})())
    close = AsyncMock()
    monkeypatch.setattr("backend.providers.configuration.tester.DeclarativeJobProvider.search", search)
    monkeypatch.setattr("backend.providers.configuration.tester.DeclarativeJobProvider.close", close)
    monkeypatch.setattr(settings, "OFFLINE_MODE", False)
    url = f"/api/v1/job-providers/{created['id']}/test"
    denied = client.post(url, json={}, headers=auth_headers)
    assert denied.status_code == 422
    search.assert_not_called()
    allowed = client.post(url, json={"allow_network": True}, headers=auth_headers)
    assert allowed.status_code == 200, allowed.text
    search.assert_awaited_once()
    close.assert_awaited_once()
    after = client.get(f"/api/v1/job-providers/{created['id']}", headers=auth_headers).json()
    assert after["enabled"] is False
    assert after["revision"] == 1


def test_provider_test_offline_mode_never_contacts_network(client, auth_headers, monkeypatch):
    created = client.post("/api/v1/job-providers", json=json_provider_payload().model_dump(mode="json"), headers=auth_headers).json()
    search = AsyncMock()
    monkeypatch.setattr("backend.providers.configuration.tester.DeclarativeJobProvider.search", search)
    monkeypatch.setattr(settings, "OFFLINE_MODE", True)
    response = client.post(f"/api/v1/job-providers/{created['id']}/test", json={"allow_network": True}, headers=auth_headers)
    assert response.status_code == 503
    search.assert_not_called()


def test_existing_agent_read_grant_cannot_manage_provider_installations(client, auth_headers):
    issued = client.post(
        "/api/v1/automation/grants",
        headers=auth_headers,
        json={"label": "Synthetic read client", "scopes": ["system:read", "applications:read"], "lifetime_days": 1, "password": "Globalpass1"},
    )
    assert issued.status_code == 201, issued.text
    grant_headers = {"Authorization": f"Bearer {issued.json()['token']}"}
    denied = client.post("/api/v1/job-providers", json=json_provider_payload().model_dump(mode="json"), headers=grant_headers)
    assert denied.status_code == 401
    assert client.get("/api/v1/job-providers", headers=grant_headers).status_code == 401
    assert client.get("/api/v1/job-providers", headers=auth_headers).json()["installed"] == []


def test_corrupt_bundled_pack_is_an_explicit_catalog_failure(client, auth_headers, monkeypatch):
    def corrupt():
        raise ProviderPackError("synthetic failure")

    monkeypatch.setattr("backend.api.routes.job_providers.bundled_provider_pack_summaries", corrupt)
    response = client.get("/api/v1/job-providers", headers=auth_headers)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_pack_unavailable"
    assert response.headers["cache-control"].startswith("no-store")


def test_provider_crud_and_registry_cannot_cross_accounts(db_session, test_user):
    other = User(username="other-provider-owner", hashed_password="unused")
    db_session.add(other)
    db_session.commit()
    service = ProviderConfigurationService(db_session)
    created = service.create(test_user.id, json_provider_payload())
    assert service.list(other.id) == []
    update = ProviderConfigurationUpdate.model_validate({**json_provider_payload().model_dump(), "expected_revision": 1})
    for action in (
        lambda: service.get(other.id, created.id),
        lambda: service.update(other.id, created.id, update),
        lambda: service.set_enabled(other.id, created.id, ProviderStateUpdate(expected_revision=1, enabled=False)),
        lambda: service.delete(other.id, created.id, expected_revision=1),
    ):
        with pytest.raises(ProviderConfigurationError) as error:
            action()
        assert error.value.code == "provider_not_found"
    registry, _ = configured_provider_registry(db_session, other.id, builtins={})
    assert registry == {}
    assert service.get(test_user.id, created.id).revision == 1


def test_pack_insert_failure_rolls_back_every_installation(db_session, test_user, monkeypatch):
    service = ProviderConfigurationService(db_session)
    commit = db_session.commit

    def fail_commit():
        db_session.flush()
        raise IntegrityError("synthetic", {}, Exception())

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(ProviderConfigurationError):
        service.import_document(test_user.id, bundled_provider_pack("careeros.switzerland.core"), activate=True)
    monkeypatch.setattr(db_session, "commit", commit)
    assert db_session.query(JobProviderConfiguration).count() == 0


def test_invalid_enabled_record_fails_closed_instead_of_disappearing(db_session, test_user):
    service = ProviderConfigurationService(db_session)
    created = service.create(test_user.id, json_provider_payload())
    row = service.get_row(test_user.id, created.id)
    row.request_config = {**row.request_config, "base_url": "https://127.0.0.1"}
    db_session.commit()
    with pytest.raises(ProviderConfigurationError) as error:
        configured_provider_registry(db_session, test_user.id, builtins={})
    assert error.value.code == "invalid_stored_configuration"


def test_search_bootstrap_never_constructs_a_network_adapter(db_session, monkeypatch):
    def forbidden():
        raise AssertionError("network adapter constructed before installation and consent")

    for name in ("JobRoomProvider", "SwissDevJobsProvider", "AdeccoProvider"):
        monkeypatch.setattr(f"backend.search.orchestrator.{name}", forbidden)
    service = SearchService(db=db_session)
    assert set(service.providers) == {"local_db"}


def test_injected_network_adapters_do_not_acquire_installation_consent(db_session, test_user):
    local = object()
    registry, _ = configured_provider_registry(
        db_session, test_user.id, builtins={"local_db": local, "job_room": object()}
    )
    assert registry == {"local_db": local}


@pytest.mark.parametrize("number", [float("nan"), float("inf"), -float("inf")])
def test_request_body_rejects_nonfinite_numbers(number):
    raw = json_provider_payload().model_dump()
    raw["request"]["json_body"] = {"invalid": number}
    with pytest.raises(ValueError):
        type(json_provider_payload()).model_validate(raw)
