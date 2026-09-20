from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.agent_work.context import (
    build_context_snapshot,
    redact_contacts,
)
from backend.career.models import CandidateProfile, CareerFact
from backend.models.job import Job, ScrapedJob


def test_contact_redaction() -> None:
    text = "Please reach me at alice.smith@example.ch or +41 79 123 4567 for inquiries."
    redacted = redact_contacts(text)
    assert "alice.smith@example.ch" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "+41 79 123 4567" not in redacted
    assert "[REDACTED_PHONE]" in redacted


def test_contact_redaction_handles_long_non_email_runs_in_linear_time() -> None:
    prefix = "%" * 100_000
    redacted = redact_contacts(f"{prefix} alice@example.ch.")
    assert redacted == f"{prefix} [REDACTED_EMAIL]."


@pytest.mark.parametrize("phone", ["079 123 45 67", "044 123 45 67", "0791234567"])
def test_contact_redaction_covers_domestic_swiss_numbers(phone):
    redacted = redact_contacts(f"Call {phone} for private details")
    assert phone not in redacted
    assert "[REDACTED_PHONE]" in redacted


def test_build_context_snapshot_redacts_and_computes_digest(db_session, test_user) -> None:
    profile = CandidateProfile(
        user_id=test_user.id,
        display_name="Alice Candidate",
        revision=2,
        email="personal@example.com",
        phone="+41 79 000 0000",
        preferences={"target_roles": ["Python Dev"], "preferred_languages": ["en"]},
    )
    db_session.add(profile)
    db_session.flush()

    fact1 = CareerFact(
        profile_id=profile.id,
        fact_type="experience",
        verification_status="confirmed",
        position=1,
        payload={
            "role": "Senior Engineer",
            "organization": "Fictional Corp",
            "description": "Contact boss at manager@corp.com or +41 79 111 2233.",
            "skills": ["Python", "SQL"],
        },
    )
    # Draft fact should NOT be included in snapshot!
    fact2 = CareerFact(
        profile_id=profile.id,
        fact_type="skill",
        verification_status="draft",
        position=2,
        payload={"title": "Unconfirmed skill"},
    )
    db_session.add_all([fact1, fact2])

    first_seen = datetime.now(UTC) - timedelta(days=5)
    last_seen = datetime.now(UTC) - timedelta(minutes=5)
    scraped = ScrapedJob(
        platform="manual",
        platform_job_id=f"manual-test-{test_user.id}-1",
        title="Senior Python Engineer",
        company="TechCorp",
        external_url="https://techcorp.com/jobs/1",
        description="Great job in Zurich. Email hr@techcorp.com",
        content_revision=3,
        first_seen_at=first_seen,
        last_seen_at=last_seen,
        last_changed_at=first_seen,
    )
    db_session.add(scraped)
    db_session.flush()

    job = Job(
        user_id=test_user.id,
        scraped_job_id=scraped.id,
    )
    db_session.add(job)
    db_session.commit()

    context, digest, revisions = build_context_snapshot(
        db_session,
        user_id=test_user.id,
        request_id="req-123",
        work_kind="analyze",
        instruction="Check fit for role",
        target_job_id=job.id,
    )

    assert context.request_id == "req-123"
    assert len(context.facts) == 1
    assert context.facts[0].id == fact1.id
    assert "manager@corp.com" not in context.facts[0].description
    assert "[REDACTED_EMAIL]" in context.facts[0].description
    assert "+41 79 111 2233" not in context.facts[0].description
    assert "[REDACTED_PHONE]" in context.facts[0].description

    assert context.target_job is not None
    assert context.target_job.title == "Senior Python Engineer"
    assert context.target_job.observed_at == last_seen
    assert revisions["profile"] == 2
    assert revisions["job"] == 3
    assert len(digest) == 64


def test_recursive_redaction_preserves_dates_and_metrics():
    from backend.agent_work.context import _sanitize_attributes

    value = {
        "items": [
            {
                "email": "private@example.com",
                "phone": "+41 79 111 2233",
                "notes": [{"text": "Mail private@example.com"}],
            }
        ],
        "history": "2019-2024",
        "result": "EUR 250000",
    }
    result = _sanitize_attributes(value)
    assert "private@example.com" not in str(result) and "+41" not in str(result)
    assert result["history"] == "2019-2024" and result["result"] == "EUR 250000"


def test_empty_selected_facts_means_no_disclosure(db_session, test_user):
    from tests.backend.agent_work.helpers import make_work

    work, _, _, fact = make_work(db_session, test_user.id, "analyze")
    context, _, _ = build_context_snapshot(
        db_session,
        user_id=test_user.id,
        request_id=work.id,
        work_kind="analyze",
        instruction="Synthetic",
        target_job_id=work.target_job_id,
        selected_fact_ids=[],
    )
    assert context.facts == []


def test_private_reference_is_omitted_even_when_confirmed(db_session, test_user):
    from tests.backend.agent_work.helpers import make_work

    work, _, _, fact = make_work(db_session, test_user.id, "analyze")
    db_session.add(
        CareerFact(
            profile_id=fact.profile_id,
            fact_type="reference",
            verification_status="confirmed",
            position=2,
            payload={"name": "Private Person", "email": "private@example.com"},
        )
    )
    db_session.commit()
    context, _, _ = build_context_snapshot(
        db_session,
        user_id=test_user.id,
        request_id=work.id,
        work_kind="analyze",
        instruction="Synthetic",
        target_job_id=work.target_job_id,
    )
    assert len(context.facts) == 2 and "Private Person" not in context.model_dump_json()


def test_context_rejects_oversize_without_silently_cutting_evidence(db_session, test_user):
    import pytest

    from backend.agent_work.service import AgentWorkError
    from tests.backend.agent_work.helpers import make_work

    work, _, _, fact = make_work(db_session, test_user.id, "analyze")
    fact.payload = {
        **fact.payload,
        "technologies": ["technology" + str(i) + ("x" * 850) for i in range(100)],
    }
    db_session.commit()
    with pytest.raises(AgentWorkError):
        build_context_snapshot(
            db_session,
            user_id=test_user.id,
            request_id=work.id,
            work_kind="analyze",
            instruction="Synthetic",
            target_job_id=work.target_job_id,
        )


def test_canonical_preferences_are_disclosed_without_extra_private_fields(db_session, test_user):
    from tests.backend.agent_work.helpers import make_work

    work, _, _, fact = make_work(db_session, test_user.id, "analyze")
    profile = db_session.get(CandidateProfile, fact.profile_id)
    profile.preferences = {
        "preferred_languages": ["de"],
        "preferred_locations": ["Zurich"],
        "preferred_work_modes": ["hybrid"],
        "notice_period_days": 30,
        "available_from": "2026-12-01",
        "workload_min": 80,
        "private_notes": "do not disclose",
    }
    db_session.commit()
    context, _, _ = build_context_snapshot(
        db_session,
        user_id=test_user.id,
        request_id=work.id,
        work_kind="analyze",
        instruction="Synthetic",
        target_job_id=work.target_job_id,
    )
    assert context.preferences["notice_period_days"] == 30 and context.preferences[
        "preferred_languages"
    ] == ["de"]
    assert (
        context.preferences["available_from"] == "2026-12-01"
        and "private_notes" not in context.preferences
    )
