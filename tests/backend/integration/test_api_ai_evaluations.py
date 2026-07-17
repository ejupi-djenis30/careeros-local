def test_offline_evaluation_api_persists_aggregate_report(client, auth_headers) -> None:
    response = client.post(
        "/api/v1/ai-evaluations/run",
        json={"mode": "offline"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["passed"] is True
    assert payload["case_count"] == 8
    assert "cases" not in payload["metrics"]

    listing = client.get("/api/v1/ai-evaluations", headers=auth_headers)
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == payload["id"]


def test_evaluation_api_requires_authentication(client) -> None:
    assert client.get("/api/v1/ai-evaluations").status_code == 401
