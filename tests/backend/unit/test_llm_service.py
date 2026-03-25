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
async def test_generate_search_plan_retries_underfilled_batch(mock_provider):
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
        mock_settings.LLM_SUMMARY_PROVIDER = ""
        mock_settings.LLM_SUMMARY_API_KEY = ""
        mock_settings.LLM_SUMMARY_MODEL = ""
        mock_settings.SEARCH_PLAN_BATCH_SIZE = 2
        service = LLMService()

        plan = await service.generate_search_plan(
            {"role_description": "Python developer", "search_strategy": "", "cv_content": "Python"},
            [],
            max_queries=2,
        )

        assert len(plan) == 2
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
async def test_is_summary_step_configured_false_by_default():
    """Verify summary step is NOT configured when no LLM_SUMMARY_* vars are set."""
    with patch("backend.services.llm_service.settings") as mock_settings:
        mock_settings.LLM_SUMMARY_PROVIDER = ""
        mock_settings.LLM_SUMMARY_API_KEY = ""
        mock_settings.LLM_SUMMARY_MODEL = ""
        
        with patch("backend.services.llm_service.get_provider_for_step"):
            service = LLMService()
            assert service.is_summary_step_configured() is False

@pytest.mark.asyncio
async def test_is_summary_step_configured_true_when_api_key_set():
    """Verify summary step IS configured when LLM_SUMMARY_API_KEY is set."""
    with patch("backend.services.llm_service.settings") as mock_settings:
        mock_settings.LLM_SUMMARY_PROVIDER = ""
        mock_settings.LLM_SUMMARY_API_KEY = "sk-test-key"
        mock_settings.LLM_SUMMARY_MODEL = ""
        
        with patch("backend.services.llm_service.get_provider_for_step"):
            service = LLMService()
            assert service.is_summary_step_configured() is True

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
async def test_generate_search_plan_retries_on_wrong_counts(mock_provider):
    """Verify that if counts don't match, LLM is retried up to 3 times.
    After 3 failures, the last response is accepted as-is.
    """
    # Wrong counts on first 3 calls (3 occupations instead of 2), last call returns same wrong answer
    wrong_response = {
        "searches": [
            {"domain": "it", "type": "occupation", "query": "Dev 1"},
            {"domain": "it", "type": "occupation", "query": "Dev 2"},
            {"domain": "it", "type": "occupation", "query": "Dev 3"},  # one too many
        ]
    }
    mock_provider.generate_json_async.return_value = wrong_response
    
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        
        # Request max 2 occupations, 1 keyword — but LLM always returns 3 occupations, 0 keywords
        plan = await service.generate_search_plan(
            {"role_description": "Dev", "search_strategy": "", "cv_content": ""},
            [],
            max_occupation_queries=2,
            max_keyword_queries=1,
        )
        
        # After 3 retries (4 total calls including first), accepts whatever the LLM returned
        assert mock_provider.generate_json_async.call_count == 4  # initial + 3 retries
        assert len(plan) == 3  # Accepted the wrong response after max retries

@pytest.mark.asyncio
async def test_generate_search_plan_succeeds_on_second_attempt(mock_provider):
    """Verify that if 2nd call returns correct counts, only 2 LLM calls are made."""
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
        
        # Should stop after 2nd call which returned correct counts
        assert mock_provider.generate_json_async.call_count == 2
        assert len(plan) == 2
        types = {s["type"] for s in plan}
        assert "occupation" in types
        assert "keyword" in types


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
