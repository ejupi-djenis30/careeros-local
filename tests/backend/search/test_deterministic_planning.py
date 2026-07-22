from types import SimpleNamespace

from backend.core.config import settings
from backend.search.acquisition import AcquisitionMixin
from backend.search.deterministic_planning import build_deterministic_search_plan


def _profile(**overrides):
    values = {
        "max_queries": 4,
        "max_occupation_queries": 2,
        "max_keyword_queries": 2,
        "preferred_domains": ["it"],
        "profile_search_intent_role_family": "Platform Engineer",
        "profile_normalized_role_family": "Software Engineer",
        "profile_search_intent_domain": "it",
        "profile_normalized_domain": "it",
        "profile_search_intent_keywords": ["Python", "Kubernetes"],
        "profile_search_intent_skills": ["Python", "PostgreSQL"],
        "profile_normalized_skills": ["Docker"],
        "profile_normalized_transferable_skills": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_deterministic_plan_uses_only_explicit_input_and_obeys_limits():
    plan = build_deterministic_search_plan(
        {
            "role_description": "Backend Developer, Site Reliability Engineer",
            "search_strategy": 'Focus on "distributed systems"; remote roles',
        },
        _profile(),
    )

    assert plan == [
        {
            "query": "Backend Developer",
            "type": "occupation",
            "domain": "it",
            "language": "en",
        },
        {
            "query": "Site Reliability Engineer",
            "type": "occupation",
            "domain": "it",
            "language": "en",
        },
        {
            "query": "distributed systems",
            "type": "keyword",
            "domain": "it",
            "language": "en",
        },
        {"query": "remote", "type": "keyword", "domain": "it", "language": "en"},
    ]


def test_deterministic_plan_works_with_only_user_entered_role_description():
    profile = _profile(
        max_queries=2,
        max_occupation_queries=None,
        max_keyword_queries=None,
        preferred_domains=None,
        profile_search_intent_role_family=None,
        profile_normalized_role_family=None,
        profile_search_intent_domain=None,
        profile_normalized_domain=None,
        profile_search_intent_keywords=None,
        profile_search_intent_skills=None,
        profile_normalized_skills=None,
    )

    plan = build_deterministic_search_plan(
        {"role_description": "Backend Developer / Platform Engineer"}, profile
    )

    assert [item["query"] for item in plan] == ["Backend Developer", "Platform Engineer"]
    assert all(item["domain"] == "general" for item in plan)


def test_deterministic_plan_never_mines_private_cv_text_for_queries():
    profile = _profile(
        max_queries=1,
        max_occupation_queries=None,
        max_keyword_queries=None,
        preferred_domains=None,
        profile_search_intent_role_family=None,
        profile_normalized_role_family=None,
        profile_search_intent_domain=None,
        profile_normalized_domain=None,
        profile_search_intent_keywords=None,
        profile_search_intent_skills=None,
        profile_normalized_skills=None,
    )

    plan = build_deterministic_search_plan(
        {
            "role_description": "Security Engineer",
            "cv_content": "PRIVATE-COMPANY-NAME secret internal project",
        },
        profile,
    )

    assert plan[0]["query"] == "Security Engineer"
    assert "PRIVATE-COMPANY-NAME" not in str(plan)


def test_deterministic_plan_rejects_cv_and_model_derived_fields_without_explicit_input():
    profile = _profile()

    assert build_deterministic_search_plan({"cv_content": "Python engineer"}, profile) == []


def test_zero_limits_disable_queries_while_none_uses_defaults():
    disabled = _profile(
        max_queries=3,
        max_occupation_queries=0,
        max_keyword_queries=1,
    )
    plan = build_deterministic_search_plan(
        {"role_description": "Platform Engineer", "search_strategy": 'Use "Python"'},
        disabled,
    )
    assert [item["query"] for item in plan] == ["Python"]

    assert build_deterministic_search_plan(
        {"role_description": "Platform Engineer"},
        _profile(max_queries=0, max_occupation_queries=None, max_keyword_queries=None),
    ) == []

    defaulted = build_deterministic_search_plan(
        {"role_description": "Platform Engineer"},
        _profile(max_queries=None, max_occupation_queries=None, max_keyword_queries=None),
        default_max_queries=1,
    )
    assert [item["query"] for item in defaulted] == ["Platform Engineer"]


def test_acquisition_boundary_preserves_configured_zero(monkeypatch):
    monkeypatch.setattr(settings, "SEARCH_DEGRADED_PLAN_MAX_QUERIES", 0)
    monkeypatch.setattr(settings, "SEARCH_DEGRADED_PLAN_MAX_KEYWORDS", 0)
    profile = _profile(
        max_queries=None,
        max_occupation_queries=None,
        max_keyword_queries=None,
    )

    assert AcquisitionMixin()._build_deterministic_explicit_plan(
        {"role_description": "Platform Engineer", "search_strategy": "Python"},
        profile,
    ) == []
