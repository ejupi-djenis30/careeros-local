"""Synthetic fixtures using the real public agent contracts."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from backend.agent_work.schemas import AgentWorkCreateRequest, ProposalSubmissionRequest
from backend.agent_work.service import AgentWorkService
from backend.automation.grants import issue_grant
from backend.career.models import CandidateProfile, CareerFact
from backend.models.job import Job, ScrapedJob

DIMENSIONS = ("role", "requirements", "language", "location", "contract", "freshness")


def gates(fact_id=None):
    quotes = {
        "role": "Engineer",
        "requirements": "Python",
        "language": "English",
        "location": "Zurich",
        "contract": "permanent",
        "freshness": "posted today",
    }
    return [
        {
            "dimension": name,
            "status": "eligible" if fact_id else "hold",
            "reason": "Supported" if fact_id else "Not verified",
            "fact_ids": [
                str(uuid5(NAMESPACE_URL, fact_id + "-language")) if name == "language" else fact_id
            ]
            if fact_id
            else [],
            "quote_references": [quotes[name]]
            if fact_id
            else [],
            "unknowns": [] if fact_id else ["Not verified"],
        }
        for name in DIMENSIONS
    ]


def scores(value=0):
    return {
        **{
            name: {"score": value, "explanation": "Supported" if value else "Unknown: not verified"}
            for name in DIMENSIONS
        },
        "overall_score": value,
    }


def discovery(title="Engineer"):
    return {
        "kind": "discover",
        "listings": [
            {
                "title": title,
                "company": "Fictional AG",
                "external_url": "https://example.com/jobs/engineer",
                "source_text": "Python Engineer",
                "observed_at": datetime.now(UTC).isoformat(),
                "source_platform": "company_careers",
                "gates": gates(),
                "scores": scores(),
            }
        ],
    }


def make_work(db, user_id, kind="discover"):
    grant, token = issue_grant(
        db,
        user_id=user_id,
        label="Synthetic review grant",
        scopes=["context:read", "proposals:write"],
        acknowledged_disclosure=True,
    )
    targets = {}
    fact = None
    if kind != "discover":
        profile = CandidateProfile(
            user_id=user_id,
            display_name="Fictional Candidate",
            revision=1,
            preferences={"preferred_locations": ["Zurich"], "contract_types": ["permanent"]},
        )
        db.add(profile)
        db.flush()
        fact = CareerFact(
            profile_id=profile.id,
            fact_type="experience",
            verification_status="confirmed",
            position=1,
            payload={
                "role": "Software Engineer",
                "organization": "Fictional AG",
                "description": "Developed Python services",
            },
        )
        db.add(fact)
        db.flush()
        language_id = str(uuid5(NAMESPACE_URL, fact.id + "-language"))
        db.add(
            CareerFact(
                id=language_id,
                profile_id=profile.id,
                fact_type="language",
                verification_status="confirmed",
                position=2,
                payload={"language": "English", "level": "C1"},
            )
        )
        listing = ScrapedJob(
            platform="manual",
            platform_job_id="fixture-" + str(user_id),
            title="Engineer",
            company="Fictional AG",
            external_url="https://example.com/job",
            description="Python Engineer, English, permanent, Zurich, posted today",
            location="Zurich",
        )
        db.add(listing)
        db.flush()
        job = Job(user_id=user_id, scraped_job_id=listing.id)
        db.add(job)
        db.commit()
        targets = {"target_job_id": job.id, "selected_fact_ids": [fact.id, language_id]}
    work = AgentWorkService(db).create_work_request(
        user_id,
        AgentWorkCreateRequest(
            work_kind=kind, grant_id=grant.id, instruction="Synthetic work", **targets
        ),
    )
    return work, grant, token, fact


def submission(work, result=None, key="synthetic-1"):
    return ProposalSubmissionRequest.model_validate(
        {
            "request_id": work.id,
            "input_digest": work.input_digest,
            "idempotency_key": key,
            "client": "Synthetic agent",
            "result": result or discovery(),
        }
    )


def analysis(fact_id):
    return {
        "kind": "analyze",
        "gates": gates(fact_id),
        "scores": scores(90),
        "claims": [
            {
                "claim_text": "Developed Python services",
                "fact_ids": [fact_id],
                "quote_text": "Python",
            }
        ],
        "recommendation": "strong_fit",
    }
