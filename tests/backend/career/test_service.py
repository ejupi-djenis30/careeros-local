import errno
import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from backend.career.completeness import analyze_profile, calculate_completeness_score
from backend.career.models import CandidateProfile, CareerFact
from backend.career.repository import CareerProfileRepository
from backend.career.schemas import CareerProfileWrite
from backend.career.service import CareerSearchSnapshotError, build_career_search_snapshot
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


def test_service_returns_deterministic_completeness_conflicts_and_evidence(client, auth_headers):
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


def test_fast_completeness_score_matches_full_profile_analysis():
    profile = _profile()

    assert calculate_completeness_score(profile) == analyze_profile(profile).completeness_score


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


def test_career_search_snapshot_is_deterministic_bounded_and_private():
    confirmed_skill = CareerFact(
        id="20000000-0000-4000-8000-000000000001",
        profile_id="30000000-0000-4000-8000-000000000001",
        fact_type="skill",
        position=0,
        verification_status="confirmed",
        payload={"name": "Python", "level": "advanced"},
    )
    confirmed_experience = CareerFact(
        id="20000000-0000-4000-8000-000000000002",
        profile_id="30000000-0000-4000-8000-000000000001",
        fact_type="experience",
        position=1,
        verification_status="confirmed",
        payload={
            "role": "Platform Engineer",
            "organization": "Example Systems",
            "email": "private@example.test",
            "contactEmail": "camel@example.test",
            "phone": "+41 79 111 22 33",
            "portfolioUrl": "https://private.example.test/profile",
            "nationality": "Swiss",
            "nationalité": "Suisse",
            "description": (
                "Contact private@example.test or +41 79 111 22 33. "
                "Visit https://private.example.test/profile. "
            )
            + ("Reliable delivery. " * 2_000),
        },
    )
    draft = CareerFact(
        id="20000000-0000-4000-8000-000000000003",
        profile_id="30000000-0000-4000-8000-000000000001",
        fact_type="education",
        position=2,
        verification_status="draft",
        payload={"institution": "Draft University", "qualification": "Draft"},
    )
    archived = CareerFact(
        id="20000000-0000-4000-8000-000000000004",
        profile_id="30000000-0000-4000-8000-000000000001",
        fact_type="project",
        position=3,
        verification_status="confirmed",
        archived_at=datetime.now(timezone.utc),
        payload={"name": "Archived project", "description": "Do not include"},
    )
    reference = CareerFact(
        id="20000000-0000-4000-8000-000000000005",
        profile_id="30000000-0000-4000-8000-000000000001",
        fact_type="reference",
        position=4,
        verification_status="confirmed",
        payload={"name": "Private Person", "email": "reference@example.test"},
    )
    profile = CandidateProfile(
        id="30000000-0000-4000-8000-000000000001",
        user_id=7,
        revision=4,
        display_name="Private Name",
        headline="Platform engineer · mira@example.test",
        summary="Builds dependable systems. Nationality: Swiss",
        preferences={
            "target_roles": ["Staff Engineer"],
            "preferred_work_modes": ["hybrid"],
            "job_source_consents": {"job_room": True},
            "contact_email": "prefs@example.test",
        },
        facts=[reference, archived, confirmed_experience, draft, confirmed_skill],
    )

    first = build_career_search_snapshot(profile)
    second = build_career_search_snapshot(profile)
    document = json.loads(first.text)

    assert first == second
    assert first.fact_ids == (confirmed_skill.id, confirmed_experience.id)
    assert first.profile_revision == 4
    assert first.sha256 == second.sha256
    assert len(first.text) <= 32_000
    assert document["included_fact_count"] == 2
    assert [item["id"] for item in document["facts"]] == list(first.fact_ids)
    assert document["preferences"] == {
        "preferred_work_modes": ["hybrid"],
        "target_roles": ["Staff Engineer"],
    }
    assert "Private Name" not in first.text
    assert "private@example.test" not in first.text
    assert "camel@example.test" not in first.text
    assert "reference@example.test" not in first.text
    assert "+41 79 111 22 33" not in first.text
    assert "https://private.example.test/profile" not in first.text
    assert "Swiss" not in first.text
    assert "Suisse" not in first.text
    assert "Draft University" not in first.text
    assert "Archived project" not in first.text


def test_career_search_snapshot_redacts_phone_formats_without_erasing_metrics():
    description = (
        "Reach me on 079 123 45 67; international 0041 79 123 45 67; "
        "office (079) 123-45-67; dotted 079.123.45.67; "
        "alternate +41 (0)79 / 123 45 67; US (415) 555-2671; "
        "compact 0791234567. Tenure 2019-2024; "
        "migration window 2026-07-26 12.30; European date 26.07.2026 12.30; "
        "annual volume 1 000 000 000 requests; "
        "ISO 9001 27001; processed 1234567890 records; availability 99.95 / 99.99%."
    )
    fact = CareerFact(
        id="20000000-0000-4000-8000-000000000020",
        profile_id="30000000-0000-4000-8000-000000000020",
        fact_type="experience",
        position=0,
        verification_status="confirmed",
        payload={"role": "Platform Engineer", "description": description},
    )
    profile = CandidateProfile(
        id="30000000-0000-4000-8000-000000000020",
        user_id=20,
        revision=1,
        headline="Platform Engineer",
        summary="Seven years of hands-on delivery.",
        facts=[fact],
    )

    snapshot = build_career_search_snapshot(profile)
    sanitized = json.loads(snapshot.text)["facts"][0]["payload"]["description"]

    for phone in (
        "079 123 45 67",
        "0041 79 123 45 67",
        "(079) 123-45-67",
        "079.123.45.67",
        "+41 (0)79 / 123 45 67",
        "(415) 555-2671",
        "0791234567",
    ):
        assert phone not in sanitized
    assert sanitized.count("[redacted-contact]") == 7
    for metric in (
        "2019-2024",
        "2026-07-26 12.30",
        "26.07.2026 12.30",
        "1 000 000 000 requests",
        "ISO 9001 27001",
        "1234567890 records",
        "99.95 / 99.99%",
    ):
        assert metric in sanitized


def test_career_search_snapshot_caps_fact_count_and_complete_document_size():
    profile_id = "30000000-0000-4000-8000-000000000003"
    facts = [
        CareerFact(
            id=f"40000000-0000-4000-8000-{index:012d}",
            profile_id=profile_id,
            fact_type="project",
            position=index,
            verification_status="confirmed",
            payload={
                "name": f"Project {index}",
                "description": "Evidence " * 300,
            },
        )
        for index in range(200)
    ]
    profile = CandidateProfile(
        id=profile_id,
        user_id=9,
        revision=1,
        display_name="Private Name",
        headline="Platform engineer",
        summary="Builds local systems.",
        preferences={},
        facts=list(reversed(facts)),
    )

    snapshot = build_career_search_snapshot(profile)
    document = json.loads(snapshot.text)

    assert len(snapshot.text) <= 32_000
    assert document["eligible_fact_count"] == 200
    assert 0 < document["included_fact_count"] <= 128
    assert len(document["facts"]) == document["included_fact_count"]
    assert list(snapshot.fact_ids) == [fact.id for fact in facts[: len(snapshot.fact_ids)]]
    assert [fact["id"] for fact in document["facts"]] == list(snapshot.fact_ids)


def test_career_search_snapshot_requires_usable_confirmed_fact():
    profile = CandidateProfile(
        id="30000000-0000-4000-8000-000000000002",
        user_id=8,
        revision=1,
        display_name="Private Name",
        headline="",
        summary="",
        preferences={},
        facts=[
            CareerFact(
                id="20000000-0000-4000-8000-000000000006",
                profile_id="30000000-0000-4000-8000-000000000002",
                fact_type="skill",
                position=0,
                verification_status="draft",
                payload={"name": "Python", "level": "advanced"},
            )
        ],
    )

    with pytest.raises(CareerSearchSnapshotError, match="at least one confirmed"):
        build_career_search_snapshot(profile)
