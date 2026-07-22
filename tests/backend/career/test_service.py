import errno
from copy import deepcopy

import pytest

from backend.career.repository import CareerProfileRepository
from backend.career.schemas import CareerProfileWrite
from backend.storage.atomic import StorageWriteError

EXPERIENCE_ONE = "10000000-0000-4000-8000-000000000001"
EXPERIENCE_TWO = "10000000-0000-4000-8000-000000000002"
SKILL = "10000000-0000-4000-8000-000000000003"


def _profile() -> dict:
    return {
        "expected_revision": 0,
        "display_name": "Mira Vale",
        "headline": "Principal engineer",
        "summary": "Builds private, dependable systems with measurable outcomes.",
        "email": "mira@example.test",
        "location": {"city": "Zurich", "country": "CH"},
        "preferences": {
            "target_roles": ["Staff Engineer"],
            "preferred_work_modes": ["hybrid"],
        },
        "facts": [
            {
                "id": EXPERIENCE_ONE,
                "fact_type": "experience",
                "verification_status": "confirmed",
                "payload": {
                    "role": "Principal Engineer",
                    "organization": "Private Systems",
                    "employment_type": "permanent",
                    "start_date": "2022-01-01",
                    "current": True,
                    "achievements": ["Reduced lead time by 40%."],
                },
            },
            {
                "id": EXPERIENCE_TWO,
                "fact_type": "experience",
                "verification_status": "confirmed",
                "payload": {
                    "role": "Engineering Lead",
                    "organization": "Second Systems",
                    "employment_type": "permanent",
                    "start_date": "2024-01-01",
                    "current": True,
                },
            },
            {
                "id": SKILL,
                "fact_type": "skill",
                "verification_status": "confirmed",
                "payload": {
                    "name": "Python",
                    "level": "expert",
                    "evidence_fact_ids": [EXPERIENCE_ONE],
                },
            },
            {
                "fact_type": "achievement",
                "verification_status": "draft",
                "payload": {"title": "Unverified claim"},
            },
        ],
        "goals": [
            {
                "name": "Staff engineering role",
                "is_primary": True,
                "payload": {
                    "status": "active",
                    "start_date": "2026-01-01",
                    "target_date": "2026-12-31",
                    "target_roles": ["Staff Engineer"],
                    "success_criteria": ["Sign an aligned offer"],
                    "milestones": [
                        {
                            "id": "portfolio",
                            "title": "Publish portfolio",
                            "status": "in_progress",
                            "target_date": "2026-09-30",
                        }
                    ],
                    "actions": [
                        {
                            "id": "portfolio-case",
                            "title": "Write architecture case study",
                            "status": "in_progress",
                            "due_date": "2026-08-31",
                            "linked_fact_ids": [EXPERIENCE_ONE],
                        }
                    ],
                },
            }
        ],
    }


def test_service_returns_deterministic_completeness_conflicts_and_evidence(
    client, auth_headers
):
    response = client.put("/api/v1/career-profile", json=_profile(), headers=auth_headers)
    assert response.status_code == 200, response.text
    analysis = response.json()["analysis"]
    assert 0 < analysis["completeness_score"] < 100
    assert analysis["section_scores"]["identity"] == 100
    assert "education" in analysis["missing_sections"]
    assert any(issue["code"] == "overlapping_primary_employment" for issue in analysis["issues"])
    evidence = {item["fact_id"]: item for item in analysis["evidence"]}
    assert evidence[SKILL]["state"] == "linked"
    assert EXPERIENCE_ONE in evidence[SKILL]["evidence_fact_ids"]
    assert any(item["state"] == "missing" for item in analysis["evidence"])

    fetched = client.get("/api/v1/career-profile", headers=auth_headers).json()
    assert fetched["analysis"] == analysis
    summary = client.get("/api/v1/career-profile/summary", headers=auth_headers).json()
    assert summary["completeness_score"] == analysis["completeness_score"]
    assert summary["issue_count"] == len(analysis["issues"])


def test_goal_actions_progress_and_links_round_trip(client, auth_headers):
    payload = deepcopy(_profile())
    payload["goals"][0]["payload"]["progress_percent"] = 45
    payload["goals"][0]["payload"]["progress_notes"] = [
        {
            "recorded_at": "2026-07-17T10:00:00Z",
            "text": "Portfolio outline reviewed.",
            "progress_percent": 45,
            "evidence_fact_ids": [EXPERIENCE_ONE],
        }
    ]
    response = client.put("/api/v1/career-profile", json=payload, headers=auth_headers)
    assert response.status_code == 200, response.text
    goal = response.json()["goals"][0]["payload"]
    assert goal["progress_percent"] == 45
    assert goal["actions"][0]["linked_fact_ids"] == [EXPERIENCE_ONE]
    assert goal["progress_notes"][0]["progress_percent"] == 45


def test_goal_rejects_impossible_action_and_milestone_dates(client, auth_headers):
    payload = _profile()
    payload["goals"][0]["payload"]["actions"][0].update(
        {"status": "completed", "completed_date": None}
    )
    response = client.put("/api/v1/career-profile", json=payload, headers=auth_headers)
    assert response.status_code == 422
    assert "completed_date" in response.text


def test_profile_disk_full_rolls_back_to_last_durable_revision(
    client, auth_headers, db_session, test_user, monkeypatch
):
    created = client.put("/api/v1/career-profile", json=_profile(), headers=auth_headers)
    assert created.status_code == 200, created.text
    current = created.json()
    update = deepcopy(_profile())
    update["expected_revision"] = current["revision"]
    update["headline"] = "This update must not survive"
    for position, fact in enumerate(update["facts"]):
        fact["id"] = current["facts"][position]["id"]
    update["goals"][0]["id"] = current["goals"][0]["id"]

    def disk_full_commit():
        raise OSError(errno.ENOSPC, "database or disk is full")

    monkeypatch.setattr(db_session, "commit", disk_full_commit)
    repository = CareerProfileRepository(db_session)
    with pytest.raises(StorageWriteError, match="storage is full"):
        repository.save(test_user.id, CareerProfileWrite.model_validate(update))

    db_session.expire_all()
    persisted = repository.get_by_user(test_user.id)
    assert persisted is not None
    assert persisted.revision == current["revision"]
    assert persisted.headline == current["headline"]
