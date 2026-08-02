def _profile(consents: dict[str, bool]) -> dict:
    return {
        "expected_revision": 0,
        "display_name": "Local Candidate",
        "preferences": {"job_source_consents": consents},
        "facts": [],
        "goals": [],
    }


def test_job_source_api_is_deny_by_default(client, auth_headers) -> None:
    response = client.get("/api/v1/search/sources", headers=auth_headers)

    assert response.status_code == 200
    sources = {item["key"]: item for item in response.json()}
    assert list(sources) == ["local_db"]
    assert sources["local_db"]["consented"] is True


def test_legacy_profile_consent_cannot_install_or_enable_a_provider(client, auth_headers) -> None:
    saved = client.put(
        "/api/v1/career-profile",
        headers=auth_headers,
        json=_profile({"job_room": True, "swissdevjobs": False}),
    )
    assert saved.status_code == 200, saved.text

    response = client.get("/api/v1/search/sources", headers=auth_headers)
    sources = {item["key"]: item for item in response.json()}

    assert list(sources) == ["local_db"]


def test_job_source_api_reflects_imported_provider_revision_state(client, auth_headers) -> None:
    imported = client.post(
        "/api/v1/job-providers/packs/careeros.switzerland.core/import",
        json={"activate": False},
        headers=auth_headers,
    )
    assert imported.status_code == 201, imported.text
    providers = imported.json()["imported"]

    disabled_sources = {
        item["key"]: item
        for item in client.get("/api/v1/search/sources", headers=auth_headers).json()
    }
    assert disabled_sources["job_room"]["consented"] is False

    job_room = providers[0]
    enabled = client.patch(
        f"/api/v1/job-providers/{job_room['id']}/state",
        json={"expected_revision": 1, "enabled": True},
        headers=auth_headers,
    )
    assert enabled.status_code == 200, enabled.text

    enabled_sources = {
        item["key"]: item
        for item in client.get("/api/v1/search/sources", headers=auth_headers).json()
    }
    assert enabled_sources["job_room"]["consented"] is True
    assert enabled_sources["swissdevjobs"]["consented"] is False


def test_unknown_job_source_consent_is_rejected(client, auth_headers) -> None:
    response = client.put(
        "/api/v1/career-profile",
        headers=auth_headers,
        json=_profile({"unknown_source": True}),
    )

    assert response.status_code == 422
