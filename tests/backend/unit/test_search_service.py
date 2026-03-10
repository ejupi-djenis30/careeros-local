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
def search_service(mock_job_repo, mock_profile_repo):
    return SearchService(mock_job_repo, mock_profile_repo)

@pytest.mark.asyncio
async def test_run_search_success(search_service, mock_profile_repo, mock_job_repo):
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
    
    mock_job_repo.get_user_job_identifiers.return_value = []
    
    mock_provider = MagicMock()
    mock_provider.get_provider_info.return_value = MagicMock(accepted_domains=["*"])
    mock_provider.search = AsyncMock(return_value=MagicMock(items=[MagicMock(id="job1", source="test", external_url="url1")]))
    
    with patch("backend.services.search_service.llm_service") as mock_llm, \
         patch("backend.services.search_service.init_status"), \
         patch("backend.services.search_service.add_log"), \
         patch("backend.services.search_service.update_status"), \
         patch("backend.services.search_service.JobRoomProvider", return_value=mock_provider), \
         patch("backend.services.search_service.SwissDevJobsProvider", return_value=mock_provider), \
         patch("backend.services.search_service.LocalDbProvider", return_value=mock_provider):
        
        # New format: domain instead of provider
        mock_llm.generate_search_plan = AsyncMock(return_value=[
            {"domain": "it", "query": "Software Engineer", "type": "occupation", "language": "en"}
        ])
        
        await search_service.run_search(1)
        
        mock_llm.generate_search_plan.assert_called_once()
        # All 3 providers should be called since domain=it matches both generalists AND it-only
        assert mock_provider.search.await_count >= 1

@pytest.mark.asyncio
async def test_run_search_stopped_by_user(search_service, mock_profile_repo):
    mock_profile = MagicMock()
    mock_profile.is_stopped = True
    mock_profile_repo.get.return_value = mock_profile
    
    with patch("backend.services.search_service.init_status"), \
         patch("backend.services.search_service.add_log"), \
         patch("backend.services.search_service.update_status") as mock_update:
        
        await search_service.run_search(1)

@pytest.mark.asyncio
async def test_run_search_no_plan(search_service, mock_profile_repo):
    mock_profile_repo.get.return_value = MagicMock()
    with patch("backend.services.search_service.llm_service") as mock_llm, \
         patch("backend.services.search_service.init_status"), \
         patch("backend.services.search_service.add_log"), \
         patch("backend.services.search_service.update_status") as mock_update:
        mock_llm.generate_search_plan = AsyncMock(return_value=[])
        await search_service.run_search(1)
        mock_update.assert_any_call(1, state="done", jobs_found=0, jobs_new=0)
