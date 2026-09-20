import pytest

from backend.agent_work.models import AgentWorkRequest
from backend.automation.grants import issue_grant
from tests.backend.agent_work.helpers import discovery, make_work


def test_mutual_auth_exclusivity_bridge_rejects_jwt_and_missing_auth(bridge_client, auth_headers):
    for headers in ({}, auth_headers):
        res = bridge_client.get("/api/v1/agent-bridge/status", headers=headers)
        assert res.status_code == 401
        assert res.json()["detail"]["code"] == "grant_required"
        assert "no-store" in res.headers["cache-control"]


def test_owner_routes_reject_grant(bridge_client, db_session, test_user):
    _, _, token, _ = make_work(db_session, test_user.id)
    assert (
        bridge_client.get(
            "/api/v1/agent-work", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 401
    )


def test_scope_gating_and_metadata_privacy(bridge_client, db_session, test_user):
    grant, token = issue_grant(
        db_session,
        user_id=test_user.id,
        label="Write only",
        scopes=["proposals:write"],
        acknowledged_disclosure=True,
    )
    from backend.agent_work.schemas import AgentWorkCreateRequest
    from backend.agent_work.service import AgentWorkService

    work = AgentWorkService(db_session).create_work_request(
        test_user.id,
        AgentWorkCreateRequest(
            work_kind="discover",
            grant_id=grant.id,
            instruction="Private instruction alice@example.com",
        ),
    )
    headers = {"Authorization": "Bearer " + token}
    listing = bridge_client.get("/api/v1/agent-bridge/work-requests", headers=headers)
    assert listing.status_code == 200
    assert "Private instruction" not in listing.text and "alice@example.com" not in listing.text
    assert "instruction" not in listing.json()["items"][0]
    assert (
        bridge_client.get(
            f"/api/v1/agent-bridge/work-requests/{work.id}/context", headers=headers
        ).status_code
        == 403
    )


def test_agent_bridge_and_work_lifecycle_flow(bridge_client, db_session, test_user, auth_headers):
    work, _, token, _ = make_work(db_session, test_user.id)
    headers = {"Authorization": "Bearer " + token}
    context = bridge_client.get(
        f"/api/v1/agent-bridge/work-requests/{work.id}/context", headers=headers
    )
    assert context.status_code == 200 and "proposal_schema" in context.json()
    body = {
        "request_id": work.id,
        "input_digest": work.input_digest,
        "idempotency_key": "api-test",
        "client": "Synthetic",
        "result": discovery(),
    }
    returned = bridge_client.post(
        f"/api/v1/agent-bridge/work-requests/{work.id}/result", headers=headers, json=body
    )
    assert returned.status_code == 200
    detail = bridge_client.get(f"/api/v1/agent-work/{work.id}", headers=auth_headers).json()
    accepted = bridge_client.post(
        f"/api/v1/agent-work/{work.id}/accept",
        headers=auth_headers,
        json={
            "expected_revision": detail["revision"],
            "expected_target_revisions": detail["input_revisions"],
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["created_job_ids"]
    assert (
        bridge_client.post(
            f"/api/v1/agent-bridge/work-requests/{work.id}/result", headers=headers, json=body
        ).json()["proposal_id"]
        == returned.json()["proposal_id"]
    )


@pytest.mark.parametrize("failure", ["foreign_grant", "canceled", "expired", "maintenance"])
def test_context_and_receipt_fail_closed(bridge_client, db_session, test_user, failure):
    from datetime import UTC, datetime, timedelta

    from backend.agent_work.proposal_service import ProposalService
    from tests.backend.agent_work.helpers import submission

    work, grant, token, _ = make_work(db_session, test_user.id)
    ProposalService(db_session).submit_proposal(grant.id, work.id, submission(work))
    if failure == "foreign_grant":
        _, token = issue_grant(
            db_session,
            user_id=test_user.id,
            label="Other",
            scopes=["context:read"],
            acknowledged_disclosure=True,
        )
    elif failure == "canceled":
        db_session.get(AgentWorkRequest, work.id).state = "canceled"
    elif failure == "expired":
        db_session.get(AgentWorkRequest, work.id).expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
    else:
        test_user.vault_lifecycle_state = "reset_pending"
    db_session.commit()
    for suffix in ("context", "result"):
        result = bridge_client.get(
            f"/api/v1/agent-bridge/work-requests/{work.id}/{suffix}",
            headers={"Authorization": "Bearer " + token},
        )
        assert result.status_code != 200
        assert "no-store" in result.headers["cache-control"]


@pytest.mark.parametrize(
    "headers,peer",
    [
        ({"Origin": "https://example.com"}, "127.0.0.1"),
        ({}, "192.0.2.1"),
        ({"Host": "example.com"}, "127.0.0.1"),
    ],
)
def test_bridge_transport_rejects_nonlocal_authority(
    bridge_client, db_session, test_user, headers, peer
):
    _, _, token, _ = make_work(db_session, test_user.id)
    bridge_client._transport.client = (peer, 50100)
    res = bridge_client.get(
        "/api/v1/agent-bridge/status", headers={"Authorization": "Bearer " + token, **headers}
    )
    assert res.status_code in {400, 403}


def test_validation_errors_do_not_echo_body(bridge_client, db_session, test_user):
    work, _, token, _ = make_work(db_session, test_user.id)
    secret = "never-echo-synthetic-private-value"
    response = bridge_client.post(
        f"/api/v1/agent-bridge/work-requests/{work.id}/result",
        headers={"Authorization": "Bearer " + token},
        json={"client": secret},
    )
    assert response.status_code == 422 and secret not in response.text
    assert "no-store" in response.headers["cache-control"]


def test_corrupt_stored_proposal_fails_with_private_owner_error(
    bridge_client, db_session, test_user, auth_headers
):
    from backend.agent_work.models import AgentProposal
    from backend.agent_work.proposal_service import ProposalService
    from tests.backend.agent_work.helpers import submission

    work, grant, _, _ = make_work(db_session, test_user.id)
    ProposalService(db_session).submit_proposal(grant.id, work.id, submission(work))
    request = db_session.get(AgentWorkRequest, work.id)
    proposal = db_session.query(AgentProposal).filter_by(request_id=work.id).one()
    proposal.payload = {"kind": "unknown", "private": "never-echo-synthetic-private-value"}
    db_session.commit()
    response = bridge_client.post(
        f"/api/v1/agent-work/{work.id}/accept",
        headers=auth_headers,
        json={"expected_revision": 2, "expected_target_revisions": request.input_revisions},
    )
    assert response.status_code == 422 and "never-echo" not in response.text
    assert response.json()["detail"]["code"] == "invalid_result"
    db_session.expire_all()
    assert db_session.get(AgentWorkRequest, work.id).state == "returned"
