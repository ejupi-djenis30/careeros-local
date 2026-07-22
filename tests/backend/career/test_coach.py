from unittest.mock import AsyncMock, MagicMock

from backend.inference.ports import InferenceUsage, StructuredInferenceResult


def _structured(payload):
    return StructuredInferenceResult(
        payload=payload,
        model_id="ollama-local/test-model",
        runtime="test",
        usage=InferenceUsage(prompt_tokens=30, completion_tokens=12),
        duration_ms=3,
    )


def _profile_payload():
    return {
        "expected_revision": 0,
        "display_name": "Mira Vale",
        "headline": "Analytical Engineer",
        "summary": "Private summary that is not sent unless represented as a fact.",
        "email": "private@example.test",
        "phone": "+41 79 000 00 00",
        "location": {"city": "Zurich"},
        "preferences": {},
        "facts": [
            {
                "fact_type": "achievement",
                "position": 0,
                "verification_status": "confirmed",
                "payload": {
                    "title": "Reduced build time",
                    "description": "Reduced local build time by 40 percent.",
                    "metric_value": 40,
                    "metric_unit": "percent",
                },
            }
        ],
        "goals": [],
    }


def test_grounded_coach_persists_valid_local_citations_and_can_be_deleted(
    client, auth_headers, monkeypatch
):
    profile = client.put(
        "/api/v1/career-profile", json=_profile_payload(), headers=auth_headers
    ).json()
    fact_id = profile["facts"][0]["id"]
    provider = MagicMock()
    provider.model_id = "ollama-local/test-model"
    provider.endpoint = "http://127.0.0.1:11434"
    provider.generate_structured_async = AsyncMock(
        return_value=_structured({
            "answer": "Lead with the verified 40 percent build-time reduction.",
            "claims": [
                {
                    "text": "Verified 40 percent build time reduction.",
                    "fact_ids": [fact_id],
                    "job_ids": [],
                }
            ],
            "fact_citations": [fact_id],
            "job_citations": [],
            "confidence": 0.95,
            "missing_evidence": [],
        })
    )
    factory = MagicMock(return_value=provider)
    monkeypatch.setattr("backend.api.routes.career_coach.get_provider_for_step", factory)

    response = client.post(
        "/api/v1/career-coach/messages",
        json={"message": "Which achievement should I emphasize?", "fact_ids": [fact_id]},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    reply = response.json()
    assert reply["message"]["cited_fact_ids"] == [fact_id]
    assert reply["message"]["model_id"] == "ollama-local/test-model"
    assert reply["message"]["generation_metadata"]["mode"] == "local"
    factory.assert_called_once_with("default")
    request = provider.generate_structured_async.await_args.args[0]
    assert "untrusted data" in request.system_prompt
    assert fact_id in request.user_prompt
    assert "Reduced local build time" in request.user_prompt
    assert "private@example.test" not in request.user_prompt
    assert "+41 79" not in request.user_prompt
    assert reply["message"]["generation_metadata"]["confidence"] == 0.95

    summaries = client.get("/api/v1/career-coach/conversations", headers=auth_headers)
    assert summaries.status_code == 200
    assert summaries.json()[0]["message_count"] == 2
    assert "messages" not in summaries.json()[0]
    detail = client.get(
        f"/api/v1/career-coach/conversations/{reply['conversation_id']}",
        headers=auth_headers,
    )
    assert [message["role"] for message in detail.json()["messages"]] == [
        "user",
        "assistant",
    ]
    deleted = client.delete(
        f"/api/v1/career-coach/conversations/{reply['conversation_id']}",
        headers=auth_headers,
    )
    assert deleted.status_code == 204
    assert (
        client.get(
            f"/api/v1/career-coach/conversations/{reply['conversation_id']}",
            headers=auth_headers,
        ).status_code
        == 404
    )


def test_coach_rejects_unsupported_citation(client, auth_headers, monkeypatch):
    profile = client.put(
        "/api/v1/career-profile", json=_profile_payload(), headers=auth_headers
    ).json()
    provider = MagicMock()
    provider.model_id = "ollama-local/test-model"
    provider.generate_structured_async = AsyncMock(
        return_value=_structured({
            "answer": "Unsupported claim",
            "claims": [
                {
                    "text": "Unsupported claim",
                    "fact_ids": ["00000000-0000-0000-0000-000000000000"],
                    "job_ids": [],
                }
            ],
            "fact_citations": ["00000000-0000-0000-0000-000000000000"],
            "job_citations": [],
            "confidence": 0.1,
            "missing_evidence": [],
        })
    )
    monkeypatch.setattr(
        "backend.api.routes.career_coach.get_provider_for_step", lambda _step: provider
    )
    response = client.post(
        "/api/v1/career-coach/messages",
        json={
            "message": "Invent something impressive",
            "fact_ids": [profile["facts"][0]["id"]],
        },
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "could not be grounded" in response.text
    conversations = client.get("/api/v1/career-coach/conversations", headers=auth_headers)
    assert conversations.status_code == 200
    assert conversations.json() == []


def test_coach_reports_local_model_unavailable_without_blocking_vault(
    client, auth_headers, monkeypatch
):
    client.put("/api/v1/career-profile", json=_profile_payload(), headers=auth_headers)
    provider = MagicMock()
    provider.model_id = "ollama-local/unavailable"
    provider.generate_structured_async = AsyncMock(side_effect=OSError("offline"))
    monkeypatch.setattr(
        "backend.api.routes.career_coach.get_provider_for_step", lambda _step: provider
    )
    response = client.post(
        "/api/v1/career-coach/messages",
        json={"message": "Help me plan my next step"},
        headers=auth_headers,
    )
    assert response.status_code == 503
    assert "local model is unavailable" in response.text
    assert client.get("/api/v1/career-profile", headers=auth_headers).status_code == 200
    assert client.get(
        "/api/v1/career-coach/conversations", headers=auth_headers
    ).json() == []
