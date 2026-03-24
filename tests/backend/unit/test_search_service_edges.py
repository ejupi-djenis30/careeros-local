import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from backend.services.search_service import SearchService, get_search_service
from backend.schemas import SearchProfile

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_service():
    mock_job_repo = MagicMock()
    mock_profile_repo = MagicMock()
    service = SearchService(job_repo=mock_job_repo, profile_repo=mock_profile_repo)
    return service

def test_get_search_service():
    mock_db = MagicMock()
    service = get_search_service(mock_db)
    assert isinstance(service, SearchService)

async def test_deduplicate(mock_service):
    profile = MagicMock()
    profile.id = 1
    
    db_row = MagicMock()
    db_row.configure_mock(platform="job_room", platform_job_id="123", external_url="http://x", title="dev", company="ACME")
    mock_service.job_repo.get_profile_job_identifiers.return_value = [db_row]
    
    from types import SimpleNamespace
    
    # 1. Exact replicate by explicit key
    job1 = SimpleNamespace(
        source="job_room", id="123", title="dev", 
        company=SimpleNamespace(name="ACME"), external_url="http://x"
    )
    
    # 2. Replicate by URL
    job2 = SimpleNamespace(
        source="other", id="999", title="dev",
        company=SimpleNamespace(name="ACME"), external_url="http://x"
    )
    
    # 3. Fuzzy match
    job3 = SimpleNamespace(
        source="other2", id="888", title=" d e v ",
        company=SimpleNamespace(name="A.C.M.E"), external_url="http://y"
    )
    
    # 4. Same fuzzy key among new jobs
    job4 = SimpleNamespace(
        source="new", id="111", title="Software Engineer",
        company=SimpleNamespace(name="NewCo"), external_url="http://new"
    )
    
    job5 = SimpleNamespace(
        source="new", id="222", title="Software Engineer",
        company=SimpleNamespace(name="NewCo"), external_url="http://new2"
    )
    
    unique_jobs, duplicates = mock_service._deduplicate(profile, [job1, job2, job3, job4, job5])
    
    assert len(unique_jobs) == 2
    assert unique_jobs[0].id == "888"
    assert unique_jobs[1].id == "111"
    assert duplicates == 3

async def test_analyze_and_save_success(mock_service):
    profile_dict = {
        "id": 1,
        "user_id": 1,
        "latitude": 47.0,
        "longitude": 8.0,
        "role_description": "developer"
    }
    
    job1 = MagicMock()
    job1.source = "job_room"
    job1.id = "100"
    job1.title = "Python Dev"
    job1.descriptions = [MagicMock(description="Cool job")]
    job1.occupations = [MagicMock(education_code="123", qualification_code="456")]
    job1.location = MagicMock(city="Zurich", coordinates=MagicMock(lat=47.3, lon=8.5))
    job1.employment = MagicMock(workload_min=80, workload_max=100)
    job1.language_skills = [MagicMock(language_code="en", spoken_level="C1")]
    job1.company = MagicMock()
    job1.company.name = "BigTech"
    job1.application = MagicMock(form_url="http://app", email="hr@ht")
    job1.external_url = None
    job1.publication = MagicMock(start_date="2024-01-01T10:00:00Z")
    
    # Needs geocode resolution
    job2 = MagicMock()
    job2.source = "adecco"
    job2.id = "200"
    job2.title = "Java Dev"
    job2.descriptions = [MagicMock(description="Boring job " * 100)] # hits char limit
    job2.occupations = []
    job2.location = MagicMock(city="Bern", coordinates=None)
    job2.employment = MagicMock(workload_min=100, workload_max=100)
    job2.language_skills = []
    job2.company = None
    job2.application = None
    job2.external_url = "http://job2"
    job2.publication = MagicMock(start_date="2024-01-01")
    
    with patch("backend.services.search_service.llm_service.analyze_job_batch") as mock_analyze:
        # Return 2 results
        # 1st is relevant, 2nd is not
        mock_analyze.return_value = [
            {"relevant": True, "affinity_score": 90, "worth_applying": True},
            {"relevant": False}
        ]
        
        with patch("backend.services.utils.geocode_location") as mock_geocode:
            mock_geocode.return_value = MagicMock(lat=46.9, lon=7.4)
            
            with patch("backend.services.search_service.SessionLocal") as mock_session_local:
                mock_session = MagicMock()
                mock_session_local.return_value = mock_session
                mock_session.query.return_value.filter.return_value.all.return_value = []
                
                saved, skipped = await mock_service._analyze_and_save(1, profile_dict, [job1, job2])
                
                assert saved == 1
                assert skipped == 1
                mock_session.add_all.assert_called()
                mock_session.commit.assert_called()

async def test_analyze_and_save_db_error(mock_service):
    profile_dict = {"id": 1, "user_id": 1}
    job1 = MagicMock()
    job1.descriptions = [MagicMock(description="x")]
    
    with patch("backend.services.search_service.llm_service.analyze_job_batch") as mock_analyze:
        mock_analyze.return_value = [{"relevant": True}]
        
        with patch("backend.services.search_service.SessionLocal") as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value = mock_session
            mock_session.query.return_value.filter.return_value.all.return_value = []
            
            mock_session.commit.side_effect = Exception("DB Fail")
            
            saved, skipped = await mock_service._analyze_and_save(1, profile_dict, [job1])
            assert saved == 0
            assert skipped == 1
            mock_session.rollback.assert_called_once()

async def test_analyze_and_save_batch_exception(mock_service):
    profile_dict = {"id": 1, "user_id": 1}
    job1 = MagicMock()
    job1.descriptions = [MagicMock(description="x")]
    
    with patch("backend.services.search_service.llm_service.analyze_job_batch", side_effect=Exception("API limit")):
        saved, skipped = await mock_service._analyze_and_save(1, profile_dict, [job1])
        assert saved == 0
        assert skipped == 1

async def test_run_search_cv_summarization_and_unexpected(mock_service):
    profile = MagicMock(id=1)
    profile_dict = {"id": 1, "cv_content": "Long CV content " * 100}
    
    # 1. Test run_search exception wrapping
    with patch.object(mock_service, "_execute_searches", side_effect=Exception("Critical")):
        await mock_service.run_search(1)
        # Should not raise, just catch and log

    # 2. Test CV summarization usage and deduplicate call
    with patch.object(mock_service, "_execute_searches") as mock_exec, \
         patch("backend.services.search_service.llm_service.summarize_cv", return_value="Short CV"), \
         patch.object(mock_service, "_deduplicate") as mock_dedup, \
         patch.object(mock_service, "_relevance_filter", return_value=[]), \
         patch.object(mock_service, "_analyze_and_save", return_value=(0,0)), \
         patch.object(mock_service, "_generate_plan", return_value=[{"query":"dev"}]), \
         patch.object(mock_service.profile_repo, "get") as mock_get_profile:
        
        mock_get_profile.return_value = profile
        mock_service.profile_repo.get_dict.return_value = profile_dict
        job1 = MagicMock()
        mock_exec.return_value = [job1]
        mock_dedup.return_value = ([job1], 0)
        
        await mock_service.run_search(1)
        
        mock_dedup.assert_called_once()

async def test_run_search_profile_not_found(mock_service):
    mock_service.profile_repo.get = MagicMock(return_value=None)
    await mock_service.run_search(999)

async def test_generate_plan_exception(mock_service):
    with patch("backend.services.search_service.llm_service.generate_search_plan", side_effect=Exception("LLM Fail")):
        res = await mock_service._generate_plan(1, {}, MagicMock(max_queries=5), {}, {})
        assert res == []

async def test_generate_plan_empty_query(mock_service):
    with patch("backend.services.search_service.llm_service.generate_search_plan", return_value=[{"query": ""}, {"query": "dev"}]):
        profile = MagicMock(max_queries=5, cached_queries=None)
        res = await mock_service._generate_plan(1, {}, profile, {}, {})
        assert len(res) == 1
        assert res[0]["query"] == "dev"

async def test_relevance_filter_exception(mock_service):
    job = MagicMock()
    job.title = "test"
    job.company = MagicMock()
    job.company.name = "test"
    job.descriptions = [MagicMock(description="desc")]
    job._summary = None
    with patch("backend.services.search_service.llm_service.check_relevance_batch", side_effect=Exception("relevance fail")):
        res = await mock_service._relevance_filter(1, {}, [job])
        assert len(res) == 1

async def test_analyze_and_save_stopped_and_truncation(mock_service):
    profile_dict = {"id": 1, "user_id": 1, "latitude": 47.0, "longitude": 8.0}
    
    from types import SimpleNamespace
    
    # Needs truncation and geocoding
    job1 = SimpleNamespace(
        id="1",
        source="test",
        title="test title",
        company=SimpleNamespace(name="test inc"),
        location=SimpleNamespace(city="Bern", coordinates=None),
        employment=SimpleNamespace(workload_min=100, workload_max=100),
        application=None,
        external_url="x",
        publication=None,
        descriptions=[SimpleNamespace(description="A"*5000)] # Over max
    )
    
    with patch("backend.services.search_service.settings.MAX_DESCRIPTION_CHARS", 100), \
         patch("backend.services.search_service.get_status", return_value={"state": "searching"}), \
         patch("backend.services.search_service.llm_service.analyze_job_batch", return_value=[{"relevant": True, "affinity_score": 50, "worth_applying": False}]), \
         patch("backend.services.utils.geocode_location", return_value=MagicMock(lat=46.9, lon=7.4)), \
         patch("backend.services.search_service.SessionLocal") as mock_session_local:
         
         mock_session = MagicMock()
         mock_session.query.return_value.filter.return_value.all.return_value = []
         mock_session_local.return_value = mock_session
         
         saved, skipped = await mock_service._analyze_and_save(1, profile_dict, [job1])
         assert saved == 1
         assert skipped == 0

async def test_analyze_and_save_length_mismatch(mock_service):
    with patch("backend.services.search_service.get_status", return_value={"state": "searching"}), \
         patch("backend.services.search_service.llm_service.analyze_job_batch", return_value=[]):
        saved, skipped = await mock_service._analyze_and_save(1, {}, [MagicMock(descriptions=[MagicMock(description="x")])])
        assert saved == 0
        assert skipped == 1

async def test_analyze_and_save_stopped(mock_service):
    with patch("backend.services.search_service.get_status", return_value={"state": "stopped"}):
        saved, skipped = await mock_service._analyze_and_save(1, {}, [MagicMock()])
        assert saved == 0

async def test_execute_searches_flow(mock_service):
    profile = MagicMock()
    searches = [{"query": "dev", "domain": "IT", "type": "occupation"}]
    
    mock_adecco = AsyncMock()
    # provider info mocked
    p_info = {"adecco": {}, "job_room": {}}
    av_prov = {"adecco": mock_adecco, "job_room": mock_adecco}
    
    with patch("backend.services.search_service.avam_mapper.resolve", return_value=[]), \
         patch("backend.services.search_service.get_compatible_providers", return_value=["job_room", "adecco"]), \
         patch("backend.services.search_service.build_search_request", return_value=MagicMock()), \
         patch("backend.services.search_service.get_status") as mock_status:
         
        mock_status.side_effect = [{"state": "searching"}, {"state": "searching"}] # Avoid stopping early
        
        # Test pagination and sleep
        mock_adecco.search = AsyncMock()
        mock_adecco.search.return_value = MagicMock(items=[MagicMock(), MagicMock()], total_pages=1)
        
        # We need to just call _execute_searches, which calls execute_single_search internally
        with patch.object(mock_service, "_execute_searches") as mock_exec: # Wait! I'm trying to test _execute_searches!
            pass # We don't patch it, we execute it!
            
        res = await mock_service._execute_searches(1, profile, searches, av_prov, p_info)
        assert len(res) > 0

async def test_execute_searches_aborts_and_pagination(mock_service):
    searches = [{"query": "dev", "domain": "IT", "type": "keyword"}]
    mock_adecco = AsyncMock()
    # Mock search so it produces 2 pages, giving the loop a chance to sleep and break
    mock_adecco.search = AsyncMock()
    # First call page 0, second page 1
    mock_adecco.search.return_value = MagicMock(items=[MagicMock()], total_pages=2)
    av_prov = {"adecco": mock_adecco}
    
    with patch("backend.services.search_service.get_compatible_providers", return_value=["adecco"]), \
         patch("backend.services.search_service.get_status") as mock_status:
         
         # 1. Start searching... 2. second page loop checks status again and aborts
         mock_status.side_effect = [{"state": "searching"}, {"state": "stopped"}]
         
         from types import SimpleNamespace
         profile = SimpleNamespace(location_filter="", posted_within_days=10, max_distance=10, workload_filter="", latitude=None, longitude=None, contract_type="")
         
         res = await mock_service._execute_searches(1, profile, searches, av_prov, {"adecco": {}})
         # Because it stopped early, it just returns items from the first page
         assert len(res) > 0

async def test_execute_searches_incompatible_or_stopped(mock_service):
    # Stopped immediately
    with patch("backend.services.search_service.get_status", return_value={"state": "stopped"}):
        res = await mock_service._execute_searches(1, MagicMock(), [{"query":"t"}], {}, {})
        assert res == []
        
    # Incompatible domain
    with patch("backend.services.search_service.get_status", return_value={"state": "searching"}), \
         patch("backend.services.search_service.get_compatible_providers", return_value=[]):
        res = await mock_service._execute_searches(1, MagicMock(), [{"query":"t"}], {}, {})
        assert res == []

async def test_relevance_filter_drops(mock_service):
    job = MagicMock()
    with patch("backend.services.search_service.llm_service.check_relevance_batch", return_value=[False]):
        res = await mock_service._relevance_filter(1, {}, [job])
        assert len(res) == 0

async def test_run_search_finally_nameerror(mock_service):
    # simulate available_providers not defined NameError
    with patch.object(mock_service, "_generate_plan", side_effect=Exception("Fast fail")):
        # We manually raise NameError during cleanup
        mock_service.profile_repo.get = MagicMock(side_effect=NameError("Simulated available_providers fail"))
        await mock_service.run_search(1)

async def test_run_search_cleanup_close(mock_service):
    # Setup mock to reach finally block with populated available_providers
    profile = MagicMock(id=1, cv_content=None)
    mock_service.profile_repo.get = MagicMock(return_value=profile)
    
    provider1 = AsyncMock()
    provider1.close = AsyncMock()
    
    provider2 = MagicMock()
    delattr(provider2, "close") # ensure no close method
    provider2._session = AsyncMock()
    provider2._session.aclose = AsyncMock()
    
    # We patch the provider initializations directly
    with patch("backend.services.search_service.get_compatible_providers", return_value=["job_room", "adecco"]), \
         patch("backend.services.search_service.JobRoomProvider", return_value=provider1), \
         patch("backend.services.search_service.AdeccoProvider", return_value=provider2), \
         patch.object(mock_service, "_generate_plan", side_effect=Exception("fast fail")): # fast exit to run finally
         await mock_service.run_search(1)
         
    provider1.close.assert_called_once()
    provider2._session.aclose.assert_called_once()
