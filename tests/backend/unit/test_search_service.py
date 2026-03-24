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
        mock_llm.check_relevance_batch = AsyncMock(return_value=[True])
        mock_llm.analyze_job_batch = AsyncMock(return_value=[{"relevant": True, "affinity_score": 80}])
        
        await svc.run_search(1)
        
        mock_llm.generate_search_plan.assert_called_once()
        # All 3 providers should be called since domain=it matches both generalists AND it-only
        assert mock_provider.search.await_count >= 1

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
         patch("backend.services.search_service.update_status") as mock_update:
        
        await search_service.run_search(1)

@pytest.mark.asyncio
async def test_run_search_no_plan(search_service, mock_profile_repo, mock_db):
    mock_profile_repo.get.return_value = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    with patch("backend.services.search_service.llm_service") as mock_llm, \
         patch("backend.services.search_service.init_status"), \
         patch("backend.services.search_service.add_log"), \
         patch("backend.services.search_service.JobRoomProvider"), \
         patch("backend.services.search_service.SwissDevJobsProvider"), \
         patch("backend.services.search_service.AdeccoProvider"), \
         patch("backend.services.search_service.LocalDbProvider"), \
         patch("backend.services.search_service.update_status") as mock_update:
        mock_llm.generate_search_plan = AsyncMock(return_value=[])
        await search_service.run_search(1)
        mock_update.assert_any_call(1, state="done")

@pytest.mark.asyncio
async def test_relevance_filter_passes_correct_data(search_service):
    """Verify _relevance_filter prepares job_data correctly and passes search_strategy."""
    mock_job = MagicMock()
    mock_job.title = "Software Engineer"
    mock_job.company.name = "Google"
    mock_job.descriptions = [MagicMock(description="Developing cool stuff at Google")]
    mock_job._summary = None  # Ensure it falls back to description in test
    
    profile_dict = {
        "role_description": "Dev",
        "search_strategy": "Remote only"
    }
    
    with patch("backend.services.search_service.llm_service") as mock_llm:
        mock_llm.check_relevance_batch = AsyncMock(return_value=[True])
        
        await search_service._relevance_filter(123, profile_dict, [mock_job])
        
        mock_llm.check_relevance_batch.assert_called_once()
        args, kwargs = mock_llm.check_relevance_batch.call_args
        
        job_data = args[0]
        assert len(job_data) == 1
        assert job_data[0]["title"] == "Software Engineer"
        assert job_data[0]["company"] == "Google"
        assert job_data[0]["description_snippet"] == "Developing cool stuff at Google"
        
        assert args[1] == "Dev"
        assert kwargs["search_strategy"] == "Remote only"
