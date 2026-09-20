import pytest

from backend.agent_work.acceptance import accept_work_proposal
from backend.agent_work.models import AgentWorkRequest
from backend.agent_work.proposal_service import ProposalService
from backend.agent_work.schemas import AgentWorkAcceptRequest, AgentWorkCreateRequest
from backend.agent_work.service import AgentWorkError, AgentWorkService
from backend.applications.models import ApplicationDossierDraft
from backend.applications.schemas import ApplicationCreate, GenerationProvenance
from backend.applications.service import ApplicationService
from backend.career.models import CareerFact
from backend.models.job import Job
from backend.resumes.draft_service import ResumeDraftService
from backend.resumes.models import ResumeDraft, ResumeVersion
from backend.resumes.schemas import ResumeDraftCreate
from tests.backend.agent_work.helpers import make_work, submission


def material_scenario(db, user_id, *, job_description=None, include_extra_context=False):
    original, grant, _, fact = make_work(db, user_id, "analyze")
    if job_description is not None:
        listing = db.get(Job, original.target_job_id).scraped_job
        listing.description = job_description
        listing.content_revision += 1
        db.commit()
    extra_fact = None
    request_fact_ids = [fact.id]
    if include_extra_context:
        extra_fact = CareerFact(
            profile_id=fact.profile_id,
            fact_type="experience",
            verification_status="confirmed",
            position=3,
            payload={
                "role": "Systems Engineer",
                "organization": "Synthetic GmbH",
                "description": "Developed Rust services",
            },
        )
        db.add(extra_fact)
        db.commit()
        request_fact_ids.append(extra_fact.id)
    resume = ResumeDraftService(db).create(
        user_id, ResumeDraftCreate(title="Reviewed CV", selected_fact_ids=[fact.id])
    )
    app = ApplicationService(db).create(user_id, ApplicationCreate(job_id=original.target_job_id))
    work = AgentWorkService(db).create_work_request(
        user_id,
        AgentWorkCreateRequest(
            work_kind="materials",
            grant_id=grant.id,
            instruction="Tailor cited materials",
            target_job_id=original.target_job_id,
            target_application_id=app.id,
            target_resume_id=resume.id,
            selected_fact_ids=request_fact_ids,
            preset_id="software-en",
            preset_version=1,
            locale="en",
        ),
    )
    text = "Developed Python services"
    result = {
        "kind": "materials",
        "preset_id": "software-en",
        "preset_version": 1,
        "locale": "en",
        "cv_selected_fact_ids": [fact.id],
        "cv_cited_overrides": [{"id": "cv-1", "text": text, "fact_ids": [fact.id]}],
        "cover_letter": [{"id": "letter-1", "text": text, "fact_ids": [fact.id]}],
        "email": {
            "mode": "short",
            "subject": "Application",
            "body": [{"id": "email-1", "text": text, "fact_ids": [fact.id]}],
            "attachment_names": [],
        },
        "questions_answers": [
            {"id": "answer-1", "question": "Experience?", "text": text, "fact_ids": [fact.id]}
        ],
        "requirements_to_evidence": [
            {"requirement": "Python", "quote_text": "Python", "fact_ids": [fact.id]}
        ],
    }
    return work, grant, result, resume, extra_fact


def test_material_acceptance_updates_both_drafts_without_publication(db_session, test_user):
    work, grant, result, resume, _ = material_scenario(db_session, test_user.id)
    ProposalService(db_session).submit_proposal(grant.id, work.id, submission(work, result))
    req = db_session.get(AgentWorkRequest, work.id)
    receipt = accept_work_proposal(
        db_session,
        user_id=test_user.id,
        request_id=work.id,
        accept_in=AgentWorkAcceptRequest(
            expected_revision=2, expected_target_revisions=req.input_revisions
        ),
    )
    assert receipt["resume_draft_id"] == resume.id and receipt["resume_revision"] == 2
    dossier = db_session.query(ApplicationDossierDraft).one()
    assert (
        dossier.resume_draft_id == resume.id
        and dossier.resume_version_id is None
        and dossier.resume_draft_revision == 2
    )
    assert dossier.content["cover_letter"] == "Developed Python services"
    provenance = GenerationProvenance.model_validate(dossier.content["generation_provenance"])
    assert provenance.source == "external-agent"
    assert str(provenance.request_id) == work.id
    assert str(provenance.grant_id) == grant.id
    assert provenance.generated_at is not None and provenance.generated_at.tzinfo is not None
    assert len(dossier.content["evidence_claims"]) == 3
    assert db_session.query(ResumeVersion).count() == 0
    current = db_session.get(ResumeDraft, resume.id)
    assert current.generation_context["mode"] == "external-agent"
    assert current.generation_context["request_id"] == work.id
    assert (
        ResumeDraftService(db_session)
        .response(ResumeDraftService(db_session).profile(test_user.id), current)
        .generation_context.mode
        == "external-agent"
    )


def test_material_late_dossier_failure_rolls_back_cv_and_acceptance(
    db_session, test_user, monkeypatch
):
    work, grant, result, resume, _ = material_scenario(db_session, test_user.id)
    ProposalService(db_session).submit_proposal(grant.id, work.id, submission(work, result))
    req = db_session.get(AgentWorkRequest, work.id)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic dossier fault")

    monkeypatch.setattr(ApplicationService, "mutate_dossier_draft_flush_only", fail)
    with pytest.raises(RuntimeError):
        accept_work_proposal(
            db_session,
            user_id=test_user.id,
            request_id=work.id,
            accept_in=AgentWorkAcceptRequest(
                expected_revision=2, expected_target_revisions=req.input_revisions
            ),
        )
    db_session.expire_all()
    assert db_session.get(ResumeDraft, resume.id).revision == 1
    assert db_session.query(ApplicationDossierDraft).count() == 0
    assert db_session.get(AgentWorkRequest, work.id).state == "returned"


def test_changed_destination_cv_blocks_acceptance(db_session, test_user):
    work, grant, result, resume, _ = material_scenario(db_session, test_user.id)
    ProposalService(db_session).submit_proposal(grant.id, work.id, submission(work, result))
    req = db_session.get(AgentWorkRequest, work.id)
    current = db_session.get(ResumeDraft, resume.id)
    current.revision += 1
    db_session.commit()
    with pytest.raises(AgentWorkError) as exc:
        accept_work_proposal(
            db_session,
            user_id=test_user.id,
            request_id=work.id,
            accept_in=AgentWorkAcceptRequest(
                expected_revision=2, expected_target_revisions=req.input_revisions
            ),
        )
    assert (
        exc.value.code == "stale_input" and db_session.query(ApplicationDossierDraft).count() == 0
    )


def test_material_request_uses_selected_resume_preset_when_omitted(db_session, test_user):
    work, grant, _, resume, _ = material_scenario(db_session, test_user.id)
    created = AgentWorkService(db_session).create_work_request(
        test_user.id,
        AgentWorkCreateRequest(
            work_kind="materials",
            grant_id=grant.id,
            instruction="Use current CV layout",
            target_application_id=work.target_application_id,
            target_resume_id=resume.id,
            selected_fact_ids=[],
        ),
    )
    assert (created.preset_id, created.preset_version, created.locale) == ("software-en", 1, "en")


@pytest.mark.parametrize(
    "invalid_kind",
    ["invented_requirement", "opposite_polarity", "negated_requirement", "duplicate_override"],
)
def test_material_submission_rejects_unpublishable_or_conflicting_content(
    db_session, test_user, invalid_kind
):
    description = (
        "Python not required, English, permanent, Zurich"
        if invalid_kind in {"opposite_polarity", "negated_requirement"}
        else None
    )
    work, grant, result, resume, _ = material_scenario(
        db_session,
        test_user.id,
        job_description=description,
    )
    if invalid_kind == "invented_requirement":
        result["requirements_to_evidence"][0]["requirement"] = "Doctorate in quantum physics"
    elif invalid_kind == "opposite_polarity":
        result["requirements_to_evidence"][0].update(
            {"requirement": "Python required", "quote_text": "Python not required"}
        )
    elif invalid_kind == "negated_requirement":
        result["requirements_to_evidence"][0].update(
            {"requirement": "Python", "quote_text": "Python not required"}
        )
    else:
        result["cv_cited_overrides"].append(
            {
                "id": "cv-conflict",
                "text": "Developed Python services",
                "fact_ids": result["cv_selected_fact_ids"],
            }
        )

    with pytest.raises(AgentWorkError):
        ProposalService(db_session).submit_proposal(
            grant.id,
            work.id,
            submission(work, result, f"invalid-{invalid_kind}"),
        )
    assert db_session.get(ResumeDraft, resume.id).revision == 1
    assert db_session.query(ApplicationDossierDraft).count() == 0
    assert db_session.get(AgentWorkRequest, work.id).state == "queued"


def test_material_requirement_evidence_must_be_part_of_selected_cv(db_session, test_user):
    work, grant, result, resume, extra_fact = material_scenario(
        db_session,
        test_user.id,
        job_description="Python Engineer, Rust, English, permanent, Zurich",
        include_extra_context=True,
    )
    assert extra_fact is not None
    result["requirements_to_evidence"] = [
        {"requirement": "Rust", "quote_text": "Rust", "fact_ids": [extra_fact.id]}
    ]
    with pytest.raises(AgentWorkError) as exc:
        ProposalService(db_session).submit_proposal(
            grant.id,
            work.id,
            submission(work, result, "unselected-requirement-evidence"),
        )
    assert exc.value.code == "evidence_invalid"
    assert db_session.get(ResumeDraft, resume.id).revision == 1
    assert db_session.query(ApplicationDossierDraft).count() == 0


def test_material_requirement_must_be_grounded_by_the_mapped_candidate_fact(
    db_session, test_user
):
    work, grant, result, resume, extra_fact = material_scenario(
        db_session,
        test_user.id,
        job_description="Python Engineer, English, permanent, Zurich",
        include_extra_context=True,
    )
    assert extra_fact is not None
    result["cv_selected_fact_ids"].append(extra_fact.id)
    result["requirements_to_evidence"] = [
        {"requirement": "Python", "quote_text": "Python", "fact_ids": [extra_fact.id]}
    ]
    with pytest.raises(AgentWorkError) as exc:
        ProposalService(db_session).submit_proposal(
            grant.id,
            work.id,
            submission(work, result, "unrelated-requirement-evidence"),
        )
    assert exc.value.code == "evidence_invalid"
    assert db_session.get(ResumeDraft, resume.id).revision == 1
    assert db_session.query(ApplicationDossierDraft).count() == 0
