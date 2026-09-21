from __future__ import annotations

import pytest

from backend.agent_work.models import AgentWorkRequest
from backend.agent_work.schemas import AgentWorkCreateRequest
from backend.agent_work.service import AgentWorkError, AgentWorkService
from backend.automation.grants import issue_grant


def _create_test_grant(db_session, user_id: int):
    view, token = issue_grant(
        db_session,
        user_id=user_id,
        label="Test Grant",
        scopes=("context:read", "proposals:write"),
        acknowledged_disclosure=True,
    )
    return view, token


def test_create_list_get_work_request(db_session, test_user) -> None:
    grant_view, _ = _create_test_grant(db_session, test_user.id)
    service = AgentWorkService(db_session)

    create_req = AgentWorkCreateRequest(
        work_kind="discover",
        grant_id=grant_view.id,
        instruction="Find remote backend roles in Switzerland",
        lifetime_hours=48,
    )
    view = service.create_work_request(test_user.id, create_req)
    assert view.id is not None
    assert view.state == "queued"
    assert view.revision == 1
    assert view.work_kind == "discover"
    assert view.bound_grant_id == grant_view.id

    # List requests
    items, total = service.list_work_requests(test_user.id)
    assert total == 1
    assert len(items) == 1
    assert items[0].id == view.id

    # Get detail
    detail = service.get_work_request(test_user.id, view.id)
    assert detail.id == view.id
    assert detail.instruction == "Find remote backend roles in Switzerland"
    assert detail.proposal is None


def test_cancel_work_request_cas(db_session, test_user) -> None:
    grant_view, _ = _create_test_grant(db_session, test_user.id)
    service = AgentWorkService(db_session)

    create_req = AgentWorkCreateRequest(
        work_kind="discover",
        grant_id=grant_view.id,
        instruction="Cancel test",
    )
    view = service.create_work_request(test_user.id, create_req)

    # Wrong revision fails
    with pytest.raises(AgentWorkError) as exc:
        service.cancel_work_request(test_user.id, view.id, expected_revision=2)
    assert exc.value.code == "revision_conflict"

    # Correct revision cancels
    canceled = service.cancel_work_request(test_user.id, view.id, expected_revision=1)
    assert canceled.state == "canceled"
    assert canceled.revision == 2

    # Cannot cancel again
    with pytest.raises(AgentWorkError) as exc:
        service.cancel_work_request(test_user.id, view.id, expected_revision=2)
    assert exc.value.code == "work_canceled"


def test_reject_work_request_only_after_returned(db_session, test_user) -> None:
    grant_view, _ = _create_test_grant(db_session, test_user.id)
    service = AgentWorkService(db_session)

    create_req = AgentWorkCreateRequest(
        work_kind="discover",
        grant_id=grant_view.id,
        instruction="Reject test",
    )
    view = service.create_work_request(test_user.id, create_req)

    # Rejecting queued request fails (must be returned first)
    with pytest.raises(AgentWorkError) as exc:
        service.reject_work_request(test_user.id, view.id, expected_revision=1)
    assert exc.value.code == "revision_conflict"

    # Set state to returned manually for lifecycle test
    req_db = db_session.get(AgentWorkRequest, view.id)
    assert req_db is not None
    req_db.state = "returned"
    db_session.commit()

    rejected = service.reject_work_request(test_user.id, view.id, expected_revision=1)
    assert rejected.state == "rejected"
    assert rejected.revision == 2
