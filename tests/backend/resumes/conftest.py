from __future__ import annotations

from copy import deepcopy

import pytest


@pytest.fixture
def detailed_profile_payload() -> dict:
    return {
        "expected_revision": 0,
        "display_name": "Mira Vale",
        "headline": "Principal Software Engineer",
        "summary": "Builds dependable systems and develops engineering teams.",
        "email": "mira@example.test",
        "phone": "+41 79 000 00 00",
        "location": {"city": "Zurich", "country": "CH"},
        "website": "https://mira.example.test",
        "preferences": {
            "workload_min": 80,
            "workload_max": 100,
            "preferred_languages": ["en", "it"],
        },
        "facts": [
            {
                "fact_type": "experience",
                "position": 0,
                "verification_status": "confirmed",
                "payload": {
                    "role": "Principal Engineer",
                    "organization": "Local Systems",
                    "employment_type": "permanent",
                    "industry": "Software",
                    "work_mode": "hybrid",
                    "location": "Zurich",
                    "start_date": "2020-01-01",
                    "current": True,
                    "description": "Leads delivery of privacy-preserving platforms.",
                    "responsibilities": ["Set technical direction", "Mentor engineers"],
                    "achievements": ["Reduced deployment lead time by 40%."],
                    "metrics": ["40% faster delivery"],
                    "technologies": ["Python", "React", "SQLite"],
                    "skills": ["Architecture", "Leadership"],
                    "team_size": 12,
                },
            },
            {
                "fact_type": "education",
                "position": 1,
                "verification_status": "confirmed",
                "payload": {
                    "institution": "University of London",
                    "qualification": "BSc Mathematics",
                    "field": "Mathematics",
                    "start_date": "2012-09-01",
                    "end_date": "2015-06-30",
                    "thesis": "Computational reasoning",
                    "activities": ["Computing society"],
                    "coursework": ["Algorithms", "Statistics"],
                },
            },
            {
                "fact_type": "skill",
                "position": 2,
                "verification_status": "confirmed",
                "payload": {
                    "name": "Python",
                    "category": "Engineering",
                    "level": "expert",
                    "years": 10,
                    "last_used_date": "2026-07-01",
                },
            },
        ],
        "goals": [
            {
                "name": "Engineering leadership",
                "is_primary": True,
                "payload": {
                    "status": "active",
                    "priority": 1,
                    "target_roles": ["Staff Engineer", "Engineering Manager"],
                    "target_industries": ["Software"],
                    "target_locations": ["Switzerland"],
                    "target_seniority": ["staff", "lead"],
                    "work_modes": ["hybrid", "remote"],
                    "contract_types": ["permanent"],
                    "compensation": {
                        "currency": "CHF",
                        "minimum": 150000,
                        "maximum": 190000,
                        "period": "year",
                    },
                    "target_date": "2027-06-30",
                    "must_haves": ["Technical leadership"],
                    "deal_breakers": ["Mandatory relocation"],
                    "skill_gaps": [
                        {
                            "skill": "People management",
                            "current_level": "working",
                            "target_level": "advanced",
                            "action": "Lead a cross-functional team",
                        }
                    ],
                    "milestones": [
                        {
                            "id": "portfolio",
                            "title": "Publish leadership portfolio",
                            "status": "planned",
                            "target_date": "2026-12-31",
                        }
                    ],
                },
            }
        ],
    }


@pytest.fixture
def saved_detailed_profile(client, auth_headers, detailed_profile_payload) -> dict:
    response = client.put(
        "/api/v1/career-profile", json=deepcopy(detailed_profile_payload), headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return response.json()
