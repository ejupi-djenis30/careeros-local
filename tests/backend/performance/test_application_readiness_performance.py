from __future__ import annotations

import json
import math
import os
import time
from tempfile import TemporaryDirectory

import pytest

from backend.applications.models import Application
from backend.applications.readiness import ApplicationReadinessService
from backend.career.models import CandidateProfile, CareerFact
from backend.resumes.models import ResumeDraft
from backend.resumes.publishing import publish_draft

FACT_COUNT = 300
SAMPLES = 30
P95_BUDGET_MS = 100.0

pytestmark = [
    pytest.mark.performance,
    pytest.mark.skipif(
        os.getenv("RUN_PERFORMANCE_TESTS") != "1",
        reason="set RUN_PERFORMANCE_TESTS=1 to execute readiness performance budgets",
    ),
]


def _p95_ms(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


def _fact(position: int) -> CareerFact:
    fixtures = (
        (
            "experience",
            {
                "role": "Principal Engineer",
                "organization": "Local Systems",
                "description": "Led reliable local platform delivery.",
                "achievements": ["Reduced deployment lead time by 40%."],
                "metrics": ["40%"],
            },
        ),
        (
            "education",
            {
                "qualification": "BSc Computer Science",
                "institution": "Technical University",
                "field": "Distributed systems",
            },
        ),
        (
            "achievement",
            {"title": "Delivery improvement", "metric_value": "40%"},
        ),
        (
            "project",
            {"name": "Local Platform", "description": "Private offline-first tooling."},
        ),
        (
            "certification",
            {"name": "Systems Architecture"},
        ),
    )
    fact_type, payload = fixtures[position] if position < len(fixtures) else (
        "skill",
        {"name": f"Engineering skill {position}", "evidence_fact_ids": []},
    )
    return CareerFact(
        fact_type=fact_type,
        position=position,
        verification_status="confirmed",
        payload=payload,
    )


def _canvas(experience_fact_id: str) -> dict:
    return {
        "schema_version": 2,
        "style": {
            "font_family": "Helvetica",
            "base_font_size": 10,
            "line_height": 1.3,
            "section_spacing": 10,
            "margin_mm": 18,
            "accent_color": "#243B53",
            "columns": 1,
        },
        "sections": [
            {
                "id": "identity",
                "kind": "identity",
                "title": "IDENTITY",
                "visible": True,
                "page_break_before": False,
                "blocks": [
                    {
                        "id": "identity-main",
                        "kind": "identity",
                        "fact_ids": [],
                        "visible": True,
                        "content": {
                            "title": "Performance Candidate",
                            "subtitle": "Principal Engineer",
                            "date_range": "",
                            "description": "candidate@example.test",
                            "bullets": [],
                        },
                        "manual_fields": [],
                        "layout": {"spacing_before_pt": 0, "keep_together": True},
                    }
                ],
            },
            {
                "id": "experience",
                "kind": "experience",
                "title": "EXPERIENCE",
                "visible": True,
                "page_break_before": False,
                "blocks": [
                    {
                        "id": "experience-main",
                        "kind": "fact",
                        "fact_ids": [experience_fact_id],
                        "visible": True,
                        "content": {
                            "title": "Principal Engineer",
                            "subtitle": "Local Systems",
                            "date_range": "2021 – Present",
                            "description": "Led reliable local platform delivery.",
                            "bullets": ["Reduced deployment lead time by 40%."],
                        },
                        "manual_fields": [],
                        "layout": {"spacing_before_pt": 0, "keep_together": True},
                    }
                ],
            },
        ],
    }


def test_verified_application_readiness_under_100ms_p95(
    db_session, test_user, monkeypatch, capsys
):
    with TemporaryDirectory(
        prefix="careeros-readiness-performance-", ignore_cleanup_errors=True
    ) as data_dir:
        monkeypatch.setattr("backend.storage.atomic.settings.DATA_DIR", data_dir)
        profile = CandidateProfile(
            user_id=test_user.id,
            revision=7,
            display_name="Performance Candidate",
            headline="Principal Engineer",
            summary="Builds dependable local systems and develops engineering teams.",
            email="candidate@example.test",
            location={"city": "Zurich", "country": "CH"},
            work_authorization=["CH"],
            preferences={
                "target_roles": ["Principal Engineer"],
                "target_industries": ["Software"],
                "preferred_work_modes": ["hybrid"],
                "salary_min_chf": 150000,
            },
        )
        profile.facts = [_fact(position) for position in range(FACT_COUNT)]
        db_session.add(profile)
        db_session.flush()
        selected_fact_ids = [fact.id for fact in profile.facts]
        draft = ResumeDraft(
            profile_id=profile.id,
            revision=1,
            profile_revision=profile.revision,
            title="Performance application",
            template_kind="ats",
            section_config={"order": ["experience"]},
            selected_fact_ids=selected_fact_ids,
            content_overrides={},
            canvas_document=_canvas(profile.facts[0].id),
            generation_context={"mode": "deterministic"},
        )
        db_session.add(draft)
        db_session.flush()
        version = publish_draft(
            db_session,
            profile=profile,
            draft=draft,
            facts=list(profile.facts),
            photo=None,
            photo_bytes=None,
        )
        application = Application(
            user_id=test_user.id,
            resume_version_id=version.id,
            revision=1,
            current_stage="preparing",
            job_snapshot={
                "schema_version": 1,
                "title": "Senior Platform Engineer",
                "company": "Local Systems",
                "description": (
                    "Build and operate a private local platform, document architecture decisions, "
                    "improve release reliability, support incident reviews and work with product "
                    "teams on secure measurable delivery."
                ),
                "application_url": "https://example.test/apply/platform",
            },
        )
        db_session.add(application)
        db_session.commit()
        db_session.refresh(application)
        service = ApplicationReadinessService(db_session)

        warm = service.build(test_user.id, application)
        assert warm.status == "ready"
        assert warm.completeness_score == 100

        samples: list[float] = []
        for _ in range(SAMPLES):
            db_session.expunge_all()
            started = time.perf_counter_ns()
            report = service.build(test_user.id, application)
            samples.append((time.perf_counter_ns() - started) / 1_000_000)
            assert report.status == "ready"

        result = {
            "selected_facts": FACT_COUNT,
            "verified_artifacts": ["docx", "pdf"],
            "samples": SAMPLES,
            "readiness_p95_ms": round(_p95_ms(samples), 3),
            "budget_ms": P95_BUDGET_MS,
        }
        with capsys.disabled():
            print(f"CAREEROS_READINESS_BENCHMARK={json.dumps(result, sort_keys=True)}")

        assert result["readiness_p95_ms"] < P95_BUDGET_MS
