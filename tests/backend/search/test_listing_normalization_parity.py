from types import SimpleNamespace

import backend.search.normalization.listings as implementation
import backend.services.search.listing_utils as compatibility


def _listing():
    return SimpleNamespace(
        source="jobroom",
        id=" A-42 ",
        external_url=(
            "HTTPS://www.Example.com/jobs/Backend/?utm_source=x&lang=EN"
        ),
        title="<b>Senior Backend Engineer</b>",
        company=SimpleNamespace(name="Acme AG"),
        employment=SimpleNamespace(
            workload_min=80,
            workload_max=100,
            work_forms=["Home Office"],
        ),
        language_skills=[SimpleNamespace(language_code="de", spoken_level="b2")],
        occupations=[
            SimpleNamespace(education_code="bachelor", qualification_code="Q1")
        ],
        skills=["Python", "FastAPI"],
        raw_data={},
    )


def test_legacy_import_is_the_canonical_normalization_module():
    assert compatibility is implementation


def test_listing_mapping_snapshot_remains_provider_independent():
    listing = _listing()
    normalized = implementation.bootstrap_normalized_job_data(
        listing,
        desc_text="Build APIs with Python. CHF 120000.",
        company_name="Acme AG",
        location_str="Zürich",
    )
    normalized.pop("normalized_at")

    assert {
        "identity": implementation.listing_identity_key(listing),
        "url": implementation.listing_url_token(listing),
        "fuzzy": implementation.listing_fuzzy_key(listing),
        "normalized": normalized,
    } == {
        "identity": "jobroom:A-42",
        "url": "example.com/jobs/backend?lang=en",
        "fuzzy": "b senior backend engineer b::acme ag",
        "normalized": {
            "normalization_confidence": 0.35,
            "normalization_source": "provider_bootstrap",
            "normalization_status": "provider_bootstrap",
            "normalization_version": 1,
            "normalized_career_changer_friendly": None,
            "normalized_contract_type": None,
            "normalized_domain": "general",
            "normalized_education_levels": ["bachelor"],
            "normalized_employment_mode": "remote",
            "normalized_entry_barrier": "medium",
            "normalized_experience_max_years": None,
            "normalized_experience_min_years": None,
            "normalized_hard_blockers": None,
            "normalized_key_requirements": None,
            "normalized_metadata": {
                "bootstrap": True,
                "company": "Acme AG",
                "location": "Zürich",
                "provider": "jobroom",
                "qualification_codes": ["Q1"],
            },
            "normalized_physical_requirements": None,
            "normalized_preferred_skills": None,
            "normalized_qualification_level": "Q1",
            "normalized_required_languages": [{"code": "de", "level": "B2"}],
            "normalized_required_skills": None,
            "normalized_role_family": "Senior Backend Engineer",
            "normalized_role_type": "technical",
            "normalized_salary_max_chf": None,
            "normalized_salary_min_chf": None,
            "normalized_seniority": "senior",
            "normalized_soft_skills": None,
            "normalized_title": "Senior Backend Engineer",
            "normalized_workload_max": 100,
            "normalized_workload_min": 80,
        },
    }
