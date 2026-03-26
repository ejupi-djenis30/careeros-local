"""Tests for backend/services/search/listing_utils.py.

These are all the pure utility helpers that had zero test coverage.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.services.search.listing_utils import (
    _canonicalize_skill,
    bootstrap_normalized_job_data,
    coerce_int,
    coerce_string_list,
    extract_listing_location_string,
    extract_listing_workload_string,
    extract_salary_max_chf,
    listing_fuzzy_key,
    listing_identity_key,
    listing_is_remote,
    normalized_text_token,
    parse_listing_publication_date,
    skills_overlap,
)


# ─── normalized_text_token ───────────────────────────────────────────────────

class TestNormalizedTextToken:
    def test_lowercases(self):
        assert normalized_text_token("PYTHON") == "python"

    def test_strips_punctuation(self):
        # C++ → c++ → non-word chars replaced → c → collapsed
        assert normalized_text_token("C++") == "c"
        assert normalized_text_token("C#") == "c"

    def test_collapses_whitespace(self):
        assert normalized_text_token("  hello   world  ") == "hello world"

    def test_empty_string(self):
        assert normalized_text_token("") == ""

    def test_non_string_returns_empty(self):
        assert normalized_text_token(None) == ""  # type: ignore[arg-type]
        assert normalized_text_token(123) == ""  # type: ignore[arg-type]


# ─── _canonicalize_skill ─────────────────────────────────────────────────────

class TestCanonicalizeSkill:
    def test_known_alias_js(self):
        assert _canonicalize_skill("js") == "javascript"

    def test_known_alias_k8s(self):
        assert _canonicalize_skill("k8s") == "kubernetes"

    def test_known_alias_postgres(self):
        assert _canonicalize_skill("postgres") == "postgresql"

    def test_known_alias_typescript(self):
        assert _canonicalize_skill("TS") == "typescript"

    def test_unknown_skill_passthrough(self):
        result = _canonicalize_skill("bizarrelanguage")
        assert result == "bizarrelanguage"

    def test_empty_string(self):
        assert _canonicalize_skill("") == ""


# ─── skills_overlap ──────────────────────────────────────────────────────────

class TestSkillsOverlap:
    def test_empty_lists_return_zero(self):
        assert skills_overlap([], ["python"]) == 0.0
        assert skills_overlap(["python"], []) == 0.0
        assert skills_overlap([], []) == 0.0

    def test_exact_match(self):
        assert skills_overlap(["python"], ["python"]) == 1.0

    def test_alias_match_js_javascript(self):
        ratio = skills_overlap(["javascript"], ["js"])
        assert ratio == 1.0

    def test_partial_overlap(self):
        ratio = skills_overlap(["python", "java"], ["python"])
        assert ratio == 0.5

    def test_no_overlap(self):
        ratio = skills_overlap(["rust"], ["python"])
        assert ratio == 0.0

    def test_substring_containment(self):
        # "machine learning" contains "ml" after canonicalization
        ratio = skills_overlap(["machine learning"], ["ml"])
        assert ratio == 1.0

    def test_full_overlap(self):
        ratio = skills_overlap(["python", "docker"], ["python", "docker"])
        assert ratio == 1.0

    def test_alias_kubernetes_k8s(self):
        ratio = skills_overlap(["k8s"], ["kubernetes"])
        assert ratio == 1.0


# ─── coerce_int ──────────────────────────────────────────────────────────────

class TestCoerceInt:
    def test_int_passthrough(self):
        assert coerce_int(42) == 42

    def test_string_digits(self):
        assert coerce_int("100") == 100

    def test_string_with_spaces(self):
        assert coerce_int("  50  ") == 50

    def test_none_returns_default(self):
        assert coerce_int(None) is None
        assert coerce_int(None, 0) == 0

    def test_empty_string_returns_default(self):
        assert coerce_int("") is None

    def test_non_numeric_string_returns_default(self):
        assert coerce_int("abc") is None

    def test_bool_returns_default(self):
        # booleans are ints in Python but should be rejected by convention
        assert coerce_int(True) is None
        assert coerce_int(False) is None


# ─── listing_identity_key ────────────────────────────────────────────────────

class TestListingIdentityKey:
    def _make(self, source=None, platform=None, id_=None, platform_job_id=None):
        obj = SimpleNamespace()
        if source is not None:
            obj.source = source
        if platform is not None:
            obj.platform = platform
        if id_ is not None:
            obj.id = id_
        if platform_job_id is not None:
            obj.platform_job_id = platform_job_id
        return obj

    def test_source_and_id(self):
        listing = self._make(source="jobroom", id_="ABC123")
        assert listing_identity_key(listing) == "jobroom:ABC123"

    def test_platform_and_platform_job_id_fallback(self):
        listing = self._make(platform="swissdevjobs", platform_job_id="XYZ")
        assert listing_identity_key(listing) == "swissdevjobs:XYZ"

    def test_missing_platform_returns_none(self):
        listing = self._make(id_="123")  # no source or platform
        assert listing_identity_key(listing) is None

    def test_missing_id_returns_none(self):
        listing = self._make(source="jobroom")  # no id or platform_job_id
        assert listing_identity_key(listing) is None


# ─── listing_fuzzy_key ───────────────────────────────────────────────────────

class TestListingFuzzyKey:
    def _make(self, title="", company_name=""):
        obj = SimpleNamespace()
        obj.title = title
        company = SimpleNamespace()
        company.name = company_name
        obj.company = company
        return obj

    def test_basic_key(self):
        key = listing_fuzzy_key(self._make(title="Software Engineer", company_name="Acme AG"))
        assert key == "software engineer::acme ag"

    def test_punctuation_stripped(self):
        key = listing_fuzzy_key(self._make(title="C++ Developer", company_name="Tech.Corp"))
        assert "::" in key

    def test_empty_title_and_company(self):
        listing = SimpleNamespace(title="")
        listing.company = None
        assert listing_fuzzy_key(listing) == ""


# ─── listing_is_remote ───────────────────────────────────────────────────────

class TestListingIsRemote:
    def _make(self, work_forms=None, title="", desc=""):
        employment = SimpleNamespace(work_forms=work_forms or [])
        description = SimpleNamespace(description=desc)
        return SimpleNamespace(
            employment=employment,
            title=title,
            descriptions=[description],
        )

    def test_remote_via_work_form(self):
        assert listing_is_remote(self._make(work_forms=["home office"])) is True

    def test_remote_keyword_in_title(self):
        assert listing_is_remote(self._make(title="Remote Software Engineer")) is True

    def test_hybrid_keyword_in_description(self):
        assert listing_is_remote(self._make(desc="This is a hybrid role")) is True

    def test_not_remote(self):
        assert listing_is_remote(self._make(title="Office Based Role", desc="Come to the office every day")) is False


# ─── extract_salary_max_chf ──────────────────────────────────────────────────

class TestExtractSalaryMaxChf:
    def _make(self, desc=""):
        description = SimpleNamespace(description=desc)
        return SimpleNamespace(descriptions=[description], raw_data=None)

    def test_chf_prefix(self):
        # Regex requires a separator (space/apostrophe) before the 3-digit group
        salary = extract_salary_max_chf(self._make("CHF 120'000 per year"))
        assert salary == 120000

    def test_chf_prefix_space_separator(self):
        salary = extract_salary_max_chf(self._make("CHF 90 000 per year"))
        assert salary == 90000

    def test_no_salary_returns_none(self):
        assert extract_salary_max_chf(self._make("No salary info here")) is None

    def test_multiple_values_returns_max(self):
        salary = extract_salary_max_chf(self._make("CHF 80'000 to CHF 120'000"))
        assert salary == 120000

    def test_empty_listing_returns_none(self):
        listing = SimpleNamespace(descriptions=[], raw_data=None)
        assert extract_salary_max_chf(listing) is None


# ─── extract_listing_workload_string ─────────────────────────────────────────

class TestExtractListingWorkloadString:
    def _make(self, workload_min=None, workload_max=None):
        employment = SimpleNamespace(workload_min=workload_min, workload_max=workload_max)
        return SimpleNamespace(employment=employment)

    def test_range(self):
        assert extract_listing_workload_string(self._make(80, 100)) == "80-100%"

    def test_equal_min_max(self):
        assert extract_listing_workload_string(self._make(100, 100)) == "100%"

    def test_no_employment(self):
        listing = SimpleNamespace(employment=None)
        assert extract_listing_workload_string(listing) == ""

    def test_none_values(self):
        assert extract_listing_workload_string(self._make(None, None)) == ""


# ─── parse_listing_publication_date ─────────────────────────────────────────

class TestParseListingPublicationDate:
    def _make(self, start_date=None):
        if start_date is None:
            return SimpleNamespace(publication=None)
        pub = SimpleNamespace(start_date=start_date)
        return SimpleNamespace(publication=pub)

    def test_iso_datetime(self):
        listing = self._make("2024-03-15T10:30:00Z")
        result = parse_listing_publication_date(listing, "jobroom", "ID123")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 3

    def test_date_only(self):
        listing = self._make("2024-06-01")
        result = parse_listing_publication_date(listing, "adecco", "X")
        assert isinstance(result, datetime)
        assert result.year == 2024

    def test_no_publication(self):
        listing = self._make(None)
        assert parse_listing_publication_date(listing, "jobroom", "X") is None

    def test_invalid_date_returns_none(self):
        listing = self._make("not-a-date")
        assert parse_listing_publication_date(listing, "jobroom", "X") is None


# ─── extract_listing_location_string ─────────────────────────────────────────

class TestExtractListingLocationString:
    def test_city_from_location_object(self):
        location = SimpleNamespace(city="Zurich")
        listing = SimpleNamespace(location=location)
        assert extract_listing_location_string(listing) == "Zurich"

    def test_no_location_returns_empty(self):
        listing = SimpleNamespace(location=None)
        assert extract_listing_location_string(listing) == ""


# ─── bootstrap_normalized_job_data ───────────────────────────────────────────

class TestBootstrapNormalizedJobData:
    def _make_listing(self, title="Software Engineer", desc="5 years experience. CHF 120000. Remote."):
        description = SimpleNamespace(description=desc)
        employment = SimpleNamespace(workload_min=80, workload_max=100, work_forms=[])
        location = SimpleNamespace(city="Zurich")
        return SimpleNamespace(
            title=title,
            descriptions=[description],
            employment=employment,
            location=location,
            language_skills=[],
            occupations=[],
            raw_data=None,
        )

    def test_returns_dict_with_required_keys(self):
        listing = self._make_listing()
        result = bootstrap_normalized_job_data(
            listing, desc_text="5 years Java experience", company_name="Acme", location_str="Zurich"
        )
        assert isinstance(result, dict)
        assert "normalized_title" in result
        assert result["normalization_confidence"] == 0.35

    def test_seniority_detection_senior(self):
        listing = self._make_listing(title="Senior Software Engineer")
        result = bootstrap_normalized_job_data(
            listing, desc_text="", company_name="Acme", location_str="Zurich"
        )
        assert result.get("normalized_seniority") == "senior"

    def test_seniority_detection_junior(self):
        listing = self._make_listing(title="Junior Developer")
        result = bootstrap_normalized_job_data(
            listing, desc_text="", company_name="Acme", location_str="Zurich"
        )
        assert result.get("normalized_seniority") == "junior"

    def test_remote_detected(self):
        listing = self._make_listing()
        employment = SimpleNamespace(workload_min=80, workload_max=100, work_forms=["home office"])
        listing.employment = employment
        result = bootstrap_normalized_job_data(
            listing, desc_text="Remote role", company_name="Acme", location_str="Zurich"
        )
        # remote → normalized_employment_mode = "remote"
        assert result.get("normalized_employment_mode") == "remote"

    def test_career_changer_signal(self):
        listing = self._make_listing()
        result = bootstrap_normalized_job_data(
            listing,
            desc_text="Quereinsteiger willkommen. No experience required.",
            company_name="Acme",
            location_str="Geneva",
        )
        assert result.get("normalized_career_changer_friendly") is True

    def test_experience_extraction(self):
        listing = self._make_listing()
        result = bootstrap_normalized_job_data(
            listing,
            desc_text="Minimum 5 years of experience with Python",
            company_name="Acme",
            location_str="Basel",
        )
        assert result.get("normalized_experience_min_years") == 5
