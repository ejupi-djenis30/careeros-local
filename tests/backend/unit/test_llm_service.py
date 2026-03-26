import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from tenacity import RetryError
from backend.services.llm_service import LLMService

@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.generate_json_async = AsyncMock()
    provider.generate_text_async = AsyncMock()
    provider.model_id = "groq/test-model"
    return provider

@pytest.fixture
def llm_service(mock_provider):
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        return LLMService()

@pytest.mark.asyncio
async def test_generate_search_plan_success(mock_provider):
    mock_provider.generate_json_async.return_value = {
        "searches": [
            {"domain": "it", "language": "en", "type": "occupation", "query": "Software Engineer"}
        ]
    }

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        profile = {"role_description": "Dev", "search_strategy": "Be aggressive", "cv_content": "Experienced"}
        providers = [{"name": "swissdevjobs", "description": "IT jobs"}]

        plan = await service.generate_search_plan(profile, providers, max_queries=1)

        assert len(plan) == 1
        assert plan[0]["query"] == "Software Engineer"
        mock_provider.generate_json_async.assert_called_once()

@pytest.mark.asyncio
async def test_generate_search_plan_error(mock_provider):
    mock_provider.generate_json_async.side_effect = Exception("LLM Error")

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        with pytest.raises(RetryError):
            await service._call_generate_search_plan({}, [])


@pytest.mark.asyncio
async def test_each_method_calls_correct_step(mock_provider):
    """Verify each method dispatches to the correct pipeline step."""
    mock_provider.generate_json_async.return_value = {"searches": []}

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider) as mock_factory:
        service = LLMService()

        await service.generate_search_plan({"role_description": "X", "search_strategy": "", "cv_content": ""}, [])
        mock_factory.assert_called_with("plan")

        mock_factory.reset_mock()
        mock_provider.generate_json_async.return_value = {"results": [{"relevant": True, "affinity_score": 50, "affinity_analysis": "", "worth_applying": False}]}
        await service.analyze_job_batch([{}], {})
        mock_factory.assert_called_with("match")

@pytest.mark.asyncio
async def test_generate_search_plan_respects_max_queries(mock_provider):
    """Verify the service truncates results when max_queries is given."""
    mock_provider.generate_json_async.return_value = {
        "searches": [
            {"domain": "it", "language": "en", "type": "occupation", "query": f"Job {i}"}
            for i in range(10)
        ]
    }

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        plan = await service.generate_search_plan({}, [], max_queries=3)
        assert len(plan) == 3

@pytest.mark.asyncio
async def test_generate_search_plan_batches_to_reach_target(mock_provider):
    mock_provider.generate_json_async.side_effect = [
        {
            "searches": [
                {"domain": "it", "language": "en", "type": "occupation", "query": "Backend Engineer"},
                {"domain": "it", "language": "en", "type": "keyword", "query": "Python"},
            ]
        },
        {
            "searches": [
                {"domain": "it", "language": "de", "type": "occupation", "query": "Softwareentwickler"},
                {"domain": "it", "language": "fr", "type": "keyword", "query": "Docker"},
            ]
        },
    ]

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider), \
         patch("backend.services.llm_service.settings") as mock_settings:
        mock_settings.LLM_SUMMARY_PROVIDER = ""
        mock_settings.LLM_SUMMARY_API_KEY = ""
        mock_settings.LLM_SUMMARY_MODEL = ""
        mock_settings.SEARCH_PLAN_BATCH_SIZE = 2
        service = LLMService()

        plan = await service.generate_search_plan(
            {"role_description": "Python developer", "search_strategy": "", "cv_content": "Python"},
            [],
            max_queries=4,
        )

        assert len(plan) == 4
        assert mock_provider.generate_json_async.call_count == 2

@pytest.mark.asyncio
async def test_generate_search_plan_stops_on_underfilled_no_retry(mock_provider):
    """Verify the system stops when a batch is underfilled and cannot be completed without retry."""
    mock_provider.generate_json_async.side_effect = [
        {
            "searches": [
                {"domain": "it", "language": "en", "type": "occupation", "query": "Backend Engineer"},
            ]
        },
        {
            "searches": [
                {"domain": "it", "language": "en", "type": "occupation", "query": "Backend Engineer"},
                {"domain": "it", "language": "en", "type": "keyword", "query": "Python"},
            ]
        },
    ]

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider), \
         patch("backend.services.llm_service.settings") as mock_settings:
        mock_settings.SEARCH_PLAN_BATCH_SIZE = 2
        service = LLMService()

        plan = await service.generate_search_plan(
            {"role_description": "Python developer", "search_strategy": "", "cv_content": "Python"},
            [],
            max_queries=2,
        )

        # Batch 1 gives 1 unique query. Batch 2 (asking for 1) gives a duplicate.
        # System stalls and terminates early instead of retrying to get the missing 1 query.
        assert len(plan) == 1
        assert mock_provider.generate_json_async.call_count == 2

@pytest.mark.asyncio
async def test_check_relevance_batch_is_permissive(mock_provider):
    """Verify the relevance prompt is permissive and includes strategy/description."""
    mock_provider.generate_json_async.return_value = {"results": [True]}
    
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        jobs = [{"title": "Dev", "company": "Anticorp", "description_snippet": "Software engineering role"}]
        strategy = "Focus on Python"
        
        await service.check_relevance_batch(jobs, "Developer", search_strategy=strategy)
        
        call_args = mock_provider.generate_json_async.call_args[0]
        sys_prompt = call_args[0]
        user_prompt = call_args[1]
        
        assert "permissive" in sys_prompt.lower()
        assert "strict" not in sys_prompt.lower()
        assert strategy in user_prompt
        assert "Software engineering role" in user_prompt
        assert "FILTERING RULES" in user_prompt

@pytest.mark.asyncio
async def test_check_relevance_batch_uses_conservative_padding_by_default(mock_provider):
    mock_provider.generate_json_async.return_value = {"results": [True]}

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider), \
         patch("backend.services.llm_service.settings.SEARCH_RELEVANCE_FALLBACK_MODE", "conservative"):
        service = LLMService()
        jobs = [
            {"title": "Dev", "company": "A", "description_snippet": "one"},
            {"title": "Ops", "company": "B", "description_snippet": "two"},
        ]

        results = await service.check_relevance_batch(jobs, "Developer")

        assert results == [True, False]

@pytest.mark.asyncio
async def test_summarize_cv_success(mock_provider):
    mock_provider.generate_text_async.return_value = "- Experience: 5 years\n- Skills: Python"
    
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        summary = await service.summarize_cv("Lorem ipsum CV content...")
        
        assert summary == "- Experience: 5 years\n- Skills: Python"
        
        call_args = mock_provider.generate_text_async.call_args[0]
        sys_prompt = call_args[0]
        user_prompt = call_args[1]
        
        assert "HR analyst" in sys_prompt
        assert "Lorem ipsum" in user_prompt
        assert "Education" in user_prompt

@pytest.mark.asyncio
async def test_analyze_job_batch_success(mock_provider):
    mock_provider.generate_json_async.return_value = {
        "results": [
            {"relevant": True, "affinity_score": 85, "worth_applying": True},
            {"relevant": False, "affinity_score": 10, "worth_applying": False}
        ]
    }
    
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        jobs = [
            {"title": "Dev", "company": "A", "location": "Remote", "description": "Good job"},
            {"title": "Chef", "company": "B", "location": "Paris", "description": "Cooking"}
        ]
        profile = {
            "role_description": "Developer",
            "search_strategy": "Only remote",
            "cv_summary": "5 years dev"
        }
        
        results = await service.analyze_job_batch(jobs, profile)
        
        assert len(results) == 2
        assert results[0]["affinity_score"] == 85
        assert results[1]["relevant"] is False
        
        call_args = mock_provider.generate_json_async.call_args[0]
        sys_prompt = call_args[0]
        user_prompt = call_args[1]
        
        assert "career coach AI" in sys_prompt
        assert "Only remote" in user_prompt
        assert "Good job" in user_prompt
        assert "Cooking" in user_prompt

@pytest.mark.asyncio
async def test_analyze_job_batch_fallback_empty_dict(mock_provider):
    mock_provider.generate_json_async.return_value = {} # Malformed response
    
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        results = await service.analyze_job_batch([{"title": "T"}], {"role_description": "R"})
        assert len(results) == 1
        assert results[0]["relevant"] is False
        assert results[0]["affinity_score"] == 0

# ─── Feature 1: Job Summary Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summarize_job_batch_success(mock_provider):
    """Verify summarize_job_batch returns one summary per job in order."""
    mock_provider.generate_json_async.return_value = {
        "summaries": [
            "Software engineer role requiring Python and 3+ years experience.",
            "Chef role requiring culinary skills and food safety knowledge."
        ]
    }
    
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        jobs = [
            {"title": "Backend Dev", "company": "TechCo", "description": "We need Python engineers..."},
            {"title": "Chef", "company": "Restaurant", "description": "Experienced chef wanted..."},
        ]
        
        summaries = await service.summarize_job_batch(jobs)
        
        assert len(summaries) == 2
        assert "Python" in summaries[0]
        assert "culinary" in summaries[1]
        
        # Verify the "summary" step provider was used
        mock_provider.generate_json_async.assert_called_once()
        call_args = mock_provider.generate_json_async.call_args[0]
        user_prompt = call_args[1]
        assert "Backend Dev" in user_prompt
        assert "Chef" in user_prompt

@pytest.mark.asyncio
async def test_summarize_job_batch_pads_on_short_response(mock_provider):
    """Verify padding with empty strings when LLM returns fewer summaries than jobs."""
    mock_provider.generate_json_async.return_value = {
        "summaries": ["Only one summary"]
    }
    
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        jobs = [
            {"title": "Job 1", "company": "A", "description": "..."},
            {"title": "Job 2", "company": "B", "description": "..."},
            {"title": "Job 3", "company": "C", "description": "..."},
        ]
        
        summaries = await service.summarize_job_batch(jobs)
        
        assert len(summaries) == 3
        assert summaries[0] == "Only one summary"
        assert summaries[1] == ""
        assert summaries[2] == ""


@pytest.mark.asyncio
async def test_normalize_job_batch_success(mock_provider):
    mock_provider.generate_json_async.return_value = {
        "results": [
            {
                "title": "Senior Backend Engineer",
                "role_family": "Backend Engineer",
                "domain": "tech",
                "seniority": "senior",
                "employment_mode": "hybrid",
                "contract_type": "permanent",
                "qualification_level": "bachelor",
                "experience_min_years": 5,
                "experience_max_years": 8,
                "workload_min": 80,
                "workload_max": 100,
                "salary_max_chf": 140000,
                "required_languages": [{"code": "DE", "level": "b2"}],
                "required_skills": ["Python", "Python", "FastAPI"],
                "education_levels": ["Bachelor"],
                "key_requirements": ["Swiss permit"],
                "confidence": 0.82,
            }
        ]
    }

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        results = await service.normalize_job_batch([
            {"title": "Senior Backend Engineer", "description": "Python FastAPI role"}
        ])

    assert len(results) == 1
    assert results[0]["domain"] == "it"
    assert results[0]["required_languages"] == [{"code": "de", "level": "B2"}]
    assert results[0]["required_skills"] == ["Python", "FastAPI"]


@pytest.mark.asyncio
async def test_normalize_job_batch_pads_invalid_rows(mock_provider):
    mock_provider.generate_json_async.return_value = {"results": [{}]}

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        results = await service.normalize_job_batch([
            {"title": "A", "description": "x"},
            {"title": "B", "description": "y"},
        ])

    assert len(results) == 2
    assert results[0]["domain"] == "general"
    assert results[1]["domain"] == "general"

# ─── Feature 4: Query Count Retry Enforcement Tests ───────────────────────────

@pytest.mark.asyncio
async def test_generate_search_plan_with_strict_occupation_keyword_split(mock_provider):
    """Verify the prompt contains strict count instructions when occupation/keyword counts are set."""
    mock_provider.generate_json_async.return_value = {
        "searches": [
            {"domain": "it", "type": "occupation", "query": "Software Engineer"},
            {"domain": "it", "type": "occupation", "query": "Backend Developer"},
            {"domain": "it", "type": "keyword", "query": "Python"},
        ]
    }
    
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        plan = await service.generate_search_plan(
            {"role_description": "Dev", "search_strategy": "", "cv_content": ""},
            [],
            max_occupation_queries=2,
            max_keyword_queries=1,
        )
        
        assert len(plan) == 3
        
        call_args = mock_provider.generate_json_async.call_args[0]
        user_prompt = call_args[1]
        assert "EXACTLY 2" in user_prompt
        assert "EXACTLY 1" in user_prompt

@pytest.mark.asyncio
async def test_generate_search_plan_accepts_wrong_counts_without_retry(mock_provider):
    """Verify that the system now accepts the first result even if counts are wrong."""
    wrong_response = {
        "searches": [
            {"domain": "it", "type": "occupation", "query": "Dev 1"},
            {"domain": "it", "type": "occupation", "query": "Dev 2"},
            {"domain": "it", "type": "occupation", "query": "Dev 3"},
        ]
    }
    mock_provider.generate_json_async.return_value = wrong_response
    
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        
        plan = await service.generate_search_plan(
            {"role_description": "Dev", "search_strategy": "", "cv_content": ""},
            [],
            max_occupation_queries=2,
            max_keyword_queries=1,
        )
        
        assert mock_provider.generate_json_async.call_count == 1
        assert len(plan) == 3

@pytest.mark.asyncio
async def test_generate_search_plan_accepts_first_attempt(mock_provider):
    """Verify that the system accepts the first result even if counts are wrong, skipping retries."""
    wrong_call = {"searches": [
        {"domain": "it", "type": "occupation", "query": "Dev 1"},
        {"domain": "it", "type": "occupation", "query": "Dev 2"},
    ]}
    correct_call = {"searches": [
        {"domain": "it", "type": "occupation", "query": "Dev 1"},
        {"domain": "it", "type": "keyword", "query": "Python"},
    ]}
    mock_provider.generate_json_async.side_effect = [wrong_call, correct_call]
    
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        
        plan = await service.generate_search_plan(
            {"role_description": "Dev", "search_strategy": "", "cv_content": ""},
            [],
            max_occupation_queries=1,
            max_keyword_queries=1,
        )
        
        # Should stop after 1st call even if it technically didn't meet the split ratio
        # (Though in this specific case, total_target is 2, and it got 2 results, so it stops)
        assert mock_provider.generate_json_async.call_count == 1
        assert len(plan) == 2


@pytest.mark.asyncio
async def test_call_generate_search_plan_accepts_queries_alias(mock_provider):
    """Accept non-canonical but common payload keys like 'queries'."""
    mock_provider.generate_json_async.return_value = {
        "queries": [
            {"domain": "it", "type": "occupation", "query": "Software Engineer"},
        ]
    }

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        plan = await service._call_generate_search_plan(
            {"role_description": "Dev", "search_strategy": "", "cv_content": ""},
            [],
            max_queries=1,
        )
        assert len(plan) == 1
        assert plan[0]["query"] == "Software Engineer"


@pytest.mark.asyncio
async def test_call_generate_search_plan_prefers_canonical_searches_over_legacy_alias(mock_provider):
    """Use canonical 'searches' when both canonical and legacy keys are present."""
    mock_provider.generate_json_async.return_value = {
        "searches": [
            {"domain": "it", "type": "occupation", "query": "Backend Engineer"},
        ],
        "queries": [
            {"domain": "it", "type": "occupation", "query": "Ignored Alias Result"},
        ],
    }

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        plan = await service._call_generate_search_plan(
            {"role_description": "Dev", "search_strategy": "", "cv_content": ""},
            [],
            max_queries=1,
        )

        assert len(plan) == 1
        assert plan[0]["query"] == "Backend Engineer"


@pytest.mark.asyncio
async def test_call_generate_search_plan_falls_back_when_canonical_searches_invalid(mock_provider):
    """Fallback to legacy alias when canonical key exists but has invalid shape."""
    mock_provider.generate_json_async.return_value = {
        "searches": "invalid",
        "queries": [
            {"domain": "it", "type": "keyword", "query": "Python"},
        ],
    }

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        plan = await service._call_generate_search_plan(
            {"role_description": "Dev", "search_strategy": "", "cv_content": ""},
            [],
            max_queries=1,
        )

        assert len(plan) == 1
        assert plan[0]["query"] == "Python"


@pytest.mark.asyncio
async def test_call_generate_search_plan_raises_on_invalid_payload(mock_provider):
    """Reject payloads that do not contain a list under searches/queries/results."""
    mock_provider.generate_json_async.return_value = {"status": "ok"}

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        with pytest.raises(RetryError):
            await service._call_generate_search_plan(
                {"role_description": "Dev", "search_strategy": "", "cv_content": ""},
                [],
                max_queries=1,
            )


@pytest.mark.asyncio
async def test_generate_search_plan_returns_partial_if_later_batch_fails(mock_provider):
    """If a later batch fails (rate limit/error), return already collected queries instead of raising."""
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider), \
         patch("backend.services.llm_service.settings") as mock_settings:
        mock_settings.LLM_SUMMARY_PROVIDER = ""
        mock_settings.LLM_SUMMARY_API_KEY = ""
        mock_settings.LLM_SUMMARY_MODEL = ""
        mock_settings.SEARCH_PLAN_BATCH_SIZE = 2

        service = LLMService()
        service._call_generate_search_plan = AsyncMock(side_effect=[
            [
                {"domain": "it", "language": "en", "type": "occupation", "query": "Backend Engineer"},
                {"domain": "it", "language": "en", "type": "keyword", "query": "Python"},
            ],
            Exception("rate_limit_exceeded"),
        ])

        plan = await service.generate_search_plan(
            {"role_description": "Python developer", "search_strategy": "", "cv_content": "Python"},
            [],
            max_queries=4,
        )

        assert len(plan) == 2
        assert {item["query"] for item in plan} == {"Backend Engineer", "Python"}


@pytest.mark.asyncio
async def test_generate_search_plan_uses_best_partial_batch_on_error(mock_provider):
    """If current batch has a best candidate set then a later retry fails, keep the best batch instead of raising."""
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider), \
         patch("backend.services.llm_service.settings") as mock_settings:
        mock_settings.LLM_SUMMARY_PROVIDER = ""
        mock_settings.LLM_SUMMARY_API_KEY = ""
        mock_settings.LLM_SUMMARY_MODEL = ""
        mock_settings.SEARCH_PLAN_BATCH_SIZE = 2

        service = LLMService()
        service._call_generate_search_plan = AsyncMock(side_effect=[
            [
                {"domain": "it", "language": "en", "type": "occupation", "query": "Backend Engineer"},
                {"domain": "it", "language": "en", "type": "keyword", "query": "Python"},
            ],
            Exception("rate_limit_exceeded"),
        ])

        plan = await service.generate_search_plan(
            {"role_description": "Python developer", "search_strategy": "", "cv_content": "Python"},
            [],
            max_queries=2,
            max_occupation_queries=2,
            max_keyword_queries=0,
        )

        assert len(plan) == 2


def test_normalize_searches_infers_type_and_normalizes_fields(llm_service):
    searches = [
        {"query": "  React  Developer 100% ", "type": "", "domain": "IT / Software", "language": "English"},
        {"query": "React Developer", "type": "occupation", "domain": "it-software", "language": "en"},
    ]

    normalized = llm_service._normalize_searches(searches)

    assert len(normalized) == 1
    assert normalized[0]["query"] == "React Developer"
    assert normalized[0]["type"] == "occupation"
    assert normalized[0]["domain"] == "it-software"
    assert normalized[0]["language"] == "en"


def test_normalize_searches_loose_dedup_drops_cosmetic_variants(llm_service):
    searches = [
        {"query": "React Developer", "type": "occupation", "domain": "it", "language": "en"},
        {"query": "Developer React", "type": "occupation", "domain": "it", "language": "en"},
    ]

    with patch("backend.services.llm_service.settings.SEARCH_PLAN_ENABLE_LOOSE_DEDUP", True):
        normalized = llm_service._normalize_searches(searches)

    assert len(normalized) == 1
    assert normalized[0]["query"] == "React Developer"


def test_normalize_searches_loose_dedup_can_be_disabled(llm_service):
    searches = [
        {"query": "React Developer", "type": "occupation", "domain": "it", "language": "en"},
        {"query": "Developer React", "type": "occupation", "domain": "it", "language": "en"},
    ]

    with patch("backend.services.llm_service.settings.SEARCH_PLAN_ENABLE_LOOSE_DEDUP", False):
        normalized = llm_service._normalize_searches(searches)

    assert len(normalized) == 2


@pytest.mark.asyncio
async def test_generate_search_plan_batch_stops_after_stall(mock_provider):
    """Verify the system terminates early if a batch produces no new unique queries, instead of rescuing."""
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider), \
         patch("backend.services.llm_service.settings") as mock_settings:
        mock_settings.SEARCH_PLAN_BATCH_SIZE = 2
        mock_settings.SEARCH_PLAN_ENABLE_LOOSE_DEDUP = True

        service = LLMService()

        # Returns empty list (all filtered out)
        service._call_generate_search_plan = AsyncMock(return_value=[])

        plan = await service.generate_search_plan(
            {"role_description": "Dev", "search_strategy": "", "cv_content": ""},
            [],
            max_queries=2,
        )

        assert len(plan) == 0
        service._call_generate_search_plan.assert_called_once()


# ─── Coverage Report Tests ─────────────────────────────────────────────────────

def test_build_coverage_report_returns_empty_for_no_queries(llm_service):
    """First batch has no collected queries — report should be empty string."""
    report = llm_service._build_coverage_report([])
    assert report == ""


def test_build_coverage_report_basic_structure(llm_service):
    """Verify the report includes distribution stats and the full structured query list."""
    collected = [
        {"type": "occupation", "domain": "it", "language": "en", "query": "Software Engineer"},
        {"type": "keyword", "domain": "it", "language": "de", "query": "Python"},
        {"type": "occupation", "domain": "finance", "language": "fr", "query": "Analyste financier"},
    ]
    report = llm_service._build_coverage_report(collected)

    assert "COVERAGE SO FAR (3 queries" in report
    assert "occupation=2, keyword=1" in report
    assert "it=2" in report
    assert "finance=1" in report
    assert "Software Engineer" in report
    assert "Python" in report
    assert "Analyste financier" in report
    assert "do NOT repeat" in report
    assert "Focus your new queries" in report


def test_build_coverage_report_remaining_needed(llm_service):
    """Remaining occupation/keyword counts should appear in the report when provided."""
    collected = [
        {"type": "occupation", "domain": "it", "language": "en", "query": "Backend Engineer"},
    ]
    report = llm_service._build_coverage_report(collected, remaining_occupations=5, remaining_keywords=3)

    assert "STILL NEEDED: 5 more occupation" in report
    assert "3 more keyword" in report


def test_build_coverage_report_identifies_missing_languages(llm_service):
    """Report should flag core languages (en/de/fr/it) that have no queries yet."""
    collected = [
        {"type": "occupation", "domain": "it", "language": "en", "query": "Backend Engineer"},
        {"type": "keyword", "domain": "it", "language": "de", "query": "Python"},
    ]
    report = llm_service._build_coverage_report(collected)

    # Both fr and it are missing from a 2-query set
    assert "Missing languages" in report
    assert "fr" in report
    assert "it" in report


def test_build_coverage_report_caps_list_at_100_entries(llm_service):
    """Verify the structured list is capped at 100 entries for token budget control."""
    collected = [
        {"type": "occupation", "domain": "it", "language": "en", "query": f"Engineer {i}"}
        for i in range(120)
    ]
    report = llm_service._build_coverage_report(collected)

    assert "120 queries already generated" in report
    assert "20 earlier queries omitted" in report
    assert "Engineer 119" in report  # last entry is present
    assert "Engineer 0" not in report  # first 20 entries omitted


def test_build_coverage_report_structured_row_format(llm_service):
    """Each query in the list should appear with type, domain, language, and text."""
    collected = [
        {"type": "occupation", "domain": "finance", "language": "fr", "query": "Analyste financier"},
    ]
    report = llm_service._build_coverage_report(collected)

    assert "[occupation] [finance] [fr] Analyste financier" in report
