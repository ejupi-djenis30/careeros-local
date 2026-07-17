from copy import deepcopy

import pytest
from pydantic import ValidationError

from backend.career.schemas import CareerGoalInput, CareerProfileWrite

EXPERIENCE_ID = "10000000-0000-4000-8000-000000000001"
SKILL_ID = "10000000-0000-4000-8000-000000000002"


def _payload() -> dict:
    return {
        "expected_revision": 0,
        "display_name": "Grace Hopper",
        "headline": "Engineering leader",
        "summary": "Builds teams and dependable compilers.",
        "preferences": {"workload_min": 80, "workload_max": 100},
        "facts": [
            {
                "fact_type": "experience",
                "verification_status": "confirmed",
                "payload": {
                    "role": "Director",
                    "organization": "Local Computing",
                    "employment_type": "permanent",
                    "industry": "Software",
                    "work_mode": "hybrid",
                    "start_date": "2020-01-01",
                    "current": True,
                    "responsibilities": ["Set direction"],
                    "achievements": ["Shortened release cycles by 30%."],
                    "metrics": ["30% faster"],
                    "technologies": ["Python"],
                    "skills": ["Leadership"],
                    "team_size": 20,
                },
            },
            {
                "fact_type": "education",
                "payload": {
                    "institution": "Yale",
                    "qualification": "PhD",
                    "field": "Mathematics",
                    "thesis": "New Types of Irreducibility Criteria",
                    "activities": ["Mathematics society"],
                    "coursework": ["Applied mathematics"],
                },
            },
            {
                "fact_type": "project",
                "payload": {
                    "name": "Compiler platform",
                    "role": "Lead",
                    "organization": "Local Computing",
                    "client": "Internal",
                    "technologies": ["Python", "LLVM"],
                    "skills": ["Compilers"],
                },
            },
            {
                "fact_type": "skill",
                "payload": {
                    "name": "Compilers",
                    "category": "Engineering",
                    "level": "expert",
                    "years": 12,
                    "last_used_date": "2026-07-01",
                },
            },
        ],
        "goals": [
            {
                "name": "VP Engineering",
                "is_primary": True,
                "payload": {
                    "status": "active",
                    "priority": 1,
                    "target_roles": ["VP Engineering"],
                    "target_industries": ["Developer tools"],
                    "target_seniority": ["executive"],
                    "target_locations": ["Switzerland"],
                    "work_modes": ["hybrid"],
                    "contract_types": ["permanent"],
                    "compensation": {
                        "currency": "CHF",
                        "minimum": 180000,
                        "maximum": 240000,
                        "period": "year",
                    },
                    "must_haves": ["Product influence"],
                    "deal_breakers": ["Weekly flights"],
                    "skill_gaps": [
                        {
                            "skill": "Board reporting",
                            "current_level": "working",
                            "target_level": "advanced",
                            "action": "Own quarterly reporting",
                        }
                    ],
                    "milestones": [
                        {
                            "id": "board-report",
                            "title": "Present a board report",
                            "status": "planned",
                            "target_date": "2026-12-01",
                        }
                    ],
                    "progress_notes": [
                        {"recorded_at": "2026-07-17T10:00:00Z", "text": "Started mentoring."}
                    ],
                },
            }
        ],
    }


def test_detailed_profile_round_trips_all_career_dimensions(client, auth_headers):
    response = client.put("/api/v1/career-profile", json=_payload(), headers=auth_headers)
    assert response.status_code == 200, response.text
    profile = response.json()

    experience = profile["facts"][0]["payload"]
    assert experience["employment_type"] == "permanent"
    assert experience["technologies"] == ["Python"]
    assert experience["team_size"] == 20
    assert profile["facts"][1]["payload"]["thesis"].startswith("New Types")
    assert profile["facts"][2]["payload"]["client"] == "Internal"
    assert profile["facts"][3]["payload"]["last_used_date"] == "2026-07-01"
    goal = profile["goals"][0]["payload"]
    assert goal["status"] == "active"
    assert goal["compensation"]["currency"] == "CHF"
    assert goal["milestones"][0]["id"] == "board-report"


def test_goal_compensation_and_completed_milestones_are_validated():
    with pytest.raises(ValidationError, match="minimum cannot exceed maximum"):
        CareerGoalInput(
            name="Invalid compensation",
            payload={
                "compensation": {
                    "currency": "CHF",
                    "minimum": 200000,
                    "maximum": 100000,
                }
            },
        )

    with pytest.raises(ValidationError, match="completed_date"):
        CareerGoalInput(
            name="Invalid milestone",
            payload={
                "milestones": [
                    {"id": "promotion", "title": "Earn promotion", "status": "achieved"}
                ]
            },
        )


def test_invalid_nested_profile_write_is_atomic(client, auth_headers):
    initial = client.put("/api/v1/career-profile", json=_payload(), headers=auth_headers)
    assert initial.status_code == 200
    before = initial.json()
    update = deepcopy(_payload())
    update["expected_revision"] = before["revision"]
    for index, fact in enumerate(update["facts"]):
        fact["id"] = before["facts"][index]["id"]
    update["goals"][0]["id"] = before["goals"][0]["id"]
    update["facts"][1]["payload"]["end_date"] = "2010-01-01"
    update["facts"][1]["payload"]["start_date"] = "2012-01-01"

    rejected = client.put("/api/v1/career-profile", json=update, headers=auth_headers)
    assert rejected.status_code == 422
    current = client.get("/api/v1/career-profile", headers=auth_headers).json()
    assert current["revision"] == before["revision"]
    assert current["facts"] == before["facts"]


def test_profile_rejects_multiple_primary_goals():
    payload = _payload()
    payload["goals"].append(deepcopy(payload["goals"][0]))
    payload["goals"][1]["name"] = "Second"
    with pytest.raises(ValidationError, match="only one career goal"):
        CareerProfileWrite.model_validate(payload)


def test_skill_evidence_must_reference_a_fact_in_the_same_profile():
    payload = _payload()
    payload["facts"][0]["id"] = EXPERIENCE_ID
    payload["facts"][3]["id"] = SKILL_ID
    payload["facts"][3]["payload"]["evidence_fact_ids"] = [EXPERIENCE_ID]
    validated = CareerProfileWrite.model_validate(payload)
    assert validated.facts[3].payload["evidence_fact_ids"] == [EXPERIENCE_ID]
    payload["facts"][3]["payload"]["evidence_fact_ids"] = [
        "90000000-0000-4000-8000-000000000009"
    ]
    with pytest.raises(ValidationError, match="evidence facts must belong"):
        CareerProfileWrite.model_validate(payload)
