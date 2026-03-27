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
    # Alias: generate_json_async_with_timeout routes through generate_json_async in tests
    provider.generate_json_async_with_timeout = provider.generate_json_async
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
async def test_generate_search_plan_single_shot_returns_all(mock_provider):
    """With single-shot generation, all queries come from one LLM call."""
    mock_provider.generate_json_async.return_value = {
        "searches": [
            {"domain": "it", "language": "en", "type": "occupation", "query": "Backend Engineer"},
            {"domain": "it", "language": "en", "type": "keyword", "query": "Python"},
            {"domain": "it", "language": "de", "type": "occupation", "query": "Softwareentwickler"},
            {"domain": "it", "language": "fr", "type": "keyword", "query": "Docker"},
        ]
    }

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()

        plan = await service.generate_search_plan(
            {"role_description": "Python developer", "search_strategy": "", "cv_content": "Python"},
            [],
            max_queries=4,
        )

        assert len(plan) == 4
        assert mock_provider.generate_json_async.call_count == 1

@pytest.mark.asyncio
async def test_generate_search_plan_partial_result_accepted(mock_provider):
    """When LLM returns fewer queries than requested, the partial result is accepted."""
    mock_provider.generate_json_async.return_value = {
        "searches": [
            {"domain": "it", "language": "en", "type": "occupation", "query": "Backend Engineer"},
        ]
    }

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()

        plan = await service.generate_search_plan(
            {"role_description": "Python developer", "search_strategy": "", "cv_content": "Python"},
            [],
            max_queries=4,
        )

        # Single call returns whatever the LLM provided, even if fewer than max_queries
        assert len(plan) == 1
        assert mock_provider.generate_json_async.call_count == 1

@pytest.mark.asyncio
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
            {"affinity_score": 85, "worth_applying": True},
            {"affinity_score": 10, "worth_applying": False}
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
        assert results[1]["affinity_score"] == 10
        
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
        assert results[0]["affinity_score"] == 0


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


# ─── Dual-signal normalize_user_profile tests ────────────────────────────────

@pytest.mark.asyncio
async def test_normalize_user_profile_dual_signal_output(mock_provider):
    """LLM returning dual-signal (candidate_profile + search_intent blocks) is flattened correctly."""
    dual_signal_response = {
        "candidate_profile": {
            "seniority": "mid",
            "domain": "it",
            "role_family": "Backend Engineer",
            "qualification_level": "bachelor",
            "experience_years": 4,
            "languages": [{"code": "en", "level": "C2"}],
            "skills": ["Python", "FastAPI", "PostgreSQL"],
        },
        "search_intent": {
            "target_domain": "logistics",
            "target_seniority": "junior",
            "target_role_family": "Warehouse Worker",
            "target_qualification_level": "none",
            "target_skills": ["forklift", "packing"],
            "open_to_unrelated": True,
            "intent_keywords": ["warehouse", "manual"],
        },
    }
    mock_provider.generate_json_async.return_value = dual_signal_response

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        result = await service.normalize_user_profile(
            cv_content="I am a backend Python developer with 4 years experience",
            role_description="Looking for warehouse work",
            search_strategy="Any manual labor accepted",
        )

    # Candidate profile fields
    assert result["domain"] == "it"
    assert result["seniority"] == "mid"
    assert "Python" in result["skills"]

    # Search intent fields
    assert result["intent_domain"] == "logistics"
    assert result["intent_seniority"] == "junior"
    assert result["open_to_unrelated"] is True
    assert "forklift" in result["intent_skills"]
    assert "warehouse" in result["intent_keywords"]


@pytest.mark.asyncio
async def test_normalize_user_profile_flat_response_backward_compat(mock_provider):
    """Old flat LLM response (no dual blocks) is still accepted via backward-compat path."""
    flat_response = {
        "seniority": "senior",
        "domain": "finance",
        "role_family": "Financial Analyst",
        "qualification_level": "master",
        "experience_years": 8,
        "languages": [],
        "skills": ["Excel", "SQL"],
        "confidence": 0.85,
    }
    mock_provider.generate_json_async.return_value = flat_response

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        result = await service.normalize_user_profile("Finance CV", "Senior analyst role", "")

    assert result["seniority"] == "senior"
    assert result["domain"] == "finance"
    assert result["experience_years"] == 8


@pytest.mark.asyncio
async def test_normalize_user_profile_open_to_unrelated_defaults_false(mock_provider):
    """When the LLM omits open_to_unrelated, default is False."""
    mock_provider.generate_json_async.return_value = {
        "seniority": "junior",
        "domain": "it",
        "role_family": "Dev",
        "qualification_level": "none",
        "experience_years": 1,
        "languages": [],
        "skills": [],
    }

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        result = await service.normalize_user_profile("Short CV", "Junior dev role", "")

    # Should default to False (not missing key causing KeyError)
    assert result.get("open_to_unrelated", False) is False


# ─── analyze_job_batch dimensional sub-score tests ───────────────────────────

@pytest.mark.asyncio
async def test_analyze_job_batch_returns_dimensional_subscores(mock_provider):
    """analyze_job_batch must propagate all 5 dimensional sub-scores from LLM output."""
    mock_provider.generate_json_async.return_value = {
        "results": [
            {
                "affinity_score": 78,
                "worth_applying": True,
                "affinity_analysis": "Good fit for skills and intent.",
                "skill_match_score": 80,
                "experience_match_score": 90,
                "intent_match_score": 95,
                "language_match_score": 100,
                "location_match_score": 60,
            }
        ]
    }

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        results = await service.analyze_job_batch(
            [{"title": "Warehouse Operator", "description": "Manual packing job"}],
            {"role_description": "Looking for warehouse work", "cv_summary": "Python dev"},
        )

    assert len(results) == 1
    r = results[0]
    assert r["affinity_score"] == 78
    assert r["skill_match_score"] == 80
    assert r["experience_match_score"] == 90
    assert r["intent_match_score"] == 95
    assert r["language_match_score"] == 100
    assert r["location_match_score"] == 60


@pytest.mark.asyncio
async def test_analyze_job_batch_subscores_default_to_none_on_fallback(mock_provider):
    """When LLM returns malformed response, fallback rows have None sub-scores (not KeyError)."""
    mock_provider.generate_json_async.return_value = {}  # malformed

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        results = await service.analyze_job_batch(
            [{"title": "Some job", "description": "desc"}],
            {"role_description": "Some role"},
        )

    assert len(results) == 1
    r = results[0]
    assert r["affinity_score"] == 0
    # sub-scores must exist as keys (with None value) to avoid KeyError downstream
    assert "skill_match_score" in r
    assert r["skill_match_score"] is None
    assert r["intent_match_score"] is None


# ─── normalize_job_batch role_type and industry_sector tests ─────────────────

@pytest.mark.asyncio
async def test_normalize_job_batch_returns_role_type_and_industry_sector(mock_provider):
    """normalize_job_batch must propagate role_type and industry_sector from LLM output."""
    mock_provider.generate_json_async.return_value = {
        "results": [
            {
                "title": "Warehouse Packer",
                "role_family": "Warehouse Worker",
                "domain": "logistics",
                "seniority": "junior",
                "employment_mode": "on-site",
                "contract_type": "temporary",
                "qualification_level": "none",
                "experience_min_years": 0,
                "experience_max_years": 2,
                "workload_min": 100,
                "workload_max": 100,
                "salary_max_chf": None,
                "required_languages": [],
                "required_skills": ["packing", "forklift"],
                "education_levels": [],
                "key_requirements": ["physical fitness"],
                "role_type": "manual",
                "industry_sector": "warehouse logistics",
                "confidence": 0.75,
            }
        ]
    }

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        results = await service.normalize_job_batch([
            {"title": "Warehouse Packer", "description": "Packing boxes in a warehouse"}
        ])

    assert len(results) == 1
    assert results[0]["role_type"] == "manual"
    assert results[0]["industry_sector"] == "warehouse logistics"


@pytest.mark.asyncio
async def test_normalize_job_batch_invalid_role_type_coerced_to_none(mock_provider):
    """Unknown role_type value must be coerced to None."""
    mock_provider.generate_json_async.return_value = {
        "results": [
            {
                "title": "Specialist",
                "role_family": "X",
                "domain": "general",
                "seniority": None,
                "employment_mode": "on-site",
                "contract_type": None,
                "qualification_level": None,
                "experience_min_years": None,
                "experience_max_years": None,
                "workload_min": None,
                "workload_max": None,
                "salary_max_chf": None,
                "required_languages": [],
                "required_skills": [],
                "education_levels": [],
                "key_requirements": [],
                "role_type": "alien",  # not in valid set
                "industry_sector": None,
                "confidence": 0.5,
            }
        ]
    }

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        results = await service.normalize_job_batch([
            {"title": "Specialist", "description": "unclear role"}
        ])

    assert results[0].get("role_type") is None
