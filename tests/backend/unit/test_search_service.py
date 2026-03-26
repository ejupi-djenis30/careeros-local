import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from backend.services.search_service import SearchService, get_compatible_providers


# ─── Domain Router Tests ───

def test_get_compatible_providers_generalist():
    """Generalist providers (*) accept any domain."""
    providers = {"job_room": MagicMock(), "swissdevjobs": MagicMock()}
    provider_infos = {
        "job_room": MagicMock(accepted_domains=["*"]),
        "swissdevjobs": MagicMock(accepted_domains=["it"]),
    }
    result = get_compatible_providers("finance", providers, provider_infos)
    assert result == ["job_room"]


def test_get_compatible_providers_it_domain():
    """IT queries go to both generalist AND IT-only providers."""
    providers = {"job_room": MagicMock(), "swissdevjobs": MagicMock(), "local_db": MagicMock()}
    provider_infos = {
        "job_room": MagicMock(accepted_domains=["*"]),
        "swissdevjobs": MagicMock(accepted_domains=["it"]),
        "local_db": MagicMock(accepted_domains=["*"]),
    }
    result = get_compatible_providers("it", providers, provider_infos)
    assert "job_room" in result
    assert "swissdevjobs" in result
    assert "local_db" in result


def test_get_compatible_providers_no_match():
    """If no provider accepts the domain, return only generalists."""
    providers = {"swissdevjobs": MagicMock()}
    provider_infos = {
        "swissdevjobs": MagicMock(accepted_domains=["it"]),
    }
    result = get_compatible_providers("medical", providers, provider_infos)
    assert result == []


# ─── SearchService Tests ───

@pytest.fixture
def mock_job_repo():
    return MagicMock()

@pytest.fixture
def mock_profile_repo():
    return MagicMock()

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def search_service(mock_db, mock_job_repo, mock_profile_repo):
    return SearchService(db=mock_db, job_repo=mock_job_repo, profile_repo=mock_profile_repo)

@pytest.mark.asyncio
async def test_run_search_success(search_service, mock_profile_repo, mock_job_repo, mock_db):
    # Setup mocks
    mock_profile = MagicMock()
    mock_profile.id = 1
    mock_profile.user_id = 42
    mock_profile.max_queries = 5
    mock_profile.is_stopped = False
    mock_profile.location_filter = "Zurich"
    mock_profile.workload_filter = None
    mock_profile.posted_within_days = 30
    mock_profile.contract_type = "any"
    mock_profile.latitude = None
    mock_profile.longitude = None
    mock_profile.cached_queries = None
    mock_profile.cached_cv_summary = None
    mock_profile.cv_content = "Long CV content"
    mock_profile.role_description = "Software Engineer"
    mock_profile.search_strategy = ""
    mock_profile.max_occupation_queries = None
    mock_profile.max_keyword_queries = None
    mock_profile_repo.get.return_value = mock_profile
    
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    mock_job_repo.get_user_job_identifiers.return_value = []
    mock_job_repo.get_profile_job_identifiers.return_value = []
    mock_job_repo.get_applied_scraped_job_ids.return_value = set()
    
    def make_mock_listing(job_id, url):
        m = MagicMock()
        m.id = job_id
        m.source = "test"
        m.external_url = url
        m.title = "Software Engineer"
        m.company = MagicMock(name="Test Company")
        m.location = MagicMock(city="Zurich", coordinates=None)
        m.employment = MagicMock(workload_min=80, workload_max=100)
        m.publication = MagicMock(start_date="2024-01-01")
        m.descriptions = [MagicMock(description="Cool job")]
        m.occupations = []
        m.language_skills = []
        m._source_query = "Software Engineer"
        m._summary = "Summary"
        return m

    mock_provider = MagicMock()
    mock_provider.get_provider_info.return_value = MagicMock(accepted_domains=["*"])
    mock_provider.close = MagicMock(return_value=None)
    mock_response = MagicMock(items=[make_mock_listing("job1", "url1")])
    mock_response.total_pages = 1
    mock_provider.search = AsyncMock(return_value=mock_response)
    
    with patch("backend.services.search_service.llm_service") as mock_llm, \
         patch("backend.services.search_service.init_status"), \
         patch("backend.services.search_service.add_log"), \
         patch("backend.services.search_service.update_status"), \
         patch("backend.services.search_service.JobRoomProvider"), \
         patch("backend.services.search_service.SwissDevJobsProvider"), \
         patch("backend.services.search_service.AdeccoProvider"), \
         patch("backend.services.search_service.LocalDbProvider"):
        
        # Now create service so internal providers are mocked
        svc = SearchService(db=mock_db, job_repo=mock_job_repo, profile_repo=mock_profile_repo)
        
        # Inject provider mocks into the created service
        svc.providers = {
            "job_room": mock_provider,
            "swissdevjobs": mock_provider,
            "adecco": mock_provider,
            "local_db": mock_provider
        }
        
        mock_llm.generate_search_plan = AsyncMock(return_value=[
            {"domain": "it", "query": "Software Engineer", "type": "occupation", "language": "en"}
        ])
        mock_llm.summarize_cv = AsyncMock(return_value="Condensed CV")
        mock_llm.check_relevance_batch = AsyncMock(return_value=[True])
        mock_llm.analyze_job_batch = AsyncMock(return_value=[{"relevant": True, "affinity_score": 80}])
        
        await svc.run_search(1)
        
        mock_llm.generate_search_plan.assert_called_once()

@pytest.mark.asyncio
async def test_run_search_stopped_by_user(search_service, mock_profile_repo, mock_db):
    mock_profile = MagicMock()
    mock_profile.is_stopped = True
    mock_profile_repo.get.return_value = mock_profile
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    with patch("backend.services.search_service.init_status"), \
         patch("backend.services.search_service.add_log"), \
         patch("backend.services.search_service.JobRoomProvider"), \
         patch("backend.services.search_service.SwissDevJobsProvider"), \
         patch("backend.services.search_service.AdeccoProvider"), \
         patch("backend.services.search_service.LocalDbProvider"), \
         patch("backend.services.search_service.update_status") as mock_update, \
         patch.object(search_service, "_normalize_user_profile", new=AsyncMock(return_value={})):
        
        await search_service.run_search(1)

@pytest.mark.asyncio
async def test_run_search_no_plan(search_service, mock_profile_repo, mock_db):
    mock_profile = MagicMock()
    mock_profile.id = 1
    mock_profile.user_id = 42
    mock_profile.max_queries = 5
    mock_profile.max_occupation_queries = None
    mock_profile.max_keyword_queries = None
    mock_profile.cv_content = "CV"
    mock_profile.role_description = "Dev"
    mock_profile.search_strategy = ""
    mock_profile.latitude = None
    mock_profile.longitude = None
    mock_profile.cached_queries = None
    mock_profile.cached_cv_summary = None
    mock_profile_repo.get.return_value = mock_profile
    mock_db.query.return_value.filter.return_value.first.return_value = None
    with patch("backend.services.search_service.llm_service") as mock_llm, \
            patch("backend.services.search_service.settings.SEARCH_ENABLE_DEGRADED_PLAN_FALLBACK", False), \
         patch("backend.services.search_service.init_status"), \
         patch("backend.services.search_service.add_log"), \
         patch("backend.services.search_service.JobRoomProvider"), \
         patch("backend.services.search_service.SwissDevJobsProvider"), \
         patch("backend.services.search_service.AdeccoProvider"), \
         patch("backend.services.search_service.LocalDbProvider"), \
         patch("backend.services.search_service.update_status") as mock_update:
        mock_llm.generate_search_plan = AsyncMock(return_value=[])
        await search_service.run_search(1)
        mock_update.assert_any_call(1, state="done", terminal_reason="no_queries")


@pytest.mark.asyncio
async def test_run_search_keeps_error_state_when_plan_failed(search_service, mock_profile_repo, mock_db):
    mock_profile = MagicMock()
    mock_profile.id = 1
    mock_profile.user_id = 42
    mock_profile.max_queries = 5
    mock_profile.max_occupation_queries = None
    mock_profile.max_keyword_queries = None
    mock_profile.cv_content = "CV"
    mock_profile.role_description = "Dev"
    mock_profile.search_strategy = ""
    mock_profile.latitude = None
    mock_profile.longitude = None
    mock_profile.cached_queries = None
    mock_profile.cached_cv_summary = None
    mock_profile_repo.get.return_value = mock_profile
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch("backend.services.search_service.init_status"), \
         patch("backend.services.search_service.add_log"), \
         patch("backend.services.search_service.JobRoomProvider"), \
         patch("backend.services.search_service.SwissDevJobsProvider"), \
         patch("backend.services.search_service.AdeccoProvider"), \
         patch("backend.services.search_service.LocalDbProvider"), \
         patch.object(search_service, "_generate_plan", AsyncMock(return_value=[])), \
         patch("backend.services.search_service.get_status", return_value={"state": "error", "terminal_reason": "llm_plan_error"}), \
         patch("backend.services.search_service.update_status") as mock_update:
        await search_service.run_search(1)

        unexpected = [
            call
            for call in mock_update.call_args_list
            if call.kwargs.get("state") == "done" and call.kwargs.get("terminal_reason") == "no_queries"
        ]
        assert unexpected == []


def test_build_degraded_fallback_plan_generates_minimal_queries(search_service):
    profile = MagicMock()
    profile.max_queries = 2
    profile_dict = {
        "role_description": "Backend Developer, Platform Engineer",
        "search_strategy": "Focus on Python and Docker",
        "cv_content": "5 years Python, Docker, SQL",
    }

    with patch("backend.services.search_service.settings.SEARCH_DEGRADED_PLAN_MAX_QUERIES", 3), \
         patch("backend.services.search_service.settings.SEARCH_DEGRADED_PLAN_MAX_KEYWORDS", 2):
        plan = search_service._build_degraded_fallback_plan(profile_dict, profile)

    assert len(plan) == 2
    assert all(item.get("query") for item in plan)
    assert all(item.get("type") in {"occupation", "keyword"} for item in plan)


@pytest.mark.asyncio
async def test_run_search_uses_degraded_fallback_plan_when_enabled(search_service, mock_profile_repo, mock_db):
    mock_profile = MagicMock()
    mock_profile.id = 1
    mock_profile.user_id = 42
    mock_profile.max_queries = 5
    mock_profile.max_occupation_queries = None
    mock_profile.max_keyword_queries = None
    mock_profile.cv_content = "CV"
    mock_profile.role_description = "Backend Developer"
    mock_profile.search_strategy = ""
    mock_profile.latitude = None
    mock_profile.longitude = None
    mock_profile.cached_queries = None
    mock_profile.cached_cv_summary = None
    mock_profile_repo.get.return_value = mock_profile
    mock_db.query.return_value.filter.return_value.first.return_value = None

    fallback_plan = [{"query": "Backend Developer", "type": "occupation", "domain": "general", "language": "en"}]

    with patch.object(search_service, "_generate_plan", new=AsyncMock(return_value=[])), \
         patch.object(search_service, "_build_degraded_fallback_plan", return_value=fallback_plan), \
         patch.object(search_service, "_execute_searches", new=AsyncMock(return_value=[])) as mock_exec, \
         patch.object(search_service, "_normalize_user_profile", new=AsyncMock(return_value={})), \
         patch("backend.services.search_service.llm_service.summarize_cv", new=AsyncMock(return_value="")), \
         patch("backend.services.search_service.add_log"), \
         patch("backend.services.search_service.init_status"), \
         patch("backend.services.search_service.update_status") as mock_update, \
         patch("backend.services.search_service.settings.SEARCH_ENABLE_DEGRADED_PLAN_FALLBACK", True):
        await search_service.run_search(1)

    mock_exec.assert_awaited_once()
    mock_update.assert_any_call(
        1,
        terminal_reason="degraded_plan_fallback",
        degraded_mode=True,
        total_searches=1,
        searches_generated=fallback_plan,
    )
    mock_update.assert_any_call(1, state="done", terminal_reason="no_results")


def test_apply_query_preferences_respects_language_and_domain(search_service):
    prefs = {
        "preferred_languages": ["de"],
        "preferred_domains": ["it"],
    }
    searches = [
        {"query": "Software Engineer", "language": "en", "domain": "it", "type": "occupation"},
        {"query": "Java Entwickler", "language": "de", "domain": "it", "type": "occupation"},
        {"query": "Data Analyst", "language": "de", "domain": "finance", "type": "occupation"},
    ]

    filtered, stats = search_service._apply_query_preferences(searches, prefs)
    assert len(filtered) == 1
    assert filtered[0]["query"] == "Java Entwickler"
    assert stats["dropped_language"] == 1
    assert stats["dropped_domain"] == 1


def test_apply_structured_filters_uses_normalized_languages(search_service):
    german_job = MagicMock()
    german_job._normalized_job_data = {
        "required_languages": [{"code": "de", "level": "B2"}],
    }
    german_job.language_skills = []
    german_job.employment = MagicMock(workload_min=80, workload_max=100)
    german_job.location = MagicMock(coordinates=None)

    french_job = MagicMock()
    french_job._normalized_job_data = {
        "required_languages": [{"code": "fr", "level": "B2"}],
    }
    french_job.language_skills = []
    french_job.employment = MagicMock(workload_min=80, workload_max=100)
    french_job.location = MagicMock(coordinates=None)

    preferences = {
        "preferred_languages": ["de"],
        "preferred_domains": [],
        "remote_only": False,
        "salary_min_chf": None,
        "workload_min": None,
        "workload_max": None,
        "hard_max_distance_km": None,
    }

    with patch("backend.services.search_service.add_log"):
        kept = search_service._apply_structured_filters(
            1,
            {"latitude": None, "longitude": None, "workload_filter": "80-100"},
            [german_job, french_job],
            preferences,
        )

    assert kept == [german_job]


def test_apply_structured_filters_uses_profile_workload_filter(search_service):
    fitting_job = MagicMock()
    fitting_job._normalized_job_data = {"workload_min": 80, "workload_max": 100}
    fitting_job.language_skills = []
    fitting_job.employment = MagicMock(workload_min=80, workload_max=100)
    fitting_job.location = MagicMock(coordinates=None)

    too_low_job = MagicMock()
    too_low_job._normalized_job_data = {"workload_min": 40, "workload_max": 60}
    too_low_job.language_skills = []
    too_low_job.employment = MagicMock(workload_min=40, workload_max=60)
    too_low_job.location = MagicMock(coordinates=None)

    preferences = {
        "preferred_languages": [],
        "preferred_domains": [],
        "remote_only": False,
        "salary_min_chf": None,
        "workload_min": None,
        "workload_max": None,
        "hard_max_distance_km": None,
    }

    with patch("backend.services.search_service.add_log"):
        kept = search_service._apply_structured_filters(
            1,
            {"latitude": None, "longitude": None, "workload_filter": "80-100"},
            [fitting_job, too_low_job],
            preferences,
        )

    assert kept == [fitting_job]
