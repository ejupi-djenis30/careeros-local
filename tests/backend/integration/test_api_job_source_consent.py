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
    assert sources["local_db"]["consented"] is True
    assert all(
        item["consented"] is False for item in sources.values() if item["network"]
    )


def test_job_source_api_reflects_only_saved_explicit_consent(client, auth_headers) -> None:
    saved = client.put(
        "/api/v1/career-profile",
        headers=auth_headers,
        json=_profile({"job_room": True, "swissdevjobs": False}),
    )
    assert saved.status_code == 200, saved.text

    response = client.get("/api/v1/search/sources", headers=auth_headers)
    sources = {item["key"]: item for item in response.json()}

    assert sources["job_room"]["consented"] is True
    assert sources["swissdevjobs"]["consented"] is False
    assert sources["adecco"]["consented"] is False


def test_unknown_job_source_consent_is_rejected(client, auth_headers) -> None:
    response = client.put(
        "/api/v1/career-profile",
        headers=auth_headers,
        json=_profile({"unknown_source": True}),
    )

    assert response.status_code == 422
