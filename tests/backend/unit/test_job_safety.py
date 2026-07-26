from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.jobs.matching import deterministic_job_prefilter
from backend.jobs.urls import UnsafeJobUrlError, normalize_job_url
from backend.models import ScrapedJob
from backend.schemas.job import JobCreate, JobResponse
from backend.services.search.persistence import SearchPipelinePersistence
from backend.services.search.prompt_compaction import build_scraped_job_content_fingerprint


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
    first_seen = datetime(2026, 7, 1, 8, 30, tzinfo=timezone.utc)
    previous_change = datetime(2026, 7, 2, 9, 45, tzinfo=timezone.utc)
    existing = ScrapedJob(
        id=42,
        platform="fixture",
        platform_job_id="job-1",
        title="Old title",
        company="Old company",
        description="Old description",
        external_url="https://example.test/old",
        content_fingerprint="old-fingerprint",
        first_seen_at=first_seen,
        last_seen_at=previous_change,
        last_changed_at=previous_change,
        content_revision=3,
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
    assert record.first_seen_at == first_seen
    assert record.last_seen_at > previous_change
    assert record.last_changed_at == record.last_seen_at
    assert record.content_revision == 4
    assert listing._catalog_content_changed is True
    assert listing._catalog_content_revision == 4
    assert listing._catalog_content_fingerprint == record.content_fingerprint


def test_unchanged_job_observation_only_advances_last_seen():
    repository = MagicMock()
    first_seen = datetime(2026, 7, 1, 8, 30, tzinfo=timezone.utc)
    previous_seen = datetime(2026, 7, 2, 9, 45, tzinfo=timezone.utc)
    previous_change = datetime(2026, 7, 1, 8, 30, tzinfo=timezone.utc)
    listing = SimpleNamespace(
        source="fixture",
        id="job-1",
        title="Stable role",
        external_url="https://example.test/jobs/1",
        application=None,
        raw_data={"source_revision": 1},
    )
    fingerprint = build_scraped_job_content_fingerprint(
        title="Stable role",
        company="Acme",
        location="Zurich",
        workload="80-100%",
        description="Stable description",
    )
    existing = ScrapedJob(
        id=42,
        platform="fixture",
        platform_job_id="job-1",
        title="Stable role",
        company="Acme",
        description="Stable description",
        location="Zurich",
        external_url="https://example.test/jobs/1",
        workload="80-100%",
        raw_metadata={"source_revision": 1},
        content_fingerprint=fingerprint,
        first_seen_at=first_seen,
        last_seen_at=previous_seen,
        last_changed_at=previous_change,
        content_revision=2,
        normalization_status="normalized",
    )
    repository.get_scraped_job_by_platform_and_id.return_value = existing
    service = SearchPipelinePersistence(MagicMock(), repository)

    record, created = service.upsert_scraped_job(
        listing,
        bootstrap_normalized_job_data_fn=lambda *_args, **_kwargs: {},
        extract_listing_description_text_fn=lambda _listing: "Stable description",
        extract_company_name_fn=lambda _listing: "Acme",
        extract_listing_location_string_fn=lambda _listing: "Zurich",
        extract_listing_workload_string_fn=lambda _listing: "80-100%",
        parse_listing_publication_date_fn=lambda *_args: None,
    )

    assert not created
    assert record.first_seen_at == first_seen
    assert record.last_seen_at > previous_seen
    assert record.last_changed_at == previous_change
    assert record.content_revision == 2
    assert listing._catalog_content_changed is False
    assert listing._catalog_content_revision == 2
    assert listing._catalog_content_fingerprint == fingerprint


def _captured_listing(*, revision: int = 1, fingerprint: str = "a" * 64):
    return SimpleNamespace(
        source="fixture",
        id="job-1",
        title="Platform engineer",
        external_url="https://example.test/jobs/1",
        location=None,
        _catalog_persisted=True,
        _scraped_job_id=42,
        _catalog_content_revision=revision,
        _catalog_content_fingerprint=fingerprint,
    )


def _catalog_record(*, revision: int = 1, fingerprint: str = "a" * 64):
    return ScrapedJob(
        id=42,
        platform="fixture",
        platform_job_id="job-1",
        title="Platform engineer",
        company="Example",
        description="Build and operate the platform.",
        location="Zurich",
        workload="100%",
        external_url="https://example.test/jobs/1",
        content_revision=revision,
        content_fingerprint=fingerprint,
    )


def _accepted_analysis():
    return {
        "analysis_provenance": "local_model_validated",
        "analysis_model_id": "fixture/local-model",
        "analysis_contract_version": "1.1.0",
        "analysis_output_fingerprint": "b" * 64,
        "analysis_execution_row_index": 0,
        "analysis_row_fingerprint": "c" * 64,
        "analysis_input_fingerprint": "d" * 64,
    }


@pytest.mark.asyncio
async def test_save_does_not_rewrite_or_persist_an_observation_superseded_by_new_content():
    db = MagicMock()
    db.get.return_value = _catalog_record(revision=2, fingerprint="b" * 64)
    repository = MagicMock()
    service = SearchPipelinePersistence(db, repository)
    legacy_upsert = MagicMock()

    result = await service.save_single_job(
        _captured_listing(revision=1, fingerprint="a" * 64),
        _accepted_analysis(),
        {"id": 7, "user_id": 9},
        None,
        upsert_scraped_job=legacy_upsert,
        geocode_location_fn=AsyncMock(),
    )

    assert result == "stale_catalog"
    legacy_upsert.assert_not_called()
    repository.get_job_by_user_scraped_profile.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_save_accepts_an_unchanged_captured_observation_without_second_upsert():
    current = _catalog_record()
    db = MagicMock()
    db.get.return_value = current
    repository = MagicMock()
    repository.get_job_by_user_scraped_profile.return_value = SimpleNamespace()
    service = SearchPipelinePersistence(db, repository)
    legacy_upsert = MagicMock()

    with (
        patch(
            "backend.services.search.persistence.materialize_match_citations",
            return_value=[],
        ),
        patch("backend.services.search.persistence.validate_match_attestation"),
    ):
        result = await service.save_single_job(
            _captured_listing(),
            _accepted_analysis(),
            {"id": 7, "user_id": 9},
            None,
            upsert_scraped_job=legacy_upsert,
            geocode_location_fn=AsyncMock(),
        )

    assert result == "saved"
    legacy_upsert.assert_not_called()
    assert db.get.call_count == 2
    assert db.get.call_args_list[-1].kwargs["with_for_update"] is True
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_save_skips_a_captured_observation_when_catalog_row_disappears():
    db = MagicMock()
    db.get.return_value = None
    repository = MagicMock()
    service = SearchPipelinePersistence(db, repository)

    result = await service.save_single_job(
        _captured_listing(),
        _accepted_analysis(),
        {"id": 7, "user_id": 9},
        None,
        upsert_scraped_job=MagicMock(),
        geocode_location_fn=AsyncMock(),
    )

    assert result == "stale_catalog"
    repository.get_job_by_user_scraped_profile.assert_not_called()


@pytest.mark.asyncio
async def test_same_catalog_revision_can_be_saved_for_two_user_profiles():
    current = _catalog_record()
    db = MagicMock()
    db.get.return_value = current
    repository = MagicMock()
    first_user_job = SimpleNamespace()
    second_user_job = SimpleNamespace()
    repository.get_job_by_user_scraped_profile.side_effect = [
        first_user_job,
        second_user_job,
    ]
    service = SearchPipelinePersistence(db, repository)

    with (
        patch(
            "backend.services.search.persistence.materialize_match_citations",
            return_value=[],
        ),
        patch("backend.services.search.persistence.validate_match_attestation"),
    ):
        first_result = await service.save_single_job(
            _captured_listing(),
            _accepted_analysis(),
            {"id": 11, "user_id": 101},
            None,
            upsert_scraped_job=MagicMock(),
            geocode_location_fn=AsyncMock(),
        )
        second_result = await service.save_single_job(
            _captured_listing(),
            _accepted_analysis(),
            {"id": 12, "user_id": 202},
            None,
            upsert_scraped_job=MagicMock(),
            geocode_location_fn=AsyncMock(),
        )

    assert (first_result, second_result) == ("saved", "saved")
    assert repository.get_job_by_user_scraped_profile.call_args_list[0].args == (101, 42, 11)
    assert repository.get_job_by_user_scraped_profile.call_args_list[1].args == (202, 42, 12)


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
            "first_seen_at": datetime.now(timezone.utc),
            "last_seen_at": datetime.now(timezone.utc),
            "last_changed_at": datetime.now(timezone.utc),
            "content_revision": 1,
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
