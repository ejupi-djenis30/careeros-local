from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import backend.services.search_service as search_service_module
from backend.ai.audit import fingerprint_output
from backend.ai.match_evidence import (
    candidate_evidence_document,
    fingerprint_match_input_rows,
    job_evidence_document,
)
from backend.ai.match_policy import derive_match_outcome, derive_match_presentation
from backend.ai.matching import _materialize_match_citations
from backend.ai.models import AIExecution
from backend.career.models import CandidateProfile
from backend.models import Job, ScrapedJob, SearchProfile
from backend.services.search_service import SearchService
from backend.services.search_status import get_status


class FakeProvider:
    def __init__(self, items):
        self._items = list(items)
        self.throttle_delay = 0.0
        self.calls = 0

    def get_provider_info(self):
        return {
            "name": "job_room",
            "description": "Integration test provider",
            "domain": "general",
            "accepted_domains": ["*"],
        }

    async def search(self, req):
        self.calls += 1
        return SimpleNamespace(items=list(self._items), total_pages=1, total_count=len(self._items))

    async def close(self):
        return None


def make_listing(job_id: str, title: str, company: str, description: str, city: str):
    return SimpleNamespace(
        source="job_room",
        id=job_id,
        title=title,
        company=SimpleNamespace(name=company),
        descriptions=[SimpleNamespace(description=description)],
        location=SimpleNamespace(city=city, coordinates=SimpleNamespace(lat=47.3769, lon=8.5417)),
        employment=SimpleNamespace(workload_min=80, workload_max=100, work_forms=[]),
        language_skills=[],
        occupations=[],
        publication=SimpleNamespace(start_date="2024-06-01"),
        external_url=f"https://example.com/jobs/{job_id}",
        application=None,
    )


@pytest.mark.asyncio
async def test_run_search_pipeline_persists_catalog_filters_and_refines_jobs(
    db_session, test_user, monkeypatch
):
    profile = SearchProfile(
        user_id=test_user.id,
        name="Pipeline Integration",
        cv_content="Python FastAPI SQL Docker APIs integrations backend development.",
        role_description="Backend Python engineer",
        search_strategy="Focus on backend engineering roles",
        location_filter="Zurich",
        workload_filter="80-100",
        max_queries=1,
        max_occupation_queries=0,
        max_keyword_queries=1,
    )
    db_session.add(profile)
    db_session.add(
        CandidateProfile(
            user_id=test_user.id,
            display_name="Pipeline Integration",
            preferences={"job_source_consents": {"job_room": True}},
        )
    )
    db_session.commit()
    db_session.refresh(profile)

    kept_listing = make_listing(
        "dev-1",
        "Python Backend Engineer",
        "Acme Software",
        "Build APIs with Python, FastAPI and SQL. Collaborate with product and platform teams.",
        "Zurich",
    )
    filtered_listing = make_listing(
        "fin-1",
        "Senior Accountant",
        "Ledger Corp",
        "Own month-end closing, financial reporting and SAP accounting operations.",
        "Zurich",
    )

    provider = FakeProvider([kept_listing, filtered_listing])
    service = SearchService(db=db_session)
    service.analysis_readiness_check = AsyncMock(
        return_value=SimpleNamespace(ready=True, error_code=None)
    )
    service.providers = {"job_room": provider}

    profile_norm = {
        "seniority": "mid",
        "domain": "it",
        "role_family": "backend engineer",
        "qualification_level": "bachelor",
        "experience_years": 4,
        "languages": [{"code": "en", "level": "C1"}],
        "skills": ["python", "fastapi", "sql", "docker"],
        "intent_domain": "it",
        "intent_seniority": "mid",
        "intent_role_family": "backend engineer",
        "intent_qualification_level": "bachelor",
        "intent_skills": ["python", "fastapi", "sql"],
        "open_to_unrelated": False,
        "intent_keywords": ["backend", "python"],
        "role_type": "technical",
        "industry_sectors": ["software"],
        "transferable_skills": ["communication"],
        "intent_role_type": "technical",
        "intent_seniority_min": "junior",
        "intent_seniority_max": "senior",
        "dealbreakers": [],
        "flexibility": {},
    }

    async def fake_generate_search_plan(profile_dict, provider_infos, **kwargs):
        return [
            {
                "query": "Python backend engineer",
                "domain": "it",
                "type": "keyword",
                "language": "en",
            }
        ]

    async def fake_normalize_job_batch(batch):
        results = []
        for item in batch:
            if item["title"] == "Python Backend Engineer":
                results.append(
                    {
                        "confidence": 0.95,
                        "title": item["title"],
                        "role_family": "backend engineer",
                        "domain": "it",
                        "role_type": "technical",
                        "seniority": "mid",
                        "employment_mode": "onsite",
                        "contract_type": "permanent",
                        "qualification_level": "bachelor",
                        "experience_min_years": 2,
                        "experience_max_years": 5,
                        "workload_min": 80,
                        "workload_max": 100,
                        "salary_min_chf": 95000,
                        "salary_max_chf": 120000,
                        "required_languages": [{"code": "en", "level": "B2"}],
                        "required_skills": ["python", "fastapi", "sql"],
                        "education_levels": ["bachelor"],
                        "key_requirements": ["Build backend APIs"],
                        "preferred_skills": ["docker"],
                        "soft_skills": ["communication"],
                        "physical_requirements": [],
                        "entry_barrier": "medium",
                        "career_changer_friendly": False,
                        "hard_blockers": [],
                    }
                )
            else:
                results.append(
                    {
                        "confidence": 0.95,
                        "title": item["title"],
                        "role_family": "accounting",
                        "domain": "finance",
                        "role_type": "professional",
                        "seniority": "mid",
                        "employment_mode": "onsite",
                        "contract_type": "permanent",
                        "qualification_level": "bachelor",
                        "experience_min_years": 2,
                        "experience_max_years": 5,
                        "workload_min": 80,
                        "workload_max": 100,
                        "required_languages": [{"code": "en", "level": "B2"}],
                        "required_skills": ["accounting", "sap", "excel"],
                        "education_levels": ["bachelor"],
                        "key_requirements": ["Accounting operations"],
                        "preferred_skills": [],
                        "soft_skills": ["precision"],
                        "physical_requirements": [],
                        "entry_barrier": "medium",
                        "career_changer_friendly": False,
                        "hard_blockers": [],
                    }
                )
        return results

    async def fake_analyze_job_batch(jobs_metadata, profile_dict, **_audit_context):
        contract_rows = []
        for index, _item in enumerate(jobs_metadata):
            contract_rows.append(
                {
                    "skill_match_score": 79,
                    "experience_match_score": 50,
                    "intent_match_score": 88,
                    "language_match_score": 50,
                    "location_match_score": 50,
                    "transferability_score": 50,
                    "qualification_gap_score": 50,
                }
            )

        evidence = (
            candidate_evidence_document(profile_dict),
            *[
                job_evidence_document(item, index, description_limit=1800)
                for index, item in enumerate(jobs_metadata)
            ],
        )
        output_fingerprint = fingerprint_output({"results": contract_rows})
        row_fingerprints = [fingerprint_output(row) for row in contract_rows]
        input_fingerprints = fingerprint_match_input_rows(evidence)
        execution = AIExecution(
            user_id=profile_dict["user_id"],
            task="job_match",
            contract_version="1.1.0",
            model_id="llama-cpp-local/test-model",
            input_fingerprint="c" * 64,
            output_fingerprint=output_fingerprint,
            row_fingerprints=row_fingerprints,
            row_input_fingerprints=input_fingerprints,
            evidence_count=len(evidence),
            accepted=True,
            repair_count=0,
            validation_codes=[],
            duration_ms=1,
        )
        db_session.add(execution)
        db_session.commit()

        results = []
        for index, row in enumerate(contract_rows):
            dimensions = {
                "skill": row["skill_match_score"],
                "experience": row["experience_match_score"],
                "intent": row["intent_match_score"],
                "language": row["language_match_score"],
                "location": row["location_match_score"],
                "transferability": row["transferability_score"],
                "qualification": row["qualification_gap_score"],
            }
            citations = _materialize_match_citations(
                candidate=evidence[0],
                job=evidence[index + 1],
                dimension_scores=dimensions,
            )
            score, recommendation, worth = derive_match_outcome(dimensions, citations)
            summary, flags = derive_match_presentation(recommendation, citations)
            results.append(
                {
                    **row,
                    "affinity_score": score,
                    "affinity_analysis": summary,
                    "worth_applying": worth,
                    "analysis_structured": {
                        "recommendation": recommendation,
                        "evidence_citations": citations,
                    },
                    "red_flags": flags,
                    "analysis_provenance": "local_model_validated",
                    "analysis_model_id": execution.model_id,
                    "analysis_contract_version": execution.contract_version,
                    "analysis_execution_id": execution.id,
                    "analysis_output_fingerprint": output_fingerprint,
                    "analysis_execution_row_index": index,
                    "analysis_row_fingerprint": row_fingerprints[index],
                    "analysis_input_fingerprint": input_fingerprints[index],
                }
            )
        return results

    async def passthrough_description(text, max_chars):
        return text

    monkeypatch.setattr(search_service_module.settings, "SEARCH_PIPELINE_TIMEOUT_SECONDS", 30)
    monkeypatch.setattr(
        search_service_module.settings, "SEARCH_ENABLE_NORMALIZATION_MATCHING", True
    )
    monkeypatch.setattr(search_service_module.settings, "STRUCTURED_PRESCORE_ENABLED", False)
    monkeypatch.setattr(search_service_module.settings, "MATCH_CRITIQUE_ENABLED", False)
    monkeypatch.setattr(search_service_module.settings, "MATCH_RERANK_ENABLED", False)
    monkeypatch.setattr(search_service_module.settings, "SALARY_BENCHMARK_ENABLED", False)
    monkeypatch.setattr(search_service_module.llm_service, "clear_provider_cache", lambda: None)
    monkeypatch.setattr(
        search_service_module.llm_service,
        "summarize_cv",
        AsyncMock(return_value="Condensed backend CV summary"),
    )
    monkeypatch.setattr(
        search_service_module.llm_service,
        "normalize_user_profile",
        AsyncMock(return_value=profile_norm),
    )
    monkeypatch.setattr(
        search_service_module.llm_service,
        "generate_search_plan",
        AsyncMock(side_effect=fake_generate_search_plan),
    )
    monkeypatch.setattr(
        search_service_module.llm_service,
        "normalize_job_batch",
        AsyncMock(side_effect=fake_normalize_job_batch),
    )
    monkeypatch.setattr(
        search_service_module.llm_service,
        "analyze_job_batch",
        AsyncMock(side_effect=fake_analyze_job_batch),
    )
    monkeypatch.setattr(
        search_service_module.llm_service,
        "_compress_description_if_needed",
        AsyncMock(side_effect=passthrough_description),
    )
    monkeypatch.setattr(
        search_service_module.llm_service, "is_analysis_circuit_open", lambda: False
    )

    await service.run_search(
        profile.id,
        force_regenerate_cv_summary=True,
        force_regenerate_queries=True,
    )

    status = get_status(profile.id)
    assert status["state"] == "done"
    assert status["terminal_reason"] == "completed"
    assert status["jobs_new"] == 1
    assert status["jobs_skipped"] == 1
    assert provider.calls == 1

    persisted_profile = db_session.get(SearchProfile, profile.id)
    assert persisted_profile.cached_cv_summary == "Condensed backend CV summary"
    assert persisted_profile.cached_queries is not None
    assert persisted_profile.cached_profile_snapshot is not None
    assert persisted_profile.cached_profile_snapshot_fingerprint is not None
    assert persisted_profile.profile_normalization_status == "normalized"

    scraped_jobs = db_session.query(ScrapedJob).order_by(ScrapedJob.platform_job_id.asc()).all()
    assert [job.platform_job_id for job in scraped_jobs] == ["dev-1", "fin-1"]
    assert [job.normalization_status for job in scraped_jobs] == ["normalized", "normalized"]
    assert [job.normalized_domain for job in scraped_jobs] == ["it", "finance"]
    assert all(job.content_fingerprint for job in scraped_jobs)
    assert all(job.compact_description for job in scraped_jobs)

    saved_jobs = db_session.query(Job).all()
    assert len(saved_jobs) == 1
    saved_job = saved_jobs[0]
    assert saved_job.scraped_job.platform_job_id == "dev-1"
    assert saved_job.affinity_score == 65
    assert saved_job.affinity_analysis.startswith("Local evidence review: consider")
    assert saved_job.analysis_structured["recommendation"] == "consider"
    assert saved_job.analysis_provenance == "local_model_validated"
