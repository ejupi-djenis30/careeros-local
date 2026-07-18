from __future__ import annotations

import math
import os
from time import perf_counter
from uuid import uuid4

import pytest

from backend.career.models import CandidateProfile, CareerFact
from backend.resumes.generator import generate_resume

FACT_COUNT = 1_000
GENERATION_BUDGET_MS = 500.0
READ_BUDGET_MS = 200.0
READ_SAMPLES = 30

pytestmark = [
    pytest.mark.performance,
    pytest.mark.skipif(
        os.getenv("RUN_PERFORMANCE_TESTS") != "1",
        reason="set RUN_PERFORMANCE_TESTS=1 to execute resume performance budgets",
    ),
]


def test_deterministic_generation_of_1000_facts_under_500ms():
    profile = CandidateProfile(
        id=str(uuid4()),
        user_id=1,
        revision=1,
        display_name="Performance Profile",
        headline="Local-first engineer",
        summary="Builds private local systems.",
        location={},
        work_authorization=[],
        preferences={},
    )
    facts = [
        CareerFact(
            id=str(uuid4()),
            profile_id=profile.id,
            fact_type="skill",
            position=index,
            payload={
                "name": f"Skill {index}",
                "category": "Engineering",
                "level": "advanced",
                "years": float(index % 20),
            },
            verification_status="confirmed",
        )
        for index in range(FACT_COUNT)
    ]

    started = perf_counter()
    result = generate_resume(profile, facts, template_kind="ats")
    elapsed_ms = (perf_counter() - started) * 1000

    assert elapsed_ms < GENERATION_BUDGET_MS
    assert len(result.selected_fact_ids) <= 298
    assert sum(len(section.blocks) for section in result.canvas.sections) <= 300


def _p95_ms(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


def test_detailed_resume_reads_under_200ms_p95(client, auth_headers):
    profile = client.put(
        "/api/v1/career-profile",
        json={
            "expected_revision": 0,
            "display_name": "Read Benchmark",
            "headline": "Local performance engineer",
            "summary": "Measures detailed resume reads locally.",
            "preferences": {},
            "goals": [],
            "facts": [
                {
                    "fact_type": "skill",
                    "position": index,
                    "verification_status": "confirmed",
                    "payload": {
                        "name": f"Benchmark skill {index}",
                        "category": "Engineering",
                        "level": "advanced",
                    },
                }
                for index in range(100)
            ],
        },
        headers=auth_headers,
    )
    assert profile.status_code == 200, profile.text
    created = client.post(
        "/api/v1/resumes/generate",
        json={"title": "Read performance", "template_kind": "ats"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    resume_id = created.json()["id"]
    for _ in range(3):
        assert client.get(f"/api/v1/resumes/{resume_id}", headers=auth_headers).status_code == 200

    samples = []
    for _ in range(READ_SAMPLES):
        started = perf_counter()
        response = client.get(f"/api/v1/resumes/{resume_id}", headers=auth_headers)
        samples.append((perf_counter() - started) * 1000)
        assert response.status_code == 200
        assert response.json()["canvas_document"]["sections"]

    assert _p95_ms(samples) < READ_BUDGET_MS
