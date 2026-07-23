from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from backend.jobs.matching import deterministic_job_prefilter
from backend.jobs.urls import UnsafeJobUrlError, normalize_job_url
from backend.models import ScrapedJob
from backend.schemas.job import JobCreate, JobResponse
from backend.services.search.persistence import SearchPipelinePersistence


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://user:secret@example.test/job",
        "https://example.test/job\nX-Evil: yes",
        "//example.test/job",
        "not-a-url",
    ],
)
def test_job_url_rejects_unsafe_values(value):
    with pytest.raises(UnsafeJobUrlError):
        normalize_job_url(value)


def test_job_schema_normalizes_safe_urls_and_rejects_unsafe_application_url():
    job = JobCreate(
        title="Local Engineer",
        company="Example",
        external_url=" HTTPS://Example.TEST/jobs/1#tracking ",
    )
    assert job.external_url == "https://example.test/jobs/1"
    assert normalize_job_url("https://example.test/jobs/../jobs/2#apply") == (
        "https://example.test/jobs/2"
    )
    with pytest.raises(ValidationError):
        JobCreate(
            title="Local Engineer",
            company="Example",
            external_url="https://example.test/jobs/1",
            application_url="data:text/html,unsafe",
        )


def test_changed_job_snapshot_clears_stale_normalization_and_keeps_raw_metadata():
    repository = MagicMock()
    existing = ScrapedJob(
        id=42,
        platform="fixture",
        platform_job_id="job-1",
        title="Old title",
        company="Old company",
        description="Old description",
        external_url="https://example.test/old",
        content_fingerprint="old-fingerprint",
        normalization_status="normalized",
        normalized_domain="finance",
        normalized_seniority="senior",
        normalized_required_skills=["legacy-only"],
        normalized_metadata={"stale": True},
    )
    repository.get_scraped_job_by_platform_and_id.return_value = existing
    service = SearchPipelinePersistence(MagicMock(), repository)
    listing = SimpleNamespace(
        source="fixture",
        id="job-1",
        title="New local role",
        external_url="https://example.test/new",
        application={"form_url": "https://example.test/apply", "email": "hr@example.test"},
        raw_data={"source_revision": 2},
        _source_query="local fixture",
    )

    record, created = service.upsert_scraped_job(
        listing,
        bootstrap_normalized_job_data_fn=lambda *_args, **_kwargs: {
            "normalization_status": "provider_bootstrap",
            "normalized_domain": "general",
            "normalized_metadata": {"bootstrap": True},
        },
        extract_listing_description_text_fn=lambda _listing: "New description",
        extract_company_name_fn=lambda _listing: "New company",
        extract_listing_location_string_fn=lambda _listing: "Zurich",
        extract_listing_workload_string_fn=lambda _listing: "80-100%",
        parse_listing_publication_date_fn=lambda *_args: None,
    )

    assert not created
    assert record.title == "New local role"
    assert record.external_url == "https://example.test/new"
    assert record.application_url == "https://example.test/apply"
    assert record.raw_metadata == {"source_revision": 2}
    assert record.normalization_status == "provider_bootstrap"
    assert record.normalized_domain == "general"
    assert record.normalized_seniority is None
    assert record.normalized_required_skills is None
    assert record.normalized_metadata["bootstrap"] is True
    assert "content_changed_at" in record.normalized_metadata


def test_catalog_rejects_listing_without_safe_external_url():
    repository = MagicMock()
    repository.get_scraped_job_by_platform_and_id.return_value = None
    service = SearchPipelinePersistence(MagicMock(), repository)
    listing = SimpleNamespace(source="fixture", id="job-1", title="Unsafe", external_url="x")
    with pytest.raises(UnsafeJobUrlError):
        service.upsert_scraped_job(
            listing,
            bootstrap_normalized_job_data_fn=lambda *_args, **_kwargs: {},
            extract_listing_description_text_fn=lambda _listing: "Description",
            extract_company_name_fn=lambda _listing: "Company",
            extract_listing_location_string_fn=lambda _listing: "Zurich",
            extract_listing_workload_string_fn=lambda _listing: "100%",
            parse_listing_publication_date_fn=lambda *_args: None,
        )


def test_deterministic_prefilter_is_stable_without_masquerading_as_analysis():
    job = {
        "domain": "it",
        "seniority": "senior",
        "required_skills": ["python", "sql", "kubernetes"],
        "experience_min_years": 5,
        "required_languages": [{"code": "en"}],
    }
    profile = {
        "intent_domain": "it",
        "intent_seniority": "senior",
        "skills": ["python", "sql"],
        "experience_years": 8,
        "languages": [{"code": "en", "level": "C2"}],
        "fact_ids": ["fact-b", "fact-a"],
    }
    first = deterministic_job_prefilter(job, profile)
    second = deterministic_job_prefilter(job, profile)
    assert first == second
    assert first["kind"] == "deterministic_prefilter"
    assert first["prescore"] >= 60
    assert first["unconfirmed_skills"] == ["kubernetes"]
    assert "affinity_analysis" not in first
    assert "analysis_structured" not in first


def test_invalid_job_response_clears_all_analysis_values_and_receipt_metadata():
    response = JobResponse.model_validate(
        {
            "id": 7,
            "scraped_job_id": 17,
            "title": "Untrusted local result",
            "company": "Example",
            "external_url": "https://example.test/jobs/17",
            "applied": False,
            "created_at": datetime.now(timezone.utc),
            "affinity_score": 100,
            "affinity_analysis": "Forged fit",
            "worth_applying": True,
            "skill_match_score": 100,
            "analysis_structured": {
                "recommendation": "strong_fit",
                "evidence_citations": [
                    {
                        "type": "skill",
                        "assessment": "strength",
                        "job_evidence_id": "job:0",
                        "candidate_evidence_id": "candidate:profile",
                        "job_quote_id": "job:0:skill:0",
                        "candidate_quote_id": "candidate:profile:skill:0",
                        "job_quote_hash": "a" * 64,
                        "candidate_quote_hash": "b" * 64,
                        "job_evidence": "Python services",
                        "candidate_evidence": "Python services",
                    }
                ],
            },
            "analysis_provenance": "local_model_validated",
            "analysis_model_id": "ollama/forged",
            "analysis_contract_version": "1.1.0",
            "analysis_validated_at": datetime.now(timezone.utc),
            "analysis_execution_id": "11111111-1111-1111-1111-111111111111",
            "analysis_output_fingerprint": "c" * 64,
            "analysis_execution_row_index": 0,
            "analysis_row_fingerprint": "d" * 64,
            "analysis_input_fingerprint": "e" * 64,
            "analysis_verified": True,
            "red_flags": ["forged"],
        }
    )

    assert response.analysis_verified is False
    assert response.affinity_score is None
    assert response.affinity_analysis is None
    assert response.worth_applying is False
    assert response.analysis_structured is None
    assert response.red_flags is None
    assert response.analysis_provenance is None
    assert response.analysis_model_id is None
    assert response.analysis_contract_version is None
    assert response.analysis_validated_at is None
    assert response.analysis_execution_id is None
    assert response.analysis_output_fingerprint is None
    assert response.analysis_execution_row_index is None
    assert response.analysis_row_fingerprint is None
    assert response.analysis_input_fingerprint is None
