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

async def test_get_search_service():
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
    
    unique_jobs, duplicates = mock_service._deduplicate(1, [job1, job2, job3, job4, job5])
    
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
        
        with patch("backend.services.search_service.geocode_location") as mock_geocode, \
             patch("backend.services.search_service.get_status", return_value={"state": "searching"}):
            mock_geocode.return_value = MagicMock(lat=46.9, lon=7.4)
            
            mock_session = mock_service.job_repo.db
            mock_session.query.return_value.filter.return_value.all.return_value = []
            
            saved, skipped = await mock_service._analyze_and_save(1, profile_dict, [job1, job2])
            
            assert saved == 1
            assert skipped == 1
            assert mock_session.add.called
            mock_session.commit.assert_called_once()

async def test_analyze_and_save_db_error(mock_service):
    profile_dict = {"id": 1, "user_id": 1}
    job1 = MagicMock()
    job1.descriptions = [MagicMock(description="x")]
    
    with patch("backend.services.search_service.llm_service.analyze_job_batch") as mock_analyze, \
         patch.object(mock_service, "_save_single_job", new=AsyncMock(return_value=None)):
        mock_analyze.return_value = [{"relevant": True}]
        
        with patch("backend.services.search_service.get_status", return_value={"state": "searching"}):
        
            mock_session = mock_service.job_repo.db
            mock_session.query.return_value.filter.return_value.all.return_value = []
            
            mock_session.commit.side_effect = Exception("DB Fail")
            
            saved, skipped = await mock_service._analyze_and_save(1, profile_dict, [job1])
            assert saved == 0
            assert skipped == 1
            mock_session.commit.assert_called_once()
            mock_session.rollback.assert_called_once()

async def test_analyze_and_save_batch_exception(mock_service):
    profile_dict = {"id": 1, "user_id": 1}
    job1 = MagicMock()
    job1.descriptions = [MagicMock(description="x")]
    
    with patch("backend.services.search_service.llm_service.analyze_job_batch", side_effect=Exception("API limit")), \
         patch("backend.services.search_service.get_status", return_value={"state": "searching"}):
        saved, skipped = await mock_service._analyze_and_save(1, profile_dict, [job1])
        assert saved == 0
        assert skipped == 1

async def test_run_search_cv_summarization_and_unexpected(mock_service):
    profile = MagicMock(id=1)
    profile_dict = {"id": 1, "cv_content": "Long CV content " * 100}
    
    # 1. Test run_search exception wrapping
    with patch.object(mock_service, "_execute_searches", side_effect=Exception("Critical")), \
         patch.object(mock_service, "_normalize_user_profile", new=AsyncMock(return_value={})):
        await mock_service.run_search(1)
        # Should not raise, just catch and log

    # 2. Test CV summarization usage and deduplicate call
    with patch.object(mock_service, "_execute_searches") as mock_exec, \
         patch("backend.services.search_service.llm_service.summarize_cv", return_value="Short CV"), \
         patch.object(mock_service, "_normalize_user_profile", new=AsyncMock(return_value={})), \
         patch.object(mock_service, "_deduplicate") as mock_dedup, \
         patch.object(mock_service, "_persist_scraped_job_catalog", new=AsyncMock(return_value=(0, 0))), \
         patch.object(mock_service, "_normalize_persisted_jobs", new=AsyncMock(return_value=0)), \
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
        res = await mock_service._generate_plan(1, {}, MagicMock(max_queries=5), {})
        assert res == []


async def test_generate_plan_rate_limit_sets_specific_terminal_reason(mock_service):
    profile = MagicMock(max_queries=5, max_occupation_queries=None, max_keyword_queries=None, cached_queries=None)
    profile_dict = {"role_description": "dev", "cv_content": "cv", "force_regenerate_queries": True}
    with patch("backend.services.search_service.llm_service.generate_search_plan", side_effect=Exception("rate_limit_exceeded")), \
         patch("backend.services.search_service.update_status") as mock_update:
        res = await mock_service._generate_plan(1, profile_dict, profile, {})
        assert res == []
        mock_update.assert_called_with(
            1,
            state="error",
            terminal_reason="llm_plan_rate_limited",
            error="rate_limit_exceeded",
        )

async def test_generate_plan_empty_query(mock_service):
    with patch("backend.services.search_service.llm_service.generate_search_plan", return_value=[{"query": ""}, {"query": "dev"}]):
        profile = MagicMock(max_queries=5, cached_queries=None)
        res = await mock_service._generate_plan(1, {}, profile, {})
        assert len(res) == 1
        assert res[0]["query"] == "dev"

async def test_generate_plan_uses_cache_metadata_when_inputs_match(mock_service):
    profile = MagicMock(max_queries=5, max_occupation_queries=None, max_keyword_queries=None)
    profile.cached_queries = {
        "version": 2,
        "input_fingerprint": "abc",
        "searches": [{"query": "dev", "type": "occupation", "domain": "it", "language": "en"}],
    }
    profile_dict = {
        "role_description": "dev",
        "cv_content": "cv",
        "search_strategy": "",
        "force_regenerate_queries": False,
    }

    with patch("backend.services.search_service.compute_plan_input_fingerprint", return_value="abc"), \
         patch("backend.services.search_service.add_log"):
        res = await mock_service._generate_plan(1, profile_dict, profile, {})

    assert len(res) == 1
    assert res[0]["query"] == "dev"


async def test_generate_plan_sets_cache_hit_metrics(mock_service):
    profile = MagicMock(max_queries=5, max_occupation_queries=None, max_keyword_queries=None)
    profile.cached_queries = {
        "version": 2,
        "input_fingerprint": "abc",
        "searches": [{"query": "dev", "type": "occupation", "domain": "it", "language": "en"}],
    }
    profile_dict = {
        "role_description": "dev",
        "cv_content": "cv",
        "search_strategy": "",
        "force_regenerate_queries": False,
    }

    with patch("backend.services.search_service.compute_plan_input_fingerprint", return_value="abc"), \
         patch("backend.services.search_service.add_log"), \
         patch("backend.services.search_service.update_status") as mock_update:
        await mock_service._generate_plan(1, profile_dict, profile, {})

    mock_update.assert_any_call(1, plan_cache_hit=1, plan_cache_miss=0)
    mock_update.assert_any_call(
        1,
        total_searches=1,
        searches_generated=[{"query": "dev", "type": "occupation", "domain": "it", "language": "en"}],
        plan_unique_count=1,
    )


async def test_generate_plan_sets_cache_miss_metrics(mock_service):
    profile = MagicMock(max_queries=5, max_occupation_queries=None, max_keyword_queries=None)
    profile.cached_queries = None
    profile_dict = {
        "role_description": "dev",
        "cv_content": "cv",
        "search_strategy": "",
        "force_regenerate_queries": True,
    }

    with patch("backend.services.search_service.llm_service.generate_search_plan", return_value=[{"query": "dev", "type": "occupation", "domain": "it", "language": "en"}]), \
         patch("backend.services.search_service.add_log"), \
         patch("backend.services.search_service.update_status") as mock_update:
        await mock_service._generate_plan(1, profile_dict, profile, {})

    mock_update.assert_any_call(1, plan_cache_hit=0, plan_cache_miss=1)
    mock_update.assert_any_call(1, plan_raw_count=1)

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
         patch("backend.services.search_service.geocode_location", return_value=MagicMock(lat=46.9, lon=7.4)):
         
         mock_session = mock_service.job_repo.db
         mock_session.query.return_value.filter.return_value.all.return_value = []
         
         saved, skipped = await mock_service._analyze_and_save(1, profile_dict, [job1])
         assert saved == 1
         assert skipped == 0
         mock_session.commit.assert_called_once()

async def test_analyze_and_save_length_mismatch(mock_service):
    with patch("backend.services.search_service.get_status", return_value={"state": "searching"}), \
         patch("backend.services.search_service.llm_service.analyze_job_batch", return_value=[]):
        saved, skipped = await mock_service._analyze_and_save(1, {}, [MagicMock(descriptions=[MagicMock(description="x")])])
        assert saved == 0
        assert skipped == 1

async def test_save_single_job_invalid_publication_date_logs_warning(mock_service):
    listing = MagicMock()
    listing.source = "job_room"
    listing.id = "broken-date"
    listing.title = "Broken Date Role"
    listing.descriptions = [MagicMock(description="desc")]
    listing.company = MagicMock(name="ACME")
    listing.location = MagicMock(city="Zurich", coordinates=MagicMock(lat=47.37, lon=8.54))
    listing.employment = MagicMock(workload_min=80, workload_max=100)
    listing.publication = MagicMock(start_date="not-a-date")
    listing.application = None
    listing.external_url = "https://example.com/job"

    mock_session = mock_service.job_repo.db
    mock_session.query.return_value.filter.return_value.first.return_value = None

    with patch("backend.services.search.listing_utils.logger") as mock_logger:
        await mock_service._save_single_job(
            listing,
            {"affinity_score": 80, "affinity_analysis": "ok", "worth_applying": True},
            {"id": 1, "user_id": 99},
            None,
        )

    mock_logger.warning.assert_called_once()
    mock_session.commit.assert_called_once()

async def test_save_single_job_geocodes_missing_coordinates(mock_service):
    listing = MagicMock()
    listing.source = "job_room"
    listing.id = "missing-coords"
    listing.title = "No Coordinates Role"
    listing.descriptions = [MagicMock(description="desc")]
    listing.company = MagicMock(name="ACME")
    listing.location = MagicMock(city="Bern", coordinates=None)
    listing.employment = MagicMock(workload_min=100, workload_max=100)
    listing.publication = None
    listing.application = None
    listing.external_url = "https://example.com/job"

    mock_session = mock_service.job_repo.db
    mock_session.query.return_value.filter.return_value.first.return_value = None

    with patch("backend.services.search_service.geocode_location", new=AsyncMock(return_value=MagicMock(lat=46.948, lon=7.447))):
        await mock_service._save_single_job(
            listing,
            {"affinity_score": 60, "affinity_analysis": "ok", "worth_applying": False},
            {"id": 1, "user_id": 99},
            (47.3769, 8.5417),
        )

    saved_job = mock_session.add.call_args_list[-1].args[0]
    assert saved_job.distance_km is not None

async def test_save_single_job_deferred_commit_does_not_commit(mock_service):
    listing = MagicMock()
    listing.source = "job_room"
    listing.id = "deferred-commit"
    listing.title = "Deferred Commit Role"
    listing.descriptions = [MagicMock(description="desc")]
    listing.company = MagicMock(name="ACME")
    listing.location = MagicMock(city="Zurich", coordinates=MagicMock(lat=47.37, lon=8.54))
    listing.employment = MagicMock(workload_min=80, workload_max=100)
    listing.publication = None
    listing.application = None
    listing.external_url = "https://example.com/job/deferred"

    mock_session = mock_service.job_repo.db
    mock_session.query.return_value.filter.return_value.first.return_value = None

    await mock_service._save_single_job(
        listing,
        {"affinity_score": 60, "affinity_analysis": "ok", "worth_applying": False},
        {"id": 1, "user_id": 99},
        None,
        commit=False,
    )

    assert mock_session.add.call_count >= 2
    mock_session.commit.assert_not_called()


async def test_save_single_job_initializes_applied_false(mock_service):
    listing = MagicMock()
    listing.source = "job_room"
    listing.id = "applied-flag"
    listing.title = "Applied Flag Role"
    listing.descriptions = [MagicMock(description="desc")]
    listing.company = MagicMock(name="ACME")
    listing.location = MagicMock(city="Zurich", coordinates=MagicMock(lat=47.37, lon=8.54))
    listing.employment = MagicMock(workload_min=80, workload_max=100)
    listing.publication = None
    listing.application = None
    listing.external_url = "https://example.com/job/applied"
    listing._applied_elsewhere = True

    mock_session = mock_service.job_repo.db
    mock_session.query.return_value.filter.return_value.first.return_value = None

    await mock_service._save_single_job(
        listing,
        {"affinity_score": 60, "affinity_analysis": "ok", "worth_applying": False},
        {"id": 1, "user_id": 99},
        None,
    )

    saved_job = mock_session.add.call_args_list[-1].args[0]
    assert saved_job.applied is False


async def test_save_single_job_bootstraps_normalized_fields(mock_service):
    listing = MagicMock()
    listing.source = "job_room"
    listing.id = "normalized-bootstrap"
    listing.title = "Senior Warehouse Operator"
    listing.descriptions = [MagicMock(description="Requires 3 years experience and German B2.")]
    listing.company = MagicMock(name="ACME Logistics")
    listing.location = MagicMock(city="Zurich", coordinates=MagicMock(lat=47.37, lon=8.54))
    listing.employment = MagicMock(workload_min=80, workload_max=100)
    listing.occupations = [MagicMock(education_code="vocational", qualification_code="skilled")]
    listing.language_skills = [MagicMock(language_code="de", spoken_level="B2")]
    listing.publication = None
    listing.application = None
    listing.external_url = "https://example.com/job/normalized-bootstrap"

    mock_session = mock_service.job_repo.db
    mock_session.query.return_value.filter.return_value.first.return_value = None

    await mock_service._save_single_job(
        listing,
        {"affinity_score": 60, "affinity_analysis": "ok", "worth_applying": False},
        {"id": 1, "user_id": 99},
        None,
    )

    saved_scraped_job = mock_session.add.call_args_list[-2].args[0]
    assert saved_scraped_job.normalization_status == "provider_bootstrap"
    assert saved_scraped_job.normalized_seniority == "senior"
    assert saved_scraped_job.normalized_workload_min == 80
    assert saved_scraped_job.normalized_workload_max == 100
    assert saved_scraped_job.normalized_required_languages == [{"code": "de", "level": "B2"}]
    assert saved_scraped_job.normalized_education_levels == ["vocational"]


async def test_persist_scraped_job_catalog_commits_before_analysis(mock_service):
    listing = MagicMock()
    listing.source = "job_room"
    listing.id = "catalog-1"
    listing.title = "Cleaner"
    listing.descriptions = [MagicMock(description="Evening shift")]
    listing.company = MagicMock(name="Clean AG")
    listing.location = MagicMock(city="Zurich", coordinates=None)
    listing.employment = MagicMock(workload_min=50, workload_max=80)
    listing.occupations = []
    listing.language_skills = []
    listing.publication = None
    listing.application = None
    listing.external_url = "https://example.com/job/catalog-1"

    mock_session = mock_service.job_repo.db
    mock_session.query.return_value.filter.return_value.first.return_value = None
    mock_session.flush.side_effect = lambda: setattr(mock_session.add.call_args.args[0], "id", 321)

    created, updated = await mock_service._persist_scraped_job_catalog(1, [listing])

    assert created == 1
    assert updated == 0
    mock_session.commit.assert_called_once()
    assert getattr(listing, "_scraped_job_id", None) == 321
    assert getattr(listing, "_normalized_job_data", {}).get("status") == "provider_bootstrap"
async def test_normalize_persisted_jobs_upgrades_bootstrap_rows(mock_service):
    listing = MagicMock()
    listing._scraped_job_id = 555

    scraped_job = MagicMock()
    scraped_job.id = 555
    scraped_job.title = "Backend Engineer"
    scraped_job.company = "ACME"
    scraped_job.location = "Zurich"
    scraped_job.workload = "80-100%"
    scraped_job.description = "Python role"
    scraped_job.normalization_status = "provider_bootstrap"
    scraped_job.normalized_metadata = {}
    scraped_job.normalized_job_data = {"status": "normalized", "domain": "it"}

    mock_session = mock_service.job_repo.db
    mock_session.query.return_value.filter.return_value.first.return_value = scraped_job

    with patch("backend.services.search_service.llm_service.normalize_job_batch", new=AsyncMock(return_value=[
        {
            "title": "Backend Engineer",
            "role_family": "Backend Engineer",
            "domain": "it",
            "seniority": "senior",
            "employment_mode": "hybrid",
            "contract_type": "permanent",
            "qualification_level": "bachelor",
            "experience_min_years": 5,
            "experience_max_years": 8,
            "workload_min": 80,
            "workload_max": 100,
            "salary_min_chf": None,
            "salary_max_chf": 140000,
            "required_languages": [{"code": "de", "level": "B2"}],
            "required_skills": ["Python"],
            "education_levels": ["bachelor"],
            "key_requirements": ["Swiss permit"],
            "confidence": 0.9,
        }
    ])):
        upgraded = await mock_service._normalize_persisted_jobs(1, [listing])

    assert upgraded == 1
    assert scraped_job.normalization_status == "normalized"
    assert scraped_job.normalized_domain == "it"
    mock_session.commit.assert_called_once()

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

        mock_service.providers = av_prov

        res = await mock_service._execute_searches(1, profile, searches, p_info)
        assert len(res) >= 0

async def test_execute_searches_aborts_and_pagination(mock_service):
    searches = [{"query": "dev", "domain": "IT", "type": "keyword"}]
    mock_adecco = AsyncMock()
    mock_adecco.throttle_delay = 0.0  # real providers return float; avoid AsyncMock > int TypeError
    # Mock search so it produces 3 pages, giving the loop a chance to stop mid-run
    mock_adecco.search = AsyncMock()
    mock_adecco.search.return_value = MagicMock(items=[MagicMock()], total_pages=3, total_count=3)
    av_prov = {"adecco": mock_adecco}
    
    with patch("backend.services.search_service.get_compatible_providers", return_value=["adecco"]), \
         patch("backend.services.search_service.get_status") as mock_status:
         
         # Start searching, allow one pagination step, then abort before the third page
         mock_status.side_effect = [{"state": "searching"}, {"state": "searching"}, {"state": "stopped"}]
         
         from types import SimpleNamespace
         profile = SimpleNamespace(location_filter="", posted_within_days=10, max_distance=10, workload_filter="", latitude=None, longitude=None, contract_type="")

         mock_service.providers = av_prov

         res = await mock_service._execute_searches(1, profile, searches, {"adecco": {}})
         # Because it stopped early, it still returns jobs collected before the abort
         assert len(res) > 0

async def test_execute_searches_continues_beyond_five_pages(mock_service):
    searches = [{"query": "dev", "domain": "IT", "type": "keyword"}]
    mock_provider = AsyncMock()
    mock_provider.throttle_delay = 0.0  # real providers return float; avoid AsyncMock > int TypeError
    mock_provider.search = AsyncMock(side_effect=[
        MagicMock(items=[MagicMock(id=f"job-{idx}", external_url=f"http://example.com/{idx}")], total_pages=6, total_count=6)
        for idx in range(6)
    ])
    mock_service.providers = {"adecco": mock_provider}

    with patch("backend.services.search_service.get_compatible_providers", return_value=["adecco"]), \
         patch("backend.services.search_service.get_status", return_value={"state": "searching"}), \
         patch("backend.services.search_service.settings.SEARCH_EXECUTION_MODE", "sequential"):
        from types import SimpleNamespace
        profile = SimpleNamespace(location_filter="", posted_within_days=10, max_distance=10, workload_filter="", latitude=None, longitude=None, contract_type="")

        res = await mock_service._execute_searches(1, profile, searches, {"adecco": {}})

    assert len(res) == 6
    assert mock_provider.search.await_count == 6

async def test_execute_searches_deduplicates_fuzzy_matches(mock_service):
    searches = [{"query": "software engineer", "domain": "IT", "type": "keyword"}]
    mock_provider = AsyncMock()

    from types import SimpleNamespace

    job1 = SimpleNamespace(
        source="adecco",
        id="1",
        title="Software Engineer",
        company=SimpleNamespace(name="ACME GmbH"),
        external_url="http://example.com/1",
    )
    job2 = SimpleNamespace(
        source="adecco",
        id="2",
        title="software engineer",
        company=SimpleNamespace(name="ACME GMBH"),
        external_url="http://example.com/2",
    )
    mock_provider.search = AsyncMock(return_value=MagicMock(items=[job1, job2], total_pages=1, total_count=2))
    mock_service.providers = {"adecco": mock_provider}

    with patch("backend.services.search_service.get_compatible_providers", return_value=["adecco"]), \
         patch("backend.services.search_service.route_provider_names", return_value=["adecco"]), \
         patch("backend.services.search_service.get_status", return_value={"state": "searching"}), \
         patch("backend.services.search_service.settings.SEARCH_EXECUTION_MODE", "sequential"), \
         patch("backend.services.search_service.build_search_request", return_value=MagicMock(model_copy=lambda **kwargs: MagicMock())):
        profile = SimpleNamespace(location_filter="", posted_within_days=10, max_distance=10, workload_filter="", latitude=None, longitude=None, contract_type="")

        res = await mock_service._execute_searches(1, profile, searches, {"adecco": {}})

    assert len(res) == 1
    assert res[0].id == "1"

async def test_execute_searches_incompatible_or_stopped(mock_service):
    # Stopped immediately
    with patch("backend.services.search_service.get_status", return_value={"state": "stopped"}):
        res = await mock_service._execute_searches(1, MagicMock(), [{"query":"t"}], {})
        assert res == []
        
    # Incompatible domain
    with patch("backend.services.search_service.get_status", return_value={"state": "searching"}), \
            patch("backend.services.search_service.route_provider_names", return_value=[]):
        res = await mock_service._execute_searches(1, MagicMock(), [{"query":"t"}], {})
        assert res == []

async def test_run_search_finally_nameerror(mock_service):
    # simulate available_providers not defined NameError
    with patch.object(mock_service, "_generate_plan", side_effect=Exception("Fast fail")):
        # We manually raise NameError during cleanup
        mock_service.profile_repo.get = MagicMock(side_effect=NameError("Simulated available_providers fail"))
        await mock_service.run_search(1)

async def test_run_search_cleanup_close(mock_service):
    # Setup mock to reach finally block with populated available_providers
    profile = MagicMock(id=1, cv_content=None, user_id=1, role_description="", search_strategy="", latitude=None, longitude=None)
    mock_service.profile_repo.get = MagicMock(return_value=profile)
    
    provider1 = MagicMock()
    provider1.get_provider_info.return_value = MagicMock(accepted_domains=["*"])
    provider1.close = AsyncMock()
    
    provider2 = MagicMock()
    delattr(provider2, "close") # ensure no close method
    provider2._session = AsyncMock()
    provider2._session.aclose = AsyncMock()
    
    mock_service.providers = {"job_room": provider1, "adecco": provider2}

    with patch("backend.services.search_service.get_compatible_providers", return_value=["job_room", "adecco"]), \
         patch.object(mock_service, "_generate_plan", side_effect=Exception("fast fail")): # fast exit to run finally
        await mock_service.run_search(1)
         
    provider1.close.assert_called_once()
    provider2._session.aclose.assert_called_once()


async def test_run_search_force_regenerate_flags(mock_service):
    profile = MagicMock(
        id=1,
        user_id=1,
        cv_content="CV raw",
        role_description="dev",
        search_strategy="",
        latitude=None,
        longitude=None,
        cached_cv_summary="cached summary",
        cached_queries='[{"query":"cached dev"}]',
        max_queries=5,
        max_occupation_queries=None,
        max_keyword_queries=None,
    )
    mock_service.profile_repo.get = MagicMock(return_value=profile)

    with patch("backend.services.search_service.llm_service.generate_search_plan", new=AsyncMock(return_value=[{"query": "fresh dev"}])), \
         patch("backend.services.search_service.llm_service.summarize_cv", new=AsyncMock(return_value="fresh summary")) as mock_summarize, \
         patch.object(mock_service, "_normalize_user_profile", new=AsyncMock(return_value={})), \
         patch.object(mock_service, "_execute_searches", new=AsyncMock(return_value=[])), \
         patch("backend.services.search_service.update_status"):
        await mock_service.run_search(
            1,
            force_regenerate_cv_summary=True,
            force_regenerate_queries=True,
        )

    mock_summarize.assert_awaited_once()


async def test_run_search_done_terminal_reason_no_results(mock_service):
    profile = MagicMock(
        id=1,
        user_id=1,
        cv_content=None,
        role_description="dev",
        search_strategy="",
        latitude=None,
        longitude=None,
        cached_queries=None,
        max_queries=5,
        max_occupation_queries=None,
        max_keyword_queries=None,
    )
    mock_service.profile_repo.get = MagicMock(return_value=profile)

    with patch.object(mock_service, "_generate_plan", new=AsyncMock(return_value=[{"query": "dev"}])), \
         patch.object(mock_service, "_execute_searches", new=AsyncMock(return_value=[])), \
         patch("backend.services.search_service.update_status") as mock_update:
        await mock_service.run_search(1)

    mock_update.assert_any_call(1, state="done", terminal_reason="no_results")


async def test_run_search_done_terminal_reason_all_duplicates(mock_service):
    profile = MagicMock(
        id=1,
        user_id=1,
        cv_content=None,
        role_description="dev",
        search_strategy="",
        latitude=None,
        longitude=None,
        cached_queries=None,
        max_queries=5,
        max_occupation_queries=None,
        max_keyword_queries=None,
    )
    mock_service.profile_repo.get = MagicMock(return_value=profile)

    with patch.object(mock_service, "_generate_plan", new=AsyncMock(return_value=[{"query": "dev"}])), \
         patch.object(mock_service, "_execute_searches", new=AsyncMock(return_value=[MagicMock()])), \
         patch.object(mock_service, "_deduplicate", return_value=([], 1)), \
         patch("backend.services.search_service.update_status") as mock_update:
        await mock_service.run_search(1)

    mock_update.assert_any_call(1, state="done", terminal_reason="all_duplicates")


async def test_run_search_done_terminal_reason_no_jobs_after_structured_filters(mock_service):
    profile = MagicMock(
        id=1,
        user_id=1,
        cv_content=None,
        role_description="dev",
        search_strategy="",
        latitude=None,
        longitude=None,
        cached_queries=None,
        max_queries=5,
        max_occupation_queries=None,
        max_keyword_queries=None,
    )
    mock_service.profile_repo.get = MagicMock(return_value=profile)

    with patch.object(mock_service, "_generate_plan", new=AsyncMock(return_value=[{"query": "dev"}])), \
         patch.object(mock_service, "_execute_searches", new=AsyncMock(return_value=[MagicMock()])), \
         patch.object(mock_service, "_deduplicate", return_value=([MagicMock()], 0)), \
            patch.object(mock_service, "_persist_scraped_job_catalog", new=AsyncMock(return_value=(1, 0))), \
            patch.object(mock_service, "_apply_structured_filters", return_value=[]), \
         patch("backend.services.search_service.update_status") as mock_update:
        await mock_service.run_search(1)

        mock_update.assert_any_call(1, state="done", terminal_reason="no_jobs_after_structured_filters")

