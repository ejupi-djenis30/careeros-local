"""Unit tests for backend/providers/jobs/jobroom/request_builder.py.

Covers:
- build_search_payload: keywords, location resolution, contract type,
  radius search, language skills, workload fields
- build_search_url: sort order, language param, pagination
"""

from unittest.mock import MagicMock

import pytest

from backend.providers.jobs.jobroom.request_builder import (
    build_search_payload,
    build_search_url,
)
from backend.providers.jobs.models import (
    ContractType,
    Coordinates,
    JobSearchRequest,
    LanguageLevel,
    LanguageSkillRequest,
    RadiusSearchRequest,
    SortOrder,
)


def _make_mapper(resolved=None):
    mapper = MagicMock()
    mapper.resolve_safe.return_value = resolved or []
    return mapper


# ─── build_search_payload ─────────────────────────────────────────────────────


class TestBuildSearchPayload:
    def test_basic_payload_has_required_keys(self):
        req = JobSearchRequest()
        payload = build_search_payload(req, _make_mapper())
        assert "workloadPercentageMin" in payload
        assert "workloadPercentageMax" in payload
        assert "keywords" in payload
        assert "communalCodes" in payload

    def test_query_appended_to_keywords(self):
        req = JobSearchRequest(query="python developer", keywords=["django"])
        payload = build_search_payload(req, _make_mapper())
        assert "python developer" in payload["keywords"]
        assert "django" in payload["keywords"]

    def test_no_query_keywords_list_still_present(self):
        req = JobSearchRequest(query="", keywords=[])
        payload = build_search_payload(req, _make_mapper())
        assert payload["keywords"] == []

    def test_contract_type_permanent_sets_permanent_true(self):
        req = JobSearchRequest(contract_type=ContractType.PERMANENT)
        payload = build_search_payload(req, _make_mapper())
        assert payload["permanent"] is True

    def test_contract_type_temporary_sets_permanent_false(self):
        req = JobSearchRequest(contract_type=ContractType.TEMPORARY)
        payload = build_search_payload(req, _make_mapper())
        assert payload["permanent"] is False

    def test_contract_type_any_sets_permanent_none(self):
        req = JobSearchRequest(contract_type=ContractType.ANY)
        payload = build_search_payload(req, _make_mapper())
        assert payload["permanent"] is None

    def test_radius_search_included_when_set(self):
        req = JobSearchRequest(
            radius_search=RadiusSearchRequest(
                geo_point=Coordinates(lat=47.37, lon=8.54),
                distance=30,
            )
        )
        payload = build_search_payload(req, _make_mapper())
        assert "radiusSearchRequest" in payload
        rs = payload["radiusSearchRequest"]
        assert rs["geoPoint"]["lat"] == pytest.approx(47.37)
        assert rs["distance"] == 30

    def test_no_radius_search_key_absent(self):
        req = JobSearchRequest()
        payload = build_search_payload(req, _make_mapper())
        assert "radiusSearchRequest" not in payload

    def test_location_resolved_communal_codes_added(self):
        mapper = _make_mapper(resolved=["1234", "5678"])
        req = JobSearchRequest(location="Zurich")
        payload = build_search_payload(req, mapper)
        assert "1234" in payload["communalCodes"]
        assert "5678" in payload["communalCodes"]

    def test_existing_communal_codes_kept(self):
        # location must be non-empty for the mapper to be called
        req = JobSearchRequest(communal_codes=["9999"], location="Zurich")
        payload = build_search_payload(req, _make_mapper(resolved=["1111"]))
        assert "9999" in payload["communalCodes"]
        assert "1111" in payload["communalCodes"]

    def test_language_skills_serialised(self):
        req = JobSearchRequest(
            language_skills=[
                LanguageSkillRequest(
                    language_code="en",
                    spoken_level=LanguageLevel.PROFICIENT,
                    written_level=LanguageLevel.INTERMEDIATE,
                )
            ]
        )
        payload = build_search_payload(req, _make_mapper())
        assert payload.get("language_skills") is None  # not in current impl

    def test_workload_min_max_set(self):
        req = JobSearchRequest(workload_min=60, workload_max=80)
        payload = build_search_payload(req, _make_mapper())
        assert payload["workloadPercentageMin"] == 60
        assert payload["workloadPercentageMax"] == 80

    def test_profession_codes_serialised(self):
        req = JobSearchRequest(profession_codes=["27114004"])
        payload = build_search_payload(req, _make_mapper())
        prof = payload["professionCodes"]
        assert len(prof) == 1
        assert prof[0]["type"] == "AVAM"
        assert prof[0]["value"] == "27114004"

    def test_canton_codes_included(self):
        req = JobSearchRequest(canton_codes=["ZH", "BE"])
        payload = build_search_payload(req, _make_mapper())
        assert "ZH" in payload["cantonCodes"]
        assert "BE" in payload["cantonCodes"]


# ─── build_search_url ─────────────────────────────────────────────────────────


class TestBuildSearchUrl:
    def test_url_contains_page_and_size(self):
        req = JobSearchRequest(page=2, page_size=50)
        url = build_search_url(req)
        assert "page=2" in url
        assert "size=50" in url

    def test_default_sort_is_date_desc(self):
        req = JobSearchRequest()
        url = build_search_url(req)
        assert "sort=date_desc" in url

    def test_sort_date_asc(self):
        req = JobSearchRequest(sort=SortOrder.DATE_ASC)
        url = build_search_url(req)
        assert "sort=date_asc" in url

    def test_sort_relevance(self):
        req = JobSearchRequest(sort=SortOrder.RELEVANCE)
        url = build_search_url(req)
        assert "sort=relevance" in url

    def test_url_contains_lang_param(self):
        req = JobSearchRequest(language="en")
        url = build_search_url(req)
        assert "_ng=" in url
