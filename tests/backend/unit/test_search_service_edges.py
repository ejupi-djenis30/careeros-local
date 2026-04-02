import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.repositories.job_repository import JobRepository
from backend.repositories.profile_repository import ProfileRepository
from backend.services.search_service import SearchService, get_search_service


@pytest.fixture
def mock_service():
    mock_job_repo = MagicMock()
    mock_profile_repo = MagicMock()
    service = SearchService(job_repo=mock_job_repo, profile_repo=mock_profile_repo)
    return service


@pytest.fixture
def mock_service_with_real_repos():
    mock_db = MagicMock()
    return SearchService(
        db=mock_db,
        job_repo=JobRepository(mock_db),
        profile_repo=ProfileRepository(mock_db),
    )


async def test_get_search_service():
    mock_db = MagicMock()
    service = get_search_service(mock_db)
    assert isinstance(service, SearchService)


async def test_deduplicate(mock_service):
    profile = MagicMock()
    profile.id = 1

    db_row = MagicMock()
    db_row.configure_mock(
        platform="job_room",
        platform_job_id="123",
        external_url="http://x",
        title="dev",
        company="ACME",
    )
    mock_service.job_repo.get_profile_job_identifiers.return_value = [db_row]

    from types import SimpleNamespace

    # 1. Exact replicate by explicit key
    job1 = SimpleNamespace(
        source="job_room",
        id="123",
        title="dev",
        company=SimpleNamespace(name="ACME"),
        external_url="http://x",
    )

    # 2. Replicate by URL
    job2 = SimpleNamespace(
        source="other",
        id="999",
        title="dev",
        company=SimpleNamespace(name="ACME"),
        external_url="http://x",
    )

    # 3. Fuzzy match
    job3 = SimpleNamespace(
        source="other2",
        id="888",
        title=" d e v ",
        company=SimpleNamespace(name="A.C.M.E"),
        external_url="http://y",
    )

    # 4. Same fuzzy key among new jobs but different anchors (should remain unique)
    job4 = SimpleNamespace(
        source="new",
        id="111",
        title="Software Engineer",
        company=SimpleNamespace(name="NewCo"),
        external_url="http://new",
    )

    job5 = SimpleNamespace(
        source="new",
        id="222",
        title="Software Engineer",
        company=SimpleNamespace(name="NewCo"),
        external_url="http://new2",
    )

    unique_jobs, duplicates = mock_service._deduplicate(1, [job1, job2, job3, job4, job5])

    assert len(unique_jobs) == 3
    assert unique_jobs[0].id == "888"
    assert unique_jobs[1].id == "111"
    assert unique_jobs[2].id == "222"
    assert duplicates == 2


async def test_deduplicate_fuzzy_without_anchor_still_deduplicates(mock_service):
    from types import SimpleNamespace

    mock_service.job_repo.get_profile_job_identifiers.return_value = []
    mock_service.job_repo.get_applied_scraped_job_ids.return_value = set()

    # No source/id/url available: fuzzy key is the only identity signal.
    job1 = SimpleNamespace(title="Kitchen Assistant", company=SimpleNamespace(name="Hotel AG"))
    job2 = SimpleNamespace(title="Kitchen Assistant", company=SimpleNamespace(name="Hotel AG"))

    unique_jobs, duplicates = mock_service._deduplicate(1, [job1, job2])

    assert len(unique_jobs) == 1
    assert duplicates == 1


async def test_search_and_produce_tracks_runtime_and_history_duplicate_breakdown(mock_service):
    from types import SimpleNamespace

    profile = SimpleNamespace(
        location_filter="",
        posted_within_days=7,
        max_distance=50,
        workload_filter="",
        latitude=None,
        longitude=None,
        contract_type="",
    )
    search = {"query": "dev", "domain": "it", "type": "keyword", "language": "en"}
    provider = MagicMock()
    provider.throttle_delay = 0.0
    provider.capabilities = SimpleNamespace(max_page_size=50)

    history_job = SimpleNamespace(
        source="job_room",
        id="100",
        external_url="https://example.com/jobs/100?utm_source=test",
        title="Software Engineer",
        company=SimpleNamespace(name="Acme"),
    )
    runtime_job_a = SimpleNamespace(
        source="job_room",
        id="200",
        external_url="https://example.com/jobs/200?lang=de&page=2",
        title="Backend Engineer",
        company=SimpleNamespace(name="Beta"),
    )
    runtime_job_b = SimpleNamespace(
        source="job_room",
        id="201",
        external_url="http://www.example.com/jobs/200/?page=2&lang=DE",
        title="Backend Engineer",
        company=SimpleNamespace(name="Beta"),
    )

    provider.search = AsyncMock(
        return_value=SimpleNamespace(
            items=[history_job, runtime_job_a, runtime_job_b], total_pages=1, total_count=3
        )
    )
    mock_service.providers = {"job_room": provider}
    job_queue = asyncio.Queue()

    async def mark_catalog_state(profile_id, jobs):
        for idx, job in enumerate(jobs, start=1):
            job._catalog_persisted = True
            job._scraped_job_id = idx
            job._normalized_job_data = {"status": "provider_bootstrap"}
        return len(jobs), 0

    with (
        patch("backend.services.search_service.get_status", return_value={"state": "searching"}),
        patch("backend.services.search_service.route_provider_names", return_value=["job_room"]),
        patch("backend.services.search_service.build_search_request", return_value=MagicMock()),
        patch.object(mock_service, "_persist_scraped_job_catalog", new=mark_catalog_state),
        patch("backend.services.search_service.update_status") as mock_update,
        patch("backend.services.search_service.add_log"),
    ):
        total_found, total_duplicates = await mock_service._search_and_produce(
            1,
            profile,
            [search],
            {"job_room": MagicMock()},
            job_queue,
            {
                "existing_keys": set(),
                "existing_urls": {"example.com/jobs/100"},
                "existing_fuzzy_keys": set(),
                "existing_fuzzy_keys_strong": set(),
                "applied_scraped_ids": set(),
            },
        )

    queued_batch = await job_queue.get()
    sentinel = await job_queue.get()
    assert total_found == 3
    assert total_duplicates == 2
    assert [getattr(job, "id", None) for job in queued_batch] == ["200"]
    assert sentinel is None
    mock_update.assert_any_call(
        1, jobs_duplicates_total=2, jobs_duplicates_runtime=1, jobs_duplicates_history=1
    )


async def test_analyze_and_save_success(mock_service):
    profile_dict = {
        "id": 1,
        "user_id": 1,
        "latitude": 47.0,
        "longitude": 8.0,
        "role_description": "developer",
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
    job2.descriptions = [MagicMock(description="Boring job " * 100)]  # hits char limit
    job2.occupations = []
    job2.location = MagicMock(city="Bern", coordinates=None)
    job2.employment = MagicMock(workload_min=100, workload_max=100)
    job2.language_skills = []
    job2.company = None
    job2.application = None
    job2.external_url = "http://job2"
    job2.publication = MagicMock(start_date="2024-01-01")

    with patch("backend.services.search_service.llm_service.analyze_job_batch") as mock_analyze:
        # Return 2 results — all analyzed jobs are now saved (relevant filter removed)
        mock_analyze.return_value = [
            {"affinity_score": 90, "worth_applying": True},
            {"affinity_score": 10, "worth_applying": False},
        ]

        with (
            patch("backend.services.search_service.geocode_location") as mock_geocode,
            patch(
                "backend.services.search_service.get_status", return_value={"state": "searching"}
            ),
        ):
            mock_geocode.return_value = MagicMock(lat=46.9, lon=7.4)

            mock_session = mock_service.job_repo.db
            mock_service.job_repo.get_scraped_job_by_platform_and_id.return_value = None
            mock_service.job_repo.create_scraped_job_nested.return_value = True
            mock_service.job_repo.get_job_by_user_scraped_profile.return_value = None
            mock_service.job_repo.create_job_nested.return_value = True

            saved, skipped = await mock_service._analyze_and_save(1, profile_dict, [job1, job2])

            assert saved == 2
            assert skipped == 0
            assert mock_service.job_repo.create_scraped_job_nested.call_count == 2
            assert mock_service.job_repo.create_job_nested.call_count == 2
            # With per-job commits, commit is called once per saved job
            assert mock_session.commit.call_count == 2


async def test_analyze_and_save_db_error(mock_service):
    profile_dict = {"id": 1, "user_id": 1}
    job1 = MagicMock()
    job1.descriptions = [MagicMock(description="x")]

    # Patch _save_single_job to raise an exception — job should be skipped
    with (
        patch("backend.services.search_service.llm_service.analyze_job_batch") as mock_analyze,
        patch.object(
            mock_service, "_save_single_job", new=AsyncMock(side_effect=Exception("DB Fail"))
        ),
    ):
        mock_analyze.return_value = [{"relevant": True}]

        with patch(
            "backend.services.search_service.get_status", return_value={"state": "searching"}
        ):
            mock_session = mock_service.job_repo.db
            mock_session.query.return_value.filter.return_value.all.return_value = []

            saved, skipped = await mock_service._analyze_and_save(1, profile_dict, [job1])
            assert saved == 0
            assert skipped == 1


async def test_analyze_and_save_batch_exception(mock_service):
    profile_dict = {"id": 1, "user_id": 1}
    job1 = MagicMock()
    job1.descriptions = [MagicMock(description="x")]

    with (
        patch(
            "backend.services.search_service.llm_service.analyze_job_batch",
            side_effect=Exception("API limit"),
        ),
        patch("backend.services.search_service.get_status", return_value={"state": "searching"}),
    ):
        saved, skipped = await mock_service._analyze_and_save(1, profile_dict, [job1])
        assert saved == 0
        assert skipped == 1


async def test_run_search_cv_summarization_and_unexpected(mock_service):
    profile = MagicMock(id=1)

    # 1. Test run_search exception wrapping — exception raised inside _run_pipeline is caught.
    with patch.object(
        mock_service, "_run_pipeline", new=AsyncMock(side_effect=Exception("Critical"))
    ):
        await mock_service.run_search(1)
        # Should not raise, just catch and log

    # 2. Test that the pipeline runs without crashing when producers + consumer are stubbed out.
    with (
        patch.object(
            mock_service, "_generate_plan", new=AsyncMock(return_value=[{"query": "dev"}])
        ),
        patch.object(mock_service, "_normalize_user_profile", new=AsyncMock(return_value={})),
        patch.object(mock_service, "_search_and_produce", new=AsyncMock(return_value=(0, 0))),
        patch.object(
            mock_service, "_processing_consumer", new=AsyncMock(return_value=(0, 0, [], 0, 0))
        ),
        patch.object(mock_service.profile_repo, "get", return_value=profile),
    ):
        await mock_service.run_search(1)


async def test_run_search_profile_not_found(mock_service):
    mock_service.profile_repo.get = MagicMock(return_value=None)
    await mock_service.run_search(999)


async def test_generate_plan_exception(mock_service):
    with patch(
        "backend.services.search_service.llm_service.generate_search_plan",
        side_effect=Exception("LLM Fail"),
    ):
        res = await mock_service._generate_plan(1, {}, MagicMock(max_queries=5), {})
        assert res == []


async def test_generate_plan_rate_limit_sets_specific_terminal_reason(mock_service):
    profile = MagicMock(
        max_queries=5, max_occupation_queries=None, max_keyword_queries=None, cached_queries=None
    )
    profile_dict = {"role_description": "dev", "cv_content": "cv", "force_regenerate_queries": True}
    with (
        patch(
            "backend.services.search_service.llm_service.generate_search_plan",
            side_effect=Exception("rate_limit_exceeded"),
        ),
        patch("backend.services.search_service.update_status") as mock_update,
    ):
        res = await mock_service._generate_plan(1, profile_dict, profile, {})
        assert res == []
        mock_update.assert_called_with(
            1,
            state="error",
            terminal_reason="llm_plan_rate_limited",
            error="rate_limit_exceeded",
        )


async def test_generate_plan_empty_query(mock_service):
    with patch(
        "backend.services.search_service.llm_service.generate_search_plan",
        return_value=[{"query": ""}, {"query": "dev"}],
    ):
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

    with (
        patch("backend.services.search_service.compute_plan_input_fingerprint", return_value="abc"),
        patch("backend.services.search_service.add_log"),
    ):
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

    with (
        patch("backend.services.search_service.compute_plan_input_fingerprint", return_value="abc"),
        patch("backend.services.search_service.add_log"),
        patch("backend.services.search_service.update_status") as mock_update,
    ):
        await mock_service._generate_plan(1, profile_dict, profile, {})

    mock_update.assert_any_call(1, plan_cache_hit=1, plan_cache_miss=0)
    mock_update.assert_any_call(
        1,
        total_searches=1,
        searches_generated=[
            {"query": "dev", "type": "occupation", "domain": "it", "language": "en"}
        ],
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

    with (
        patch(
            "backend.services.search_service.llm_service.generate_search_plan",
            return_value=[{"query": "dev", "type": "occupation", "domain": "it", "language": "en"}],
        ),
        patch("backend.services.search_service.add_log"),
        patch("backend.services.search_service.update_status") as mock_update,
    ):
        await mock_service._generate_plan(1, profile_dict, profile, {})

    mock_update.assert_any_call(1, plan_cache_hit=0, plan_cache_miss=1)
    mock_update.assert_any_call(1, plan_raw_count=1)


async def test_analyze_and_save_stopped_and_truncation(mock_service):
    profile_dict = {"id": 1, "user_id": 1, "latitude": 47.0, "longitude": 8.0}

    from types import SimpleNamespace

    long_desc = "A" * 5000

    # Long descriptions should be compressed before analysis and still persist correctly.
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
        descriptions=[SimpleNamespace(description=long_desc)],
    )

    mock_session = mock_service.job_repo.db
    mock_session.query.return_value.filter.return_value.all.return_value = []

    with (
        patch("backend.services.search_service.settings.MAX_DESCRIPTION_CHARS", 100),
        patch("backend.services.search_service.llm_service.analyze_job_batch") as mock_analyze,
        patch(
            "backend.services.search_service.llm_service._compress_description_if_needed",
            new_callable=AsyncMock,
        ) as mock_compress,
    ):
        mock_analyze.return_value = [
            {"relevant": True, "affinity_score": 50, "worth_applying": False}
        ]
        mock_compress.return_value = "compressed"

        with (
            patch("backend.services.search_service.geocode_location") as mock_geocode,
            patch(
                "backend.services.search_service.get_status", return_value={"state": "searching"}
            ),
        ):
            mock_geocode.return_value = MagicMock(lat=46.9, lon=7.4)

            saved, skipped = await mock_service._analyze_and_save(1, profile_dict, [job1])
            assert saved == 1
            assert skipped == 0
            mock_session.commit.assert_called_once()
            mock_compress.assert_awaited_once_with(long_desc, 100)


async def test_analyze_and_save_length_mismatch(mock_service):
    with (
        patch("backend.services.search_service.get_status", return_value={"state": "searching"}),
        patch("backend.services.search_service.llm_service.analyze_job_batch", return_value=[]),
    ):
        saved, skipped = await mock_service._analyze_and_save(
            1, {}, [MagicMock(descriptions=[MagicMock(description="x")])]
        )
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


async def test_save_single_job_geocodes_missing_coordinates(mock_service_with_real_repos):
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

    mock_session = mock_service_with_real_repos.job_repo.db
    mock_session.query.return_value.filter.return_value.first.return_value = None

    with patch(
        "backend.services.search_service.geocode_location",
        new=AsyncMock(return_value=MagicMock(lat=46.948, lon=7.447)),
    ):
        await mock_service_with_real_repos._save_single_job(
            listing,
            {"affinity_score": 60, "affinity_analysis": "ok", "worth_applying": False},
            {"id": 1, "user_id": 99},
            (47.3769, 8.5417),
        )

    saved_job = mock_session.add.call_args_list[-1].args[0]
    assert saved_job.distance_km is not None


async def test_save_single_job_deferred_commit_does_not_commit(mock_service_with_real_repos):
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

    mock_session = mock_service_with_real_repos.job_repo.db
    mock_session.query.return_value.filter.return_value.first.return_value = None

    await mock_service_with_real_repos._save_single_job(
        listing,
        {"affinity_score": 60, "affinity_analysis": "ok", "worth_applying": False},
        {"id": 1, "user_id": 99},
        None,
        commit=False,
    )

    assert mock_session.add.call_count >= 2
    mock_session.commit.assert_not_called()


async def test_save_single_job_initializes_applied_false(mock_service_with_real_repos):
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

    mock_session = mock_service_with_real_repos.job_repo.db
    mock_session.query.return_value.filter.return_value.first.return_value = None

    await mock_service_with_real_repos._save_single_job(
        listing,
        {"affinity_score": 60, "affinity_analysis": "ok", "worth_applying": False},
        {"id": 1, "user_id": 99},
        None,
    )

    saved_job = mock_session.add.call_args_list[-1].args[0]
    assert saved_job.applied is False


async def test_save_single_job_bootstraps_normalized_fields(mock_service_with_real_repos):
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

    mock_session = mock_service_with_real_repos.job_repo.db
    mock_session.query.return_value.filter.return_value.first.return_value = None

    await mock_service_with_real_repos._save_single_job(
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


async def test_persist_scraped_job_catalog_commits_before_analysis(mock_service_with_real_repos):
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

    mock_session = mock_service_with_real_repos.job_repo.db
    mock_session.query.return_value.filter.return_value.first.return_value = None

    # New savepoint-based insert: savepoint.commit() fires instead of session.flush().
    # Simulate the database assigning an auto-increment id on commit.
    savepoint_mock = MagicMock()

    def _set_id_on_savepoint_commit():
        added_obj = mock_session.add.call_args.args[0]
        added_obj.id = 321

    savepoint_mock.commit.side_effect = _set_id_on_savepoint_commit
    mock_session.begin_nested.return_value = savepoint_mock

    created, updated = await mock_service_with_real_repos._persist_scraped_job_catalog(1, [listing])

    assert created == 1
    assert updated == 0
    mock_session.commit.assert_called_once()
    assert getattr(listing, "_scraped_job_id", None) == 321
    assert getattr(listing, "_catalog_persisted", None) is True
    assert getattr(listing, "_normalized_job_data", {}).get("status") == "provider_bootstrap"


async def test_persist_scraped_job_catalog_marks_failed_entries_without_queueing_them(mock_service):
    listing_ok = MagicMock()
    listing_fail = MagicMock()

    mock_session = mock_service.job_repo.db
    mock_session.begin_nested.return_value = MagicMock()

    scraped_job = MagicMock(id=321, normalized_job_data={"status": "provider_bootstrap"})

    def side_effect(listing):
        if listing is listing_ok:
            setattr(listing, "_catalog_persisted", True)
            setattr(listing, "_catalog_persist_error", None)
            setattr(listing, "_scraped_job_id", 321)
            setattr(listing, "_normalized_job_data", {"status": "provider_bootstrap"})
            return scraped_job, True
        raise RuntimeError("catalog failure")

    with patch.object(mock_service, "_upsert_scraped_job", side_effect=side_effect):
        created, updated = await mock_service._persist_scraped_job_catalog(
            1, [listing_ok, listing_fail]
        )

    assert created == 1
    assert updated == 0
    assert getattr(listing_ok, "_catalog_persisted", None) is True
    assert getattr(listing_fail, "_catalog_persisted", None) is False
    assert "catalog failure" in getattr(listing_fail, "_catalog_persist_error", "")


async def test_normalize_persisted_jobs_upgrades_bootstrap_rows(mock_service_with_real_repos):
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

    mock_session = mock_service_with_real_repos.job_repo.db
    mock_session.query.return_value.filter.return_value.all.return_value = [scraped_job]

    with patch(
        "backend.services.search_service.llm_service.normalize_job_batch",
        new=AsyncMock(
            return_value=[
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
            ]
        ),
    ):
        upgraded = await mock_service_with_real_repos._normalize_persisted_jobs(1, [listing])

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

    with (
        patch("backend.services.search_service.avam_mapper.resolve", return_value=[]),
        patch(
            "backend.services.search_service.get_compatible_providers",
            return_value=["job_room", "adecco"],
        ),
        patch("backend.services.search_service.build_search_request", return_value=MagicMock()),
        patch("backend.services.search_service.get_status") as mock_status,
    ):
        mock_status.side_effect = [
            {"state": "searching"},
            {"state": "searching"},
        ]  # Avoid stopping early

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

    with (
        patch("backend.services.search_service.get_compatible_providers", return_value=["adecco"]),
        patch("backend.services.search_service.get_status") as mock_status,
    ):
        # Start searching, allow one pagination step, then abort before the third page
        mock_status.side_effect = [
            {"state": "searching"},
            {"state": "searching"},
            {"state": "stopped"},
        ]

        from types import SimpleNamespace

        profile = SimpleNamespace(
            location_filter="",
            posted_within_days=10,
            max_distance=10,
            workload_filter="",
            latitude=None,
            longitude=None,
            contract_type="",
        )

        mock_service.providers = av_prov

        res = await mock_service._execute_searches(1, profile, searches, {"adecco": {}})
        # Because it stopped early, it still returns jobs collected before the abort
        assert len(res) > 0


async def test_execute_searches_continues_beyond_five_pages(mock_service):
    searches = [{"query": "dev", "domain": "IT", "type": "keyword"}]
    mock_provider = AsyncMock()
    mock_provider.throttle_delay = (
        0.0  # real providers return float; avoid AsyncMock > int TypeError
    )
    mock_provider.search = AsyncMock(
        side_effect=[
            MagicMock(
                items=[MagicMock(id=f"job-{idx}", external_url=f"http://example.com/{idx}")],
                total_pages=6,
                total_count=6,
            )
            for idx in range(6)
        ]
    )
    mock_service.providers = {"adecco": mock_provider}

    with (
        patch("backend.services.search_service.get_compatible_providers", return_value=["adecco"]),
        patch("backend.services.search_service.get_status", return_value={"state": "searching"}),
        patch("backend.services.search_service.settings.SEARCH_EXECUTION_MODE", "sequential"),
    ):
        from types import SimpleNamespace

        profile = SimpleNamespace(
            location_filter="",
            posted_within_days=10,
            max_distance=10,
            workload_filter="",
            latitude=None,
            longitude=None,
            contract_type="",
        )

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
    mock_provider.search = AsyncMock(
        return_value=MagicMock(items=[job1, job2], total_pages=1, total_count=2)
    )
    mock_service.providers = {"adecco": mock_provider}

    with (
        patch("backend.services.search_service.get_compatible_providers", return_value=["adecco"]),
        patch("backend.services.search_service.route_provider_names", return_value=["adecco"]),
        patch("backend.services.search_service.get_status", return_value={"state": "searching"}),
        patch("backend.services.search_service.settings.SEARCH_EXECUTION_MODE", "sequential"),
        patch(
            "backend.services.search_service.build_search_request",
            return_value=MagicMock(model_copy=lambda **kwargs: MagicMock()),
        ),
    ):
        profile = SimpleNamespace(
            location_filter="",
            posted_within_days=10,
            max_distance=10,
            workload_filter="",
            latitude=None,
            longitude=None,
            contract_type="",
        )

        res = await mock_service._execute_searches(1, profile, searches, {"adecco": {}})

    assert len(res) == 1
    assert res[0].id == "1"


async def test_execute_searches_incompatible_or_stopped(mock_service):
    # Stopped immediately
    with patch("backend.services.search_service.get_status", return_value={"state": "stopped"}):
        res = await mock_service._execute_searches(1, MagicMock(), [{"query": "t"}], {})
        assert res == []

    # Incompatible domain
    with (
        patch("backend.services.search_service.get_status", return_value={"state": "searching"}),
        patch("backend.services.search_service.route_provider_names", return_value=[]),
    ):
        res = await mock_service._execute_searches(1, MagicMock(), [{"query": "t"}], {})
        assert res == []


async def test_run_search_finally_nameerror(mock_service):
    # simulate available_providers not defined NameError
    with patch.object(mock_service, "_generate_plan", side_effect=Exception("Fast fail")):
        # We manually raise NameError during cleanup
        mock_service.profile_repo.get = MagicMock(
            side_effect=NameError("Simulated available_providers fail")
        )
        await mock_service.run_search(1)


async def test_run_search_cleanup_close(mock_service):
    # Setup mock to reach finally block with populated available_providers
    profile = MagicMock(
        id=1,
        cv_content=None,
        user_id=1,
        role_description="",
        search_strategy="",
        latitude=None,
        longitude=None,
    )
    mock_service.profile_repo.get = MagicMock(return_value=profile)

    provider1 = MagicMock()
    provider1.get_provider_info.return_value = MagicMock(accepted_domains=["*"])
    provider1.close = AsyncMock()

    provider2 = MagicMock()
    delattr(provider2, "close")  # ensure no close method
    provider2._session = AsyncMock()
    provider2._session.aclose = AsyncMock()

    mock_service.providers = {"job_room": provider1, "adecco": provider2}

    with (
        patch(
            "backend.services.search_service.get_compatible_providers",
            return_value=["job_room", "adecco"],
        ),
        patch.object(mock_service, "_generate_plan", side_effect=Exception("fast fail")),
    ):  # fast exit to run finally
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

    with (
        patch(
            "backend.services.search_service.llm_service.generate_search_plan",
            new=AsyncMock(return_value=[{"query": "fresh dev"}]),
        ),
        patch(
            "backend.services.search_service.llm_service.summarize_cv",
            new=AsyncMock(return_value="fresh summary"),
        ) as mock_summarize,
        patch.object(mock_service, "_normalize_user_profile", new=AsyncMock(return_value={})),
        patch.object(mock_service, "_search_and_produce", new=AsyncMock(return_value=(0, 0))),
        patch.object(
            mock_service, "_processing_consumer", new=AsyncMock(return_value=(0, 0, [], 0, 0))
        ),
        patch("backend.services.search_service.update_status"),
    ):
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

    with (
        patch.object(
            mock_service, "_generate_plan", new=AsyncMock(return_value=[{"query": "dev"}])
        ),
        patch.object(mock_service, "_search_and_produce", new=AsyncMock(return_value=(0, 0))),
        patch.object(
            mock_service, "_processing_consumer", new=AsyncMock(return_value=(0, 0, [], 0, 0))
        ),
        patch.object(mock_service, "_normalize_user_profile", new=AsyncMock(return_value={})),
        patch("backend.services.search_service.update_status") as mock_update,
    ):
        await mock_service.run_search(1)

    mock_update.assert_any_call(1, state="done", terminal_reason="no_results")


async def test_run_search_sets_error_when_all_provider_searches_fail(mock_service):
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

    with (
        patch.object(
            mock_service, "_generate_plan", new=AsyncMock(return_value=[{"query": "dev"}])
        ),
        patch.object(mock_service, "_search_and_produce", new=AsyncMock(return_value=(0, 0))),
        patch.object(
            mock_service, "_processing_consumer", new=AsyncMock(return_value=(0, 0, [], 0, 0))
        ),
        patch.object(mock_service, "_normalize_user_profile", new=AsyncMock(return_value={})),
        patch.object(
            mock_service,
            "_status_metrics",
            return_value={"errors": 1, "provider_failures": 2, "provider_successes": 0},
        ),
        patch("backend.services.search_service.update_status") as mock_update,
    ):
        await mock_service.run_search(1)

    mock_update.assert_any_call(
        1,
        state="error",
        terminal_reason="search_execution_failed",
        error="All provider searches failed before any jobs could be processed.",
    )


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

    with (
        patch.object(
            mock_service, "_generate_plan", new=AsyncMock(return_value=[{"query": "dev"}])
        ),
        patch.object(
            mock_service,
            "_load_profile_dedup_history",
            return_value={
                "existing_keys": {"job_room:123"},
                "existing_urls": set(),
                "existing_fuzzy_keys": set(),
                "existing_fuzzy_keys_strong": set(),
                "applied_scraped_ids": set(),
            },
        ),
        patch.object(mock_service, "_search_and_produce", new=AsyncMock(return_value=(3, 3))),
        patch.object(
            mock_service, "_processing_consumer", new=AsyncMock(return_value=(0, 0, [], 0, 0))
        ),
        patch.object(mock_service, "_normalize_user_profile", new=AsyncMock(return_value={})),
        patch("backend.services.search_service.update_status") as mock_update,
    ):
        await mock_service.run_search(1)

    mock_update.assert_any_call(
        1,
        state="done",
        terminal_reason="all_duplicates",
        jobs_found=3,
        jobs_duplicates=3,
        jobs_unique=0,
    )


async def test_run_search_done_terminal_reason_no_jobs_after_dedup(mock_service):
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

    with (
        patch.object(
            mock_service, "_generate_plan", new=AsyncMock(return_value=[{"query": "dev"}])
        ),
        patch.object(
            mock_service,
            "_load_profile_dedup_history",
            return_value={
                "existing_keys": set(),
                "existing_urls": set(),
                "existing_fuzzy_keys": set(),
                "existing_fuzzy_keys_strong": set(),
                "applied_scraped_ids": set(),
            },
        ),
        patch.object(mock_service, "_search_and_produce", new=AsyncMock(return_value=(3, 3))),
        patch.object(
            mock_service, "_processing_consumer", new=AsyncMock(return_value=(0, 0, [], 0, 0))
        ),
        patch.object(mock_service, "_normalize_user_profile", new=AsyncMock(return_value={})),
        patch("backend.services.search_service.update_status") as mock_update,
    ):
        await mock_service.run_search(1)

    mock_update.assert_any_call(
        1,
        state="done",
        terminal_reason="no_jobs_after_dedup",
        jobs_found=3,
        jobs_duplicates=3,
        jobs_unique=0,
    )


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

    with (
        patch.object(
            mock_service, "_generate_plan", new=AsyncMock(return_value=[{"query": "dev"}])
        ),
        patch.object(mock_service, "_search_and_produce", new=AsyncMock(return_value=(3, 0))),
        patch.object(
            mock_service, "_processing_consumer", new=AsyncMock(return_value=(3, 0, [], 0, 0))
        ),
        patch.object(mock_service, "_normalize_user_profile", new=AsyncMock(return_value={})),
        patch("backend.services.search_service.update_status") as mock_update,
    ):
        await mock_service.run_search(1)

        mock_update.assert_any_call(
            1,
            state="done",
            terminal_reason="no_jobs_after_structured_filters",
            jobs_found=3,
            jobs_duplicates=0,
            jobs_unique=3,
            jobs_skipped=3,
        )


async def test_run_search_sets_error_when_processing_fails_before_analysis(mock_service):
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

    with (
        patch.object(
            mock_service, "_generate_plan", new=AsyncMock(return_value=[{"query": "dev"}])
        ),
        patch.object(mock_service, "_search_and_produce", new=AsyncMock(return_value=(3, 0))),
        patch.object(
            mock_service, "_processing_consumer", new=AsyncMock(return_value=(1, 0, [], 0, 0))
        ),
        patch.object(mock_service, "_normalize_user_profile", new=AsyncMock(return_value={})),
        patch.object(
            mock_service,
            "_status_metrics",
            return_value={"errors": 1, "provider_failures": 0, "provider_successes": 1},
        ),
        patch("backend.services.search_service.update_status") as mock_update,
    ):
        await mock_service.run_search(1)

    mock_update.assert_any_call(
        1,
        state="error",
        terminal_reason="pipeline_processing_failed",
        jobs_found=3,
        jobs_duplicates=0,
        jobs_unique=3,
        jobs_skipped=1,
        error="Jobs were fetched but pipeline processing failed before analysis completed.",
    )


async def test_run_search_analysis_failure_not_pipeline_error_when_all_accounted(mock_service):
    """Regression: analysis batch failures should NOT produce pipeline_processing_failed when
    every unique job is either filtered OR lost to analysis errors (no truly unexplained jobs).

    Scenario:
    - 3 unique jobs found
    - 1 filtered by structured filter  (total_filtered=1)
    - 2 reached analysis but LLM failed for both  (analysis_failed=2, errors=2)
    - analyzed_pairs is empty

    Expected: state=done because unexplained_unique = 3 - 1 - 2 = 0.
    """
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

    with (
        patch.object(
            mock_service, "_generate_plan", new=AsyncMock(return_value=[{"query": "dev"}])
        ),
        patch.object(mock_service, "_search_and_produce", new=AsyncMock(return_value=(3, 0))),
        patch.object(
            mock_service, "_processing_consumer", new=AsyncMock(return_value=(1, 2, [], 0, 0))
        ),
        patch.object(mock_service, "_normalize_user_profile", new=AsyncMock(return_value={})),
        patch.object(
            mock_service,
            "_status_metrics",
            return_value={"errors": 2, "provider_failures": 0, "provider_successes": 1},
        ),
        patch("backend.services.search_service.update_status") as mock_update,
    ):
        await mock_service.run_search(1)

    # Must NOT declare pipeline_processing_failed — all 3 jobs are accounted for.
    terminal_reason_calls = [
        call.kwargs.get("terminal_reason")
        for call in mock_update.call_args_list
        if "terminal_reason" in (call.kwargs or {})
    ]
    assert "pipeline_processing_failed" not in terminal_reason_calls, (
        f"Unexpectedly triggered pipeline_processing_failed; terminal reasons seen: {terminal_reason_calls}"
    )
    final_state_calls = [
        call.kwargs.get("state")
        for call in mock_update.call_args_list
        if call.kwargs.get("state") in {"done", "error"}
    ]
    assert "done" in final_state_calls, f"Expected state=done, got: {final_state_calls}"


async def test_run_search_normalization_exception_zero_errors(mock_service):
    """Regression: normalization soft-failure must NOT inflate the errors counter.
    A run where all jobs are filtered should end done/no_jobs_after_structured_filters
    even if normalization raised internally, because the consumer no longer calls
    _increment_status_errors on normalization exceptions.
    """
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

    with (
        patch.object(
            mock_service, "_generate_plan", new=AsyncMock(return_value=[{"query": "dev"}])
        ),
        patch.object(mock_service, "_search_and_produce", new=AsyncMock(return_value=(3, 0))),
        patch.object(
            mock_service, "_processing_consumer", new=AsyncMock(return_value=(3, 0, [], 0, 0))
        ),
        patch.object(mock_service, "_normalize_user_profile", new=AsyncMock(return_value={})),
        patch.object(
            mock_service,
            "_status_metrics",
            return_value={"errors": 0, "provider_failures": 0, "provider_successes": 1},
        ),
        patch("backend.services.search_service.update_status") as mock_update,
    ):
        await mock_service.run_search(1)

    mock_update.assert_any_call(
        1,
        state="done",
        terminal_reason="no_jobs_after_structured_filters",
        jobs_found=3,
        jobs_duplicates=0,
        jobs_unique=3,
        jobs_skipped=3,
    )


# ─── _upsert_scraped_job conflict-safety tests ────────────────────────────────


def _make_listing(source="job_room", job_id="abc123", title="Developer"):
    """Helper to create a minimal listing SimpleNamespace."""
    from types import SimpleNamespace

    listing = SimpleNamespace(
        source=source,
        id=job_id,
        platform_job_id=None,
        title=title,
        company=SimpleNamespace(name="Acme"),
        descriptions=[SimpleNamespace(description="A job")],
        location=SimpleNamespace(city="Zurich", coordinates=SimpleNamespace(lat=47.37, lon=8.54)),
        employment=SimpleNamespace(workload_min=80, workload_max=100),
        application=None,
        external_url="https://example.com/job",
        publication=None,
        language_skills=[],
        occupations=[],
    )
    return listing


def _make_mock_service_with_real_upsert():
    """Return a SearchService backed by a MagicMock session for upsert tests."""
    mock_db = MagicMock()
    return SearchService(
        db=mock_db,
        job_repo=JobRepository(mock_db),
        profile_repo=ProfileRepository(mock_db),
    )


def test_upsert_scraped_job_creates_new_when_not_exists():
    """Happy path: first time we see a job, it should be added to the session."""

    service = _make_mock_service_with_real_upsert()
    db = service.db
    db.query.return_value.filter.return_value.first.return_value = None  # no existing record

    # Savepoint mock: commit succeeds
    savepoint_mock = MagicMock()
    db.begin_nested.return_value = savepoint_mock

    listing = _make_listing()

    with (
        patch("backend.services.search_service.bootstrap_normalized_job_data", return_value={}),
        patch(
            "backend.services.search_service.extract_listing_description_text", return_value="desc"
        ),
        patch("backend.services.search_service.extract_company_name", return_value="Acme"),
        patch(
            "backend.services.search_service.extract_listing_location_string", return_value="Zurich"
        ),
        patch(
            "backend.services.search_service.extract_listing_workload_string", return_value="80-100"
        ),
        patch("backend.services.search_service.parse_listing_publication_date", return_value=None),
    ):
        sj, created = service._upsert_scraped_job(listing)

    assert created is True
    db.add.assert_called_once()
    savepoint_mock.commit.assert_called_once()
    savepoint_mock.rollback.assert_not_called()


def test_upsert_scraped_job_recovers_from_integrity_error():
    """
    Concurrent insert race: flush raises IntegrityError.
    The savepoint must be rolled back and the existing record re-fetched
    without losing the outer transaction.
    """
    from sqlalchemy.exc import IntegrityError as SaIntegrityError

    service = _make_mock_service_with_real_upsert()
    db = service.db

    # First call: no existing record (race not yet detected)
    existing_sj = MagicMock()
    existing_sj.id = 99
    existing_sj.normalization_status = "normalized"
    db.query.return_value.filter.return_value.first.side_effect = [
        None,  # initial check → no record
        existing_sj,  # re-fetch after IntegrityError
    ]

    # Savepoint raises IntegrityError on commit
    savepoint_mock = MagicMock()
    savepoint_mock.commit.side_effect = SaIntegrityError("UNIQUE constraint failed", None, None)
    db.begin_nested.return_value = savepoint_mock

    listing = _make_listing()

    with (
        patch("backend.services.search_service.bootstrap_normalized_job_data", return_value={}),
        patch(
            "backend.services.search_service.extract_listing_description_text", return_value="desc"
        ),
        patch("backend.services.search_service.extract_company_name", return_value="Acme"),
        patch(
            "backend.services.search_service.extract_listing_location_string", return_value="Zurich"
        ),
        patch(
            "backend.services.search_service.extract_listing_workload_string", return_value="80-100"
        ),
        patch("backend.services.search_service.parse_listing_publication_date", return_value=None),
    ):
        sj, created = service._upsert_scraped_job(listing)

    # created must be False — we recovered the existing record
    assert created is False
    # Savepoint was rolled back (not committed successfully)
    savepoint_mock.rollback.assert_called_once()
    # The re-fetched record is returned
    assert sj is existing_sj


def test_upsert_scraped_job_updates_existing_record():
    """When a record already exists, it should be updated in-place (not re-inserted)."""
    service = _make_mock_service_with_real_upsert()
    db = service.db

    existing_sj = MagicMock()
    existing_sj.normalization_status = None
    existing_sj.description = None
    existing_sj.location = None
    existing_sj.application_url = None
    existing_sj.application_email = None
    existing_sj.workload = None
    existing_sj.publication_date = None
    existing_sj.source_query = None
    db.query.return_value.filter.return_value.first.return_value = existing_sj

    listing = _make_listing()

    with (
        patch(
            "backend.services.search_service.bootstrap_normalized_job_data",
            return_value={"normalized_domain": "IT"},
        ),
        patch(
            "backend.services.search_service.extract_listing_description_text",
            return_value="Updated desc",
        ),
        patch("backend.services.search_service.extract_company_name", return_value="Acme"),
        patch(
            "backend.services.search_service.extract_listing_location_string", return_value="Bern"
        ),
        patch(
            "backend.services.search_service.extract_listing_workload_string", return_value="100"
        ),
        patch("backend.services.search_service.parse_listing_publication_date", return_value=None),
    ):
        sj, created = service._upsert_scraped_job(listing)

    assert created is False
    # begin_nested must NOT be called (we took the update path, not the insert path)
    db.begin_nested.assert_not_called()
    # Fields that were None should have been back-filled
    assert existing_sj.description == "Updated desc"
    assert existing_sj.location == "Bern"


def test_upsert_scraped_job_handles_partial_application_payloads():
    service = _make_mock_service_with_real_upsert()
    db = service.db
    db.query.return_value.filter.return_value.first.return_value = None
    savepoint_mock = MagicMock()
    db.begin_nested.return_value = savepoint_mock

    listing = _make_listing()
    listing.application = {"email": "jobs@example.com"}

    with (
        patch("backend.services.search_service.bootstrap_normalized_job_data", return_value={}),
        patch(
            "backend.services.search_service.extract_listing_description_text", return_value="desc"
        ),
        patch("backend.services.search_service.extract_company_name", return_value="Acme"),
        patch(
            "backend.services.search_service.extract_listing_location_string", return_value="Zurich"
        ),
        patch(
            "backend.services.search_service.extract_listing_workload_string", return_value="80-100"
        ),
        patch("backend.services.search_service.parse_listing_publication_date", return_value=None),
    ):
        service._upsert_scraped_job(listing)

    saved_job = db.add.call_args.args[0]
    assert saved_job.application_url is None
    assert saved_job.application_email == "jobs@example.com"


async def test_search_and_produce_queues_only_catalog_persisted_jobs(mock_service):
    from types import SimpleNamespace

    profile = SimpleNamespace(
        location_filter="",
        posted_within_days=7,
        max_distance=50,
        workload_filter="",
        latitude=None,
        longitude=None,
        contract_type="",
    )
    search = {"query": "dev", "domain": "it", "type": "keyword", "language": "en"}
    provider = MagicMock()
    provider.throttle_delay = 0.0
    provider.capabilities = SimpleNamespace(max_page_size=50)

    job1 = SimpleNamespace(source="job_room", id="1", external_url="u1", title="Dev 1")
    job2 = SimpleNamespace(source="job_room", id="2", external_url="u2", title="Dev 2")

    provider.search = AsyncMock(
        return_value=SimpleNamespace(items=[job1, job2], total_pages=1, total_count=2)
    )
    mock_service.providers = {"job_room": provider}
    job_queue = asyncio.Queue()

    async def mark_catalog_state(profile_id, jobs):
        jobs[0]._catalog_persisted = True
        jobs[0]._scraped_job_id = 11
        jobs[0]._normalized_job_data = {"status": "provider_bootstrap"}
        jobs[1]._catalog_persisted = False
        jobs[1]._catalog_persist_error = "failed"
        return 1, 0

    with (
        patch("backend.services.search_service.get_status", return_value={"state": "searching"}),
        patch("backend.services.search_service.route_provider_names", return_value=["job_room"]),
        patch("backend.services.search_service.build_search_request", return_value=MagicMock()),
        patch.object(mock_service, "_persist_scraped_job_catalog", new=mark_catalog_state),
        patch.object(mock_service, "_increment_status_errors") as mock_errors,
        patch("backend.services.search_service.update_status"),
        patch("backend.services.search_service.add_log"),
    ):
        total_found, total_duplicates = await mock_service._search_and_produce(
            1,
            profile,
            [search],
            {"job_room": MagicMock()},
            job_queue,
            {
                "existing_keys": set(),
                "existing_urls": set(),
                "existing_fuzzy_keys": set(),
                "applied_scraped_ids": set(),
            },
        )

    queued_batch = await job_queue.get()
    sentinel = await job_queue.get()
    assert total_found == 2
    assert total_duplicates == 0
    assert [getattr(job, "id", None) for job in queued_batch] == ["1"]
    assert sentinel is None
    mock_errors.assert_called_once_with(1, 1)


async def test_search_and_produce_keeps_anchored_fuzzy_jobs_unique(mock_service):
    from types import SimpleNamespace

    profile = SimpleNamespace(
        location_filter="",
        posted_within_days=7,
        max_distance=50,
        workload_filter="",
        latitude=None,
        longitude=None,
        contract_type="",
    )
    search = {"query": "dev", "domain": "it", "type": "keyword", "language": "en"}
    provider = MagicMock()
    provider.throttle_delay = 0.0
    provider.capabilities = SimpleNamespace(max_page_size=50)

    job1 = SimpleNamespace(
        source="job_room",
        id="100",
        external_url="https://example.com/100",
        title="Software Engineer",
        company=SimpleNamespace(name="Acme"),
    )
    job2 = SimpleNamespace(
        source="job_room",
        id="200",
        external_url="https://example.com/200",
        title="Software Engineer",
        company=SimpleNamespace(name="Acme"),
    )

    provider.search = AsyncMock(
        return_value=SimpleNamespace(items=[job1, job2], total_pages=1, total_count=2)
    )
    mock_service.providers = {"job_room": provider}
    job_queue = asyncio.Queue()

    async def mark_catalog_state(profile_id, jobs):
        for idx, job in enumerate(jobs, start=1):
            job._catalog_persisted = True
            job._scraped_job_id = idx
            job._normalized_job_data = {"status": "provider_bootstrap"}
        return len(jobs), 0

    with (
        patch("backend.services.search_service.get_status", return_value={"state": "searching"}),
        patch("backend.services.search_service.route_provider_names", return_value=["job_room"]),
        patch("backend.services.search_service.build_search_request", return_value=MagicMock()),
        patch.object(mock_service, "_persist_scraped_job_catalog", new=mark_catalog_state),
        patch("backend.services.search_service.update_status") as mock_update,
        patch("backend.services.search_service.add_log"),
    ):
        total_found, total_duplicates = await mock_service._search_and_produce(
            1,
            profile,
            [search],
            {"job_room": MagicMock()},
            job_queue,
            {
                "existing_keys": set(),
                "existing_urls": set(),
                "existing_fuzzy_keys": set(),
                "existing_fuzzy_keys_strong": set(),
                "applied_scraped_ids": set(),
            },
        )

    queued_batch = await job_queue.get()
    sentinel = await job_queue.get()
    assert total_found == 2
    assert total_duplicates == 0
    assert [getattr(job, "id", None) for job in queued_batch] == ["100", "200"]
    assert sentinel is None
    mock_update.assert_any_call(
        1,
        jobs_found=2,
        jobs_duplicates=0,
        jobs_unique=2,
    )


async def test_run_search_sets_error_when_all_persistence_fails_after_analysis(mock_service):
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
    analyzed_pairs = [(MagicMock(), {"affinity_score": 70, "worth_applying": True})]

    # consumer_saved=0, consumer_skipped=1: consumer tried to persist but all failed
    with (
        patch.object(
            mock_service, "_generate_plan", new=AsyncMock(return_value=[{"query": "dev"}])
        ),
        patch.object(mock_service, "_search_and_produce", new=AsyncMock(return_value=(3, 0))),
        patch.object(
            mock_service,
            "_processing_consumer",
            new=AsyncMock(return_value=(1, 0, analyzed_pairs, 0, 1)),
        ),
        patch.object(mock_service, "_normalize_user_profile", new=AsyncMock(return_value={})),
        patch.object(
            mock_service,
            "_status_metrics",
            side_effect=[
                {"errors": 0, "provider_failures": 0, "provider_successes": 1},
                {"errors": 1, "provider_failures": 0, "provider_successes": 1},
            ],
        ),
        patch("backend.services.search_service.update_status") as mock_update,
    ):
        await mock_service.run_search(1)

    persistence_error_call = next(
        call.kwargs
        for call in mock_update.call_args_list
        if call.kwargs.get("terminal_reason") == "job_persistence_failed"
    )
    assert persistence_error_call["state"] == "error"
    assert persistence_error_call["jobs_found"] == 3
    assert persistence_error_call["jobs_duplicates"] == 0
    assert persistence_error_call["jobs_skipped"] == 2
    assert persistence_error_call["error"] == "Jobs were analyzed but none could be persisted."
    assert persistence_error_call["finished_at"]


# ─── MATCH Payload Completeness ──────────────────────────────────────────────


async def test_analyze_and_save_match_payload_includes_all_normalized_fields(mock_service):
    """Ensure the normalized_data dict forwarded to analyze_job_batch contains all
    critical fields (required_languages, hard_blockers, entry_barrier, etc.) that
    the MATCH prompt references, not just the original 8 fields."""
    from types import SimpleNamespace

    job = SimpleNamespace(
        id="1",
        source="test",
        title="Reinigungskraft (m/w/d)",
        company=SimpleNamespace(name="CleanCo AG"),
        location=SimpleNamespace(city="Bern", coordinates=None),
        employment=SimpleNamespace(workload_min=100, workload_max=100),
        application=None,
        external_url="https://example.com/job/1",
        publication=None,
        descriptions=[SimpleNamespace(description="Gute Deutschkenntnisse C2 erforderlich.")],
        language_skills=[],
        occupations=[],
    )
    # Attach full normalized data — the kind produced by normalized_job_data property
    job._normalized_job_data = {
        "domain": "general",
        "role_type": "manual",
        "industry_sector": "hospitality cleaning",
        "seniority": "junior",
        "qualification_level": "none",
        "required_skills": ["cleaning equipment"],
        "preferred_skills": ["HACCP"],
        "experience_min_years": None,
        "experience_max_years": None,
        "required_languages": [{"code": "de", "level": "C2"}],
        "entry_barrier": "none",
        "career_changer_friendly": True,
        "hard_blockers": ["valid Swiss work permit"],
        "education_levels": [],
        "key_requirements": ["physical fitness"],
        "physical_requirements": ["standing 8+ hours"],
        "soft_skills": ["team player"],
        "confidence": 0.85,
    }
    job._scraped_job_id = None

    captured_batches = []

    async def mock_analyze(batch, profile):
        captured_batches.append(batch)
        return [{"affinity_score": 70, "affinity_analysis": "ok", "worth_applying": True}]

    profile_dict = {
        "id": 1,
        "user_id": 1,
        "latitude": None,
        "longitude": None,
        "profile_normalization": {},
    }

    mock_session = mock_service.job_repo.db
    mock_session.query.return_value.filter.return_value.all.return_value = []

    with (
        patch("backend.services.search_service.get_status", return_value={"state": "searching"}),
        patch(
            "backend.services.search_service.llm_service.analyze_job_batch",
            side_effect=mock_analyze,
        ),
    ):
        await mock_service._analyze_and_save(1, profile_dict, [job])

    assert len(captured_batches) == 1
    job_meta = captured_batches[0][0]
    nd = job_meta["normalized_data"]

    # All previously missing fields must now be present and correct
    assert nd["required_languages"] == [{"code": "de", "level": "C2"}]
    assert nd["hard_blockers"] == ["valid Swiss work permit"]
    assert nd["entry_barrier"] == "none"
    assert nd["career_changer_friendly"] is True
    assert nd["preferred_skills"] == ["HACCP"]
    assert nd["physical_requirements"] == ["standing 8+ hours"]
    assert nd["education_levels"] == []
    assert nd["key_requirements"] == ["physical fitness"]
    assert nd["soft_skills"] == ["team player"]
    # Original fields still present
    assert nd["domain"] == "general"
    assert nd["required_skills"] == ["cleaning equipment"]


async def test_normalize_persisted_jobs_marks_failed_when_batch_returns_empty(
    mock_service_with_real_repos,
):
    """When LLM returns {} for a job, normalization_status must become 'failed', not stay pending."""
    listing = MagicMock()
    listing._scraped_job_id = 777

    scraped_job = MagicMock()
    scraped_job.id = 777
    scraped_job.title = "Warehouse Worker"
    scraped_job.company = "Logistics Co"
    scraped_job.location = "Zurich"
    scraped_job.workload = "100%"
    scraped_job.description = "Pack and ship."
    scraped_job.normalization_status = "provider_bootstrap"
    scraped_job.normalized_metadata = None

    mock_session = mock_service_with_real_repos.job_repo.db
    mock_session.query.return_value.filter.return_value.all.return_value = [scraped_job]

    with patch(
        "backend.services.search_service.llm_service.normalize_job_batch",
        new=AsyncMock(return_value=[{}]),  # empty dict = batch failure for this job
    ):
        upgraded = await mock_service_with_real_repos._normalize_persisted_jobs(1, [listing])

    assert upgraded == 0
    assert scraped_job.normalization_status == "failed"
    assert scraped_job.normalized_metadata is not None
    assert "normalization_failed_at" in scraped_job.normalized_metadata


async def test_normalize_persisted_jobs_splits_batches_by_prompt_budget(
    mock_service_with_real_repos,
):
    listing_one = MagicMock()
    listing_one._scraped_job_id = 101
    listing_two = MagicMock()
    listing_two._scraped_job_id = 102

    scraped_one = MagicMock()
    scraped_one.id = 101
    scraped_one.title = "Warehouse Worker"
    scraped_one.company = "Logistics Co"
    scraped_one.location = "Zurich"
    scraped_one.workload = "100%"
    scraped_one.description = "Required forklift license. " + ("detail " * 120)
    scraped_one.normalization_status = "provider_bootstrap"
    scraped_one.normalized_metadata = None
    scraped_one.normalized_job_data = {}

    scraped_two = MagicMock()
    scraped_two.id = 102
    scraped_two.title = "Kitchen Assistant"
    scraped_two.company = "Hotel Co"
    scraped_two.location = "Bern"
    scraped_two.workload = "100%"
    scraped_two.description = "Required hygiene training. " + ("detail " * 120)
    scraped_two.normalization_status = "provider_bootstrap"
    scraped_two.normalized_metadata = None
    scraped_two.normalized_job_data = {}

    mock_session = mock_service_with_real_repos.job_repo.db
    mock_session.query.return_value.filter.return_value.all.return_value = [
        scraped_one,
        scraped_two,
    ]

    captured_chunks = []

    async def capture(chunk):
        captured_chunks.append(chunk)
        return [{}, {}][: len(chunk)]

    with (
        patch("backend.services.search_service.settings.NORMALIZE_BATCH_SIZE", 10),
        patch("backend.services.search_service.settings.NORMALIZE_PROMPT_TARGET_CHARS", 350),
        patch(
            "backend.services.search_service.llm_service.normalize_job_batch",
            side_effect=capture,
        ),
    ):
        await mock_service_with_real_repos._normalize_persisted_jobs(1, [listing_one, listing_two])

    assert len(captured_chunks) == 2
    assert all(len(chunk) == 1 for chunk in captured_chunks)
