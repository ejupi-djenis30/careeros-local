from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from backend.career.models import CandidateProfile, CareerFact, CareerGoal
from backend.resumes.generator import generate_resume


def _detached_profile() -> CandidateProfile:
    return CandidateProfile(
        id=str(uuid4()),
        user_id=1,
        revision=7,
        display_name="Ada Scale",
        headline="Staff Engineer",
        summary="Builds dependable local systems.",
        location={"city": "Zurich", "country": "CH"},
        work_authorization=[],
        preferences={},
    )


def _skill(position: int, name: str) -> CareerFact:
    return CareerFact(
        id=str(uuid4()),
        profile_id="00000000-0000-0000-0000-000000000001",
        fact_type="skill",
        position=position,
        payload={"name": name, "category": "Engineering", "level": "advanced"},
        verification_status="confirmed",
    )


def _experience(position: int, role: str, year: int) -> CareerFact:
    return CareerFact(
        id=str(uuid4()),
        profile_id="00000000-0000-0000-0000-000000000001",
        fact_type="experience",
        position=position,
        payload={
            "role": role,
            "organization": f"Company {position}",
            "start_date": f"{year}-01-01",
            "end_date": f"{year}-12-31",
            "description": "Delivered reliable systems.",
        },
        verification_status="confirmed",
    )


def test_generator_is_deterministic_goal_aware_and_requires_no_model(
    client, auth_headers, db_session, detailed_profile_payload, monkeypatch
):
    second = deepcopy(detailed_profile_payload["facts"][0])
    second["position"] = 1
    second["payload"].update(
        {
            "role": "Operations Engineer",
            "organization": "Other Systems",
            "description": "Maintained internal tooling.",
            "achievements": ["Improved routine operations."],
        }
    )
    detailed_profile_payload["facts"].insert(1, second)
    saved = client.put(
        "/api/v1/career-profile", json=detailed_profile_payload, headers=auth_headers
    )
    assert saved.status_code == 200, saved.text
    db_session.expire_all()
    profile = db_session.query(CandidateProfile).one()
    facts = db_session.query(CareerFact).filter(CareerFact.profile_id == profile.id).all()
    goal = db_session.query(CareerGoal).one()

    def forbidden_model_call(*_args, **_kwargs):
        raise AssertionError("automatic resume generation must not require inference")

    monkeypatch.setattr("backend.services.llm_service.LLMService._get_provider", forbidden_model_call)
    now = datetime(2026, 7, 17, tzinfo=timezone.utc)
    first = generate_resume(profile, facts, template_kind="ats", goal=goal, generated_at=now)
    second_result = generate_resume(
        profile, reversed(facts), template_kind="ats", goal=goal, generated_at=now
    )

    assert first.canvas == second_result.canvas
    assert first.selected_fact_ids == second_result.selected_fact_ids
    experience = next(section for section in first.canvas.sections if section.kind == "experience")
    assert experience.blocks[0].content.title == "Principal Engineer"
    assert first.generation_context.mode == "deterministic"
    assert "career-goal-ranking" in first.generation_context.reason_codes
    assert all(
        block.fact_ids
        for section in first.canvas.sections
        for block in section.blocks
        if block.kind in {"summary", "fact"} and block.visible
    )


def test_generator_excludes_unconfirmed_facts(
    client, auth_headers, db_session, detailed_profile_payload
):
    detailed_profile_payload["facts"][0]["verification_status"] = "draft"
    response = client.put(
        "/api/v1/career-profile", json=detailed_profile_payload, headers=auth_headers
    )
    assert response.status_code == 200
    db_session.expire_all()
    profile = db_session.query(CandidateProfile).one()
    facts = db_session.query(CareerFact).filter(CareerFact.profile_id == profile.id).all()
    result = generate_resume(profile, facts, template_kind="ats")
    assert response.json()["facts"][0]["id"] not in result.selected_fact_ids


def test_generator_selects_targeted_facts_within_canvas_limits_and_keeps_recent_history():
    profile = _detached_profile()
    facts = [_skill(index, f"Generic skill {index}") for index in range(950)]
    relevant = _skill(951, "Privacy platform architecture")
    experiences = [
        _experience(index, f"Engineer {index}", 1995 + index) for index in range(25)
    ]
    current_relevant = _experience(999, "Staff Privacy Platform Engineer", 2025)
    facts.extend([relevant, *experiences, current_relevant])
    goal = CareerGoal(
        id=str(uuid4()),
        profile_id=profile.id,
        name="Privacy platform leadership",
        is_primary=True,
        payload={
            "target_roles": ["Staff Privacy Platform Engineer"],
            "target_industries": ["Software"],
            "target_locations": [],
            "target_seniority": ["staff"],
            "must_haves": ["privacy architecture"],
        },
    )

    result = generate_resume(profile, facts, template_kind="ats", goal=goal)

    block_count = sum(len(section.blocks) for section in result.canvas.sections)
    assert block_count <= 300
    assert len(result.selected_fact_ids) < len(facts)
    assert relevant.id in result.selected_fact_ids
    assert current_relevant.id in result.selected_fact_ids
    experience = next(section for section in result.canvas.sections if section.kind == "experience")
    assert experience.blocks[0].fact_ids == [current_relevant.id]
    assert "bounded-fact-selection" in result.generation_context.reason_codes
