from datetime import UTC, datetime, timedelta

import pytest

from backend.agent_work.models import AgentProposal, AgentWorkRequest
from backend.agent_work.proposal_service import ProposalService
from backend.agent_work.service import AgentWorkError, AgentWorkService
from backend.automation.grants import revoke_grant
from backend.career.models import CandidateProfile
from tests.backend.agent_work.helpers import analysis, make_work, submission


def test_submit_proposal_success_and_idempotent_retry(db_session, test_user):
    work, grant, _, _ = make_work(db_session, test_user.id)
    request = submission(work)
    service = ProposalService(db_session)
    first = service.submit_proposal(grant.id, work.id, request)
    second = service.submit_proposal(grant.id, work.id, request)
    assert first == second
    conflicting = request.model_copy(deep=True)
    conflicting.result.listings[0].title = "Other engineer"
    with pytest.raises(AgentWorkError, match="different result"):
        service.submit_proposal(grant.id, work.id, conflicting)
    assert db_session.query(AgentProposal).count() == 1


@pytest.mark.parametrize(
    "change,code",
    [
        ("digest", "stale_input"),
        ("profile", "stale_input"),
        ("revoke", "grant_revoked"),
        ("expiry", "work_expired"),
        ("cancel", "work_canceled"),
        ("identity", "invalid_result"),
    ],
)
def test_submission_rejects_changed_authority_and_inputs(db_session, test_user, change, code):
    work, grant, _, _ = make_work(db_session, test_user.id)
    request = submission(work)
    if change == "digest":
        request.input_digest = "0" * 64
    if change == "identity":
        request.request_id = grant.id
    if change == "profile":
        db_session.add(
            CandidateProfile(user_id=test_user.id, display_name="Later", revision=1, preferences={})
        )
        db_session.commit()
    if change == "revoke":
        revoke_grant(db_session, user_id=test_user.id, grant_id=grant.id)
    if change == "expiry":
        db_session.get(AgentWorkRequest, work.id).expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
        db_session.commit()
    if change == "cancel":
        AgentWorkService(db_session).cancel_work_request(test_user.id, work.id, 1)
    with pytest.raises(AgentWorkError) as exc:
        ProposalService(db_session).submit_proposal(grant.id, work.id, request)
    assert exc.value.code == code
    assert db_session.query(AgentProposal).count() == 0


@pytest.mark.parametrize(
    "claim",
    [
        "Earned a doctorate at Harvard",
        "Developed Python services in 2035",
        "Increased revenue by 250000",
    ],
)
def test_grounding_rejects_invented_assertions_and_rolls_back(db_session, test_user, claim):
    work, grant, _, fact = make_work(db_session, test_user.id, "analyze")
    result = analysis(fact.id)
    result["claims"][0]["claim_text"] = claim
    with pytest.raises(AgentWorkError) as exc:
        ProposalService(db_session).submit_proposal(grant.id, work.id, submission(work, result))
    assert exc.value.code == "evidence_invalid"
    db_session.expire_all()
    assert db_session.get(AgentWorkRequest, work.id).state == "queued"
    assert db_session.query(AgentProposal).count() == 0


def test_live_fact_edit_with_unchanged_profile_revision_is_stale(db_session, test_user):
    work, grant, _, fact = make_work(db_session, test_user.id, "analyze")
    result = analysis(fact.id)
    fact.payload = {**fact.payload, "description": "Changed evidence"}
    db_session.commit()
    with pytest.raises(AgentWorkError) as exc:
        ProposalService(db_session).submit_proposal(grant.id, work.id, submission(work, result))
    assert exc.value.code == "stale_input"


def test_language_gate_cannot_claim_eligibility_using_unrelated_fact(db_session, test_user):
    work, grant, _, fact = make_work(db_session, test_user.id, "analyze")
    result = analysis(fact.id)
    next(gate for gate in result["gates"] if gate["dimension"] == "language")["fact_ids"] = [
        fact.id
    ]
    with pytest.raises(AgentWorkError) as exc:
        ProposalService(db_session).submit_proposal(grant.id, work.id, submission(work, result))
    assert exc.value.code == "evidence_invalid"
