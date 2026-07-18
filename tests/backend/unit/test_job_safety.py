from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from backend.jobs.matching import deterministic_job_match
from backend.jobs.urls import UnsafeJobUrlError, normalize_job_url
from backend.models import ScrapedJob
from backend.schemas.job import JobCreate
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


def test_deterministic_match_is_stable_and_evidence_aware():
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
    first = deterministic_job_match(job, profile)
    second = deterministic_job_match(job, profile)
    assert first == second
    assert first["affinity_score"] >= 60
    assert first["analysis_structured"]["mode"] == "deterministic_local"
    assert first["analysis_structured"]["evidence_citations"] == ["fact-a", "fact-b"]
    assert "kubernetes" in first["analysis_structured"]["gaps"][0]
