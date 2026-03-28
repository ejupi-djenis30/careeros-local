"""Unit tests for backend/providers/jobs/swissdevjobs/filters.py.

Covers:
- filter_jobs: keyword filtering, location text, radius, company name,
  workload, language, work form, contract type
"""
import pytest
from unittest.mock import MagicMock

from backend.providers.jobs.models import (
    ContractType,
    JobSearchRequest,
    WorkForm,
    LanguageSkillRequest,
    RadiusSearchRequest,
    Coordinates,
)
from backend.providers.jobs.swissdevjobs.filters import filter_jobs


# ─── helpers ──────────────────────────────────────────────────────────────────

def _job(
    name="Python Developer",
    technologies=None,
    filter_tags=None,
    actual_city="Zurich",
    city_category="Swiss German",
    latitude=47.3769,
    longitude=8.5417,
    company="Acme AG",
    job_type="full-time",
    language="english",
    workplace="office",
):
    return {
        "name": name,
        "technologies": technologies or ["Python", "Django"],
        "filterTags": filter_tags or [],
        "actualCity": actual_city,
        "cityCategory": city_category,
        "latitude": latitude,
        "longitude": longitude,
        "company": company,
        "jobType": job_type,
        "language": language,
        "workplace": workplace,
    }


def _req(
    query: str = "",
    location: str = "",
    workload_min: int = 0,
    workload_max: int = 100,
    contract_type: ContractType = ContractType.ANY,
    company_name: str | None = None,
) -> JobSearchRequest:
    return JobSearchRequest(
        query=query,
        location=location,
        workload_min=workload_min,
        workload_max=workload_max,
        contract_type=contract_type,
        company_name=company_name,
    )


# ─── Keyword filtering ────────────────────────────────────────────────────────

class TestKeywordFiltering:
    def test_no_query_includes_all_jobs(self):
        jobs = [_job("Backend Engineer"), _job("Frontend Dev")]
        result = filter_jobs(jobs, _req(query=""))
        assert len(result) == 2

    def test_matching_keyword_in_name_passes(self):
        jobs = [_job("Python Developer")]
        result = filter_jobs(jobs, _req(query="python"))
        assert len(result) == 1

    def test_non_matching_keyword_excluded(self):
        jobs = [_job("Python Developer")]
        result = filter_jobs(jobs, _req(query="java"))
        assert len(result) == 0

    def test_keyword_matched_against_technologies(self):
        jobs = [_job("Software Engineer", technologies=["React", "TypeScript"])]
        result = filter_jobs(jobs, _req(query="react"))
        assert len(result) == 1

    def test_keyword_matched_against_filter_tags(self):
        jobs = [_job("Engineer", filter_tags=["remote", "startup"])]
        result = filter_jobs(jobs, _req(query="startup"))
        assert len(result) == 1

    def test_all_tokens_must_match(self):
        jobs = [_job("Python Backend Developer")]
        # Both "python" and "java" must appear
        result = filter_jobs(jobs, _req(query="python java"))
        assert len(result) == 0


# ─── Location text filtering ──────────────────────────────────────────────────

class TestLocationFiltering:
    def test_no_location_includes_all(self):
        jobs = [_job(actual_city="Zurich"), _job(actual_city="Geneva")]
        result = filter_jobs(jobs, _req(location=""))
        assert len(result) == 2

    def test_city_match_passes(self):
        jobs = [_job(actual_city="Zurich")]
        result = filter_jobs(jobs, _req(location="zurich"))
        assert len(result) == 1

    def test_city_mismatch_excluded(self):
        jobs = [_job(actual_city="Geneva")]
        result = filter_jobs(jobs, _req(location="zurich"))
        assert len(result) == 0

    def test_city_category_match_passes(self):
        jobs = [_job(actual_city="not_matching", city_category="Swiss German")]
        result = filter_jobs(jobs, _req(location="swiss german"))
        assert len(result) == 1


# ─── Radius search ────────────────────────────────────────────────────────────

class TestRadiusFiltering:
    def _radius_req(self, lat, lon, distance_km):
        return JobSearchRequest(
            radius_search=RadiusSearchRequest(
                geo_point=Coordinates(lat=lat, lon=lon),
                distance=distance_km,
            )
        )

    def test_job_within_radius_passes(self):
        # Zurich (47.37, 8.54) — job at roughly the same point
        jobs = [_job(latitude=47.37, longitude=8.54)]
        result = filter_jobs(jobs, self._radius_req(47.37, 8.54, 50))
        assert len(result) == 1

    def test_job_outside_radius_excluded(self):
        # Geneva is ~230 km from Zurich
        jobs = [_job(latitude=46.2044, longitude=6.1432)]
        result = filter_jobs(jobs, self._radius_req(47.37, 8.54, 50))
        assert len(result) == 0

    def test_job_with_no_coordinates_excluded_in_radius_search(self):
        job = _job()
        job["latitude"] = None
        job["longitude"] = None
        result = filter_jobs([job], self._radius_req(47.37, 8.54, 50))
        assert len(result) == 0


# ─── Company name filtering ───────────────────────────────────────────────────

class TestCompanyFiltering:
    def test_matching_company_passes(self):
        jobs = [_job(company="TechCorp AG")]
        result = filter_jobs(jobs, _req(company_name="techcorp"))
        assert len(result) == 1

    def test_non_matching_company_excluded(self):
        jobs = [_job(company="OtherCo")]
        result = filter_jobs(jobs, _req(company_name="techcorp"))
        assert len(result) == 0

    def test_no_company_filter_includes_all(self):
        jobs = [_job(company="AnyCompany")]
        result = filter_jobs(jobs, _req(company_name=None))
        assert len(result) == 1


# ─── Workload filtering ───────────────────────────────────────────────────────

class TestWorkloadFiltering:
    def test_looking_for_full_time_excludes_part_time(self):
        jobs = [_job(job_type="part-time")]
        result = filter_jobs(jobs, _req(workload_min=90, workload_max=100))
        assert len(result) == 0

    def test_looking_for_part_time_excludes_full_time(self):
        jobs = [_job(job_type="full-time")]
        result = filter_jobs(jobs, _req(workload_min=0, workload_max=80))
        assert len(result) == 0

    def test_flexible_workload_includes_both(self):
        jobs = [_job(job_type="full-time"), _job(job_type="part-time")]
        result = filter_jobs(jobs, _req(workload_min=50, workload_max=100))
        assert len(result) == 2


# ─── Language filtering ───────────────────────────────────────────────────────

class TestLanguageFiltering:
    def test_matching_language_passes(self):
        jobs = [_job(language="german")]
        req = JobSearchRequest(
            language_skills=[LanguageSkillRequest(language_code="de")]
        )
        result = filter_jobs(jobs, req)
        assert len(result) == 1

    def test_non_matching_language_excluded(self):
        jobs = [_job(language="french")]
        req = JobSearchRequest(
            language_skills=[LanguageSkillRequest(language_code="de")]
        )
        result = filter_jobs(jobs, req)
        assert len(result) == 0

    def test_no_language_filter_includes_all(self):
        jobs = [_job(language="italian")]
        result = filter_jobs(jobs, _req())
        assert len(result) == 1


# ─── Work form filtering ──────────────────────────────────────────────────────

class TestWorkFormFiltering:
    def test_home_office_filter_excludes_office_only(self):
        jobs = [_job(workplace="office")]
        req = JobSearchRequest(work_forms=[WorkForm.HOME_OFFICE])
        result = filter_jobs(jobs, req)
        assert len(result) == 0

    def test_home_office_filter_includes_remote(self):
        jobs = [_job(workplace="remote")]
        req = JobSearchRequest(work_forms=[WorkForm.HOME_OFFICE])
        result = filter_jobs(jobs, req)
        assert len(result) == 1

    def test_home_office_filter_includes_hybrid(self):
        jobs = [_job(workplace="hybrid")]
        req = JobSearchRequest(work_forms=[WorkForm.HOME_OFFICE])
        result = filter_jobs(jobs, req)
        assert len(result) == 1


# ─── Contract type filtering ──────────────────────────────────────────────────

class TestContractTypeFiltering:
    def test_any_contract_includes_all(self):
        jobs = [_job(job_type="full-time"), _job(job_type="freelance")]
        result = filter_jobs(jobs, _req(contract_type=ContractType.ANY))
        assert len(result) == 2

    def test_permanent_excludes_freelance(self):
        jobs = [_job(job_type="freelance permanent")]
        result = filter_jobs(jobs, _req(contract_type=ContractType.PERMANENT))
        assert len(result) == 0

    def test_temporary_includes_freelance(self):
        jobs = [_job(job_type="freelance")]
        result = filter_jobs(jobs, _req(contract_type=ContractType.TEMPORARY))
        assert len(result) == 1

    def test_permanent_includes_non_freelance(self):
        jobs = [_job(job_type="full-time")]
        result = filter_jobs(jobs, _req(contract_type=ContractType.PERMANENT))
        assert len(result) == 1
