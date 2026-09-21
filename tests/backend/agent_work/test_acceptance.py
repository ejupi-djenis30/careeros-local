from datetime import UTC, datetime, timedelta

import pytest

from backend.agent_work.acceptance import accept_work_proposal
from backend.agent_work.models import AgentWorkRequest
from backend.agent_work.proposal_service import ProposalService
from backend.agent_work.schemas import AgentWorkAcceptRequest
from backend.agent_work.service import AgentWorkError, AgentWorkService
from backend.applications.models import Application, ApplicationEvent
from backend.applications.schemas import ApplicationCreate
from backend.applications.service import ApplicationService
from backend.career.models import CandidateProfile
from backend.models.job import Job, ScrapedJob
from backend.schemas.job import JobResponse
from backend.services.job_service import JobService
from tests.backend.agent_work.helpers import analysis, discovery, make_work, submission


def accept(db, user_id, work):
    detail = AgentWorkService(db).get_work_request(user_id, work.id)
    return accept_work_proposal(
        db,
        user_id=user_id,
        request_id=work.id,
        accept_in=AgentWorkAcceptRequest(
            expected_revision=detail.revision, expected_target_revisions=detail.input_revisions
        ),
    )


def test_accept_discovery_proposal_creates_job_and_app(db_session, test_user):
    work, grant, _, _ = make_work(db_session, test_user.id)
    request = submission(work)
    receipt = ProposalService(db_session).submit_proposal(grant.id, work.id, request)
    accepted = accept(db_session, test_user.id, work)
    assert len(accepted["created_job_ids"]) == len(accepted["created_application_ids"]) == 1
    assert accept(db_session, test_user.id, work) == accepted
    assert (
        ProposalService(db_session).submit_proposal(grant.id, work.id, request).proposal_id
        == receipt.proposal_id
    )
    assert db_session.query(Job).count() == db_session.query(Application).count() == 1
    job = db_session.query(Job).one()
    assert job.scraped_job.external_url == request.result.listings[0].external_url
    assert (
        datetime.fromisoformat(job.scraped_job.raw_metadata["observed_at"])
        == request.result.listings[0].observed_at
    )
    assert db_session.query(Application).one().current_stage == "saved"
    with pytest.raises(AgentWorkError) as exc:
        accept_work_proposal(
            db_session,
            user_id=test_user.id,
            request_id=work.id,
            accept_in=AgentWorkAcceptRequest(
                expected_revision=3,
                expected_target_revisions={},
            ),
        )
    assert exc.value.code == "stale_input"


def test_distinct_discoveries_refresh_one_catalog_row_and_keep_application_snapshot(
    db_session, test_user
):
    first_seen = datetime.now(UTC) - timedelta(minutes=2)
    second_seen = datetime.now(UTC) - timedelta(minutes=1)
    first_work, first_grant, _, _ = make_work(db_session, test_user.id)
    first_result = discovery("Original Platform Engineer")
    first_result["listings"][0].update(
        {
            "external_url": "HTTPS://Example.COM/jobs/Engineer#apply",
            "source_text": "Python Engineer",
            "observed_at": first_seen.isoformat(),
        }
    )
    ProposalService(db_session).submit_proposal(
        first_grant.id, first_work.id, submission(first_work, first_result, "first-observation")
    )
    first_receipt = accept(db_session, test_user.id, first_work)
    catalog = db_session.query(ScrapedJob).one()
    catalog.normalization_status = "normalized"
    catalog.normalized_domain = "software"
    db_session.commit()

    second_work, second_grant, _, _ = make_work(db_session, test_user.id)
    second_result = discovery("Updated Platform Engineer")
    second_result["listings"][0].update(
        {
            "external_url": "https://example.com/jobs/Engineer",
            "source_text": "Rust Engineer with Kubernetes",
            "location": "Basel",
            "observed_at": second_seen.isoformat(),
        }
    )
    ProposalService(db_session).submit_proposal(
        second_grant.id,
        second_work.id,
        submission(second_work, second_result, "second-observation"),
    )
    second_receipt = accept(db_session, test_user.id, second_work)

    assert db_session.query(ScrapedJob).count() == 1
    assert db_session.query(Job).count() == 1
    assert db_session.query(Application).count() == 1
    db_session.refresh(catalog)
    assert catalog.title == "Updated Platform Engineer"
    assert catalog.description == "Rust Engineer with Kubernetes"
    assert catalog.location == "Basel"
    assert catalog.content_revision == 2
    assert catalog.normalization_status == "pending" and catalog.normalized_domain is None
    assert catalog.first_seen_at == first_seen and catalog.last_seen_at == second_seen
    assert datetime.fromisoformat(catalog.raw_metadata["observed_at"]) == second_seen
    application = db_session.query(Application).one()
    assert application.job_snapshot["title"] == "Original Platform Engineer"
    assert application.revision == 2
    assert [event.event_type for event in db_session.query(ApplicationEvent).all()] == [
        "stage",
        "note",
    ]
    assert first_receipt["created_job_ids"] == second_receipt["created_job_ids"]
    assert first_receipt["created_application_ids"] == second_receipt["created_application_ids"]


def test_accept_analysis_proposal_updates_job_without_spoofing(db_session, test_user):
    work, grant, _, fact = make_work(db_session, test_user.id, "analyze")
    result = analysis(fact.id)
    result["scores"]["overall_score"] = 7
    job = db_session.get(Job, work.target_job_id)
    job.intent_match_score = 99
    job.transferability_score = 98
    job.qualification_gap_score = 97
    job.analysis_legacy_snapshot = {"legacy": True}
    job.red_flags = ["legacy"]
    db_session.commit()
    ProposalService(db_session).submit_proposal(grant.id, work.id, submission(work, result))
    accept(db_session, test_user.id, work)
    job = db_session.get(Job, work.target_job_id)
    assert job.affinity_score == 90
    assert job.analysis_provenance == "external_agent_proposal"
    assert job.analysis_execution_id is None
    assert job.analysis_structured["payload_digest"]
    assert job.intent_match_score is None
    assert job.transferability_score is None
    assert job.qualification_gap_score is None
    assert job.analysis_legacy_snapshot is None and job.red_flags is None


def test_accepted_external_analysis_remains_verified_in_new_application_snapshot(
    db_session, test_user
):
    work, grant, _, fact = make_work(db_session, test_user.id, "analyze")
    ProposalService(db_session).submit_proposal(
        grant.id, work.id, submission(work, analysis(fact.id))
    )
    accept(db_session, test_user.id, work)

    created = ApplicationService(db_session).create(
        test_user.id, ApplicationCreate(job_id=work.target_job_id)
    )
    stored = db_session.get(Application, created.id)

    assert stored.job_snapshot["match"]["receipt_verified"] is True
    assert stored.job_snapshot["match"]["score"] == 90
    assert stored.job_snapshot["match"]["analysis"].startswith("External Agent Analysis")


@pytest.mark.parametrize(
    "change,code",
    [("profile", "stale_input"), ("expired", "work_expired"), ("expected_targets", "stale_input")],
)
def test_acceptance_rechecks_inputs_and_does_not_write_on_failure(
    db_session, test_user, change, code
):
    work, grant, _, _ = make_work(db_session, test_user.id)
    ProposalService(db_session).submit_proposal(grant.id, work.id, submission(work))
    detail = AgentWorkService(db_session).get_work_request(test_user.id, work.id)
    if change == "profile":
        db_session.add(
            CandidateProfile(user_id=test_user.id, display_name="Later", revision=1, preferences={})
        )
        db_session.commit()
    if change == "expired":
        db_session.get(AgentWorkRequest, work.id).expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
        db_session.commit()
    with pytest.raises(AgentWorkError) as exc:
        accept_work_proposal(
            db_session,
            user_id=test_user.id,
            request_id=work.id,
            accept_in=AgentWorkAcceptRequest(
                expected_revision=2,
                expected_target_revisions={}
                if change == "expected_targets"
                else detail.input_revisions,
            ),
        )
    assert exc.value.code == code
    assert db_session.query(Job).count() == db_session.query(Application).count() == 0


def test_external_attestation_requires_accepted_owned_receipt_and_current_evidence(
    db_session, test_user
):
    from backend.ai.attestation import is_external_agent_match_attested

    work, grant, _, fact = make_work(db_session, test_user.id, "analyze")
    ProposalService(db_session).submit_proposal(
        grant.id, work.id, submission(work, analysis(fact.id))
    )
    accept(db_session, test_user.id, work)
    job = db_session.get(Job, work.target_job_id)
    assert is_external_agent_match_attested(db_session, job, test_user.id)
    assert not is_external_agent_match_attested(db_session, job, test_user.id + 1)
    fact.payload = {**fact.payload, "description": "Changed after approval"}
    db_session.commit()
    assert not is_external_agent_match_attested(db_session, job, test_user.id)
    stored_work = db_session.get(AgentWorkRequest, work.id)
    with pytest.raises(AgentWorkError) as exc:
        accept_work_proposal(
            db_session,
            user_id=test_user.id,
            request_id=work.id,
            accept_in=AgentWorkAcceptRequest(
                expected_revision=3,
                expected_target_revisions=stored_work.input_revisions,
            ),
        )
    assert exc.value.code == "stale_input"


def test_external_attestation_rejects_forged_self_reported_provenance(db_session, test_user):
    from backend.ai.attestation import is_external_agent_match_attested

    work, _, _, _ = make_work(db_session, test_user.id, "analyze")
    job = db_session.get(Job, work.target_job_id)
    job.analysis_provenance = "external_agent_proposal"
    job.analysis_structured = {
        "source": "external_agent",
        "request_id": work.id,
        "proposal_id": work.id,
    }
    db_session.commit()
    assert not is_external_agent_match_attested(db_session, job, test_user.id)


def test_job_response_external_scores_require_separate_verified_flag(db_session, test_user):
    work, grant, _, fact = make_work(db_session, test_user.id, "analyze")
    ProposalService(db_session).submit_proposal(
        grant.id, work.id, submission(work, analysis(fact.id))
    )
    accept(db_session, test_user.id, work)
    job = db_session.get(Job, work.target_job_id)
    unverified = JobResponse.model_validate(job)
    assert unverified.affinity_score is None and unverified.analysis_structured is None
    job.external_analysis_verified = True
    verified = JobResponse.model_validate(job)
    assert verified.affinity_score == 90 and verified.external_analysis_verified
    assert not verified.analysis_verified and verified.analysis_execution_id is None


def test_job_service_attests_external_analysis_before_display_filter_and_sort(
    db_session, test_user
):
    work, grant, _, fact = make_work(db_session, test_user.id, "analyze")
    ProposalService(db_session).submit_proposal(
        grant.id, work.id, submission(work, analysis(fact.id))
    )
    accept(db_session, test_user.id, work)

    service = JobService(db_session)
    filtered = service.get_jobs_by_user(
        test_user.id,
        page=1,
        page_size=20,
        filters={"min_score": 80, "sort_by": "affinity_score", "sort_order": "desc"},
    )
    assert filtered["total"] == 1
    assert filtered["avg_score"] == 90
    response = JobResponse.model_validate(filtered["items"][0])
    assert response.external_analysis_verified is True
    assert response.analysis_verified is False
    assert response.affinity_score == 90

    fact.payload = {**fact.payload, "description": "Changed after review"}
    db_session.commit()
    stale_filtered = service.get_jobs_by_user(
        test_user.id,
        page=1,
        page_size=20,
        filters={"min_score": 80, "sort_by": "affinity_score", "sort_order": "desc"},
    )
    assert stale_filtered["total"] == 0

    stale_unfiltered = service.get_jobs_by_user(
        test_user.id,
        page=1,
        page_size=20,
        filters={"sort_by": "created_at", "sort_order": "desc"},
    )
    stale_response = JobResponse.model_validate(stale_unfiltered["items"][0])
    assert stale_response.external_analysis_verified is False
    assert stale_response.analysis_structured is None
    assert stale_response.affinity_score is None
