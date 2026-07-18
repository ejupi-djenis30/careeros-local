from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.ai.evaluation import load_dataset
from backend.ai.orchestrator import AIValidationError
from backend.core.config import settings
from backend.inference.ports import StructuredInferenceResult
from backend.providers.circuit_breaker import CircuitState, circuit_registry
from backend.services.llm_service import LLMService


def _golden(task_id: str) -> dict:
    case = next(item for item in load_dataset().cases if item.task_id == task_id)
    return case.expected_output


def _result(payload: dict) -> StructuredInferenceResult:
    return StructuredInferenceResult(
        payload=payload,
        model_id="ollama-local/test-model",
        runtime="test",
        duration_ms=2,
    )


@pytest.fixture(autouse=True)
def reset_circuit_registry():
    circuit_registry._breakers.clear()
    yield
    circuit_registry._breakers.clear()


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.model_id = "ollama-local/test-model"
    provider.max_tokens = 16_384
    provider.context_window = 8_192
    provider.generate_structured_async = AsyncMock()
    provider.generate_text_async = AsyncMock()
    provider.generate_text_async_with_timeout = provider.generate_text_async
    return provider


@pytest.fixture
def llm_service(mock_provider):
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        return LLMService()


def test_get_provider_propagates_local_runtime_configuration_errors():
    with patch(
        "backend.services.llm_service.get_provider_for_step",
        side_effect=ValueError("invalid local endpoint"),
    ):
        with pytest.raises(ValueError, match="invalid local endpoint"):
            LLMService()._get_provider("plan")


async def test_structured_call_sends_versioned_deterministic_schema(mock_provider):
    mock_provider.generate_structured_async.return_value = _result(_golden("search_plan"))

    async def passthrough(operation):
        return await operation()

    breaker = MagicMock(state=CircuitState.CLOSED)
    breaker.call = AsyncMock(side_effect=passthrough)
    with patch("backend.services.llm_service.circuit_registry.get", return_value=breaker):
        result = await LLMService()._call_provider_json(
            mock_provider, "plan", "system", "user"
        )

    assert result["searches"]
    request = mock_provider.generate_structured_async.await_args.args[0]
    assert request.task_id == "search_plan"
    assert request.temperature == 0
    assert request.seed == 0
    assert request.json_schema["additionalProperties"] is False


async def test_structured_call_fails_closed_after_one_repair(mock_provider):
    mock_provider.generate_structured_async.return_value = _result({"queries": []})

    with pytest.raises(AIValidationError):
        await LLMService()._call_provider_json(mock_provider, "plan", "system", "user")

    assert mock_provider.generate_structured_async.await_count == 2


async def test_generate_search_plan_is_strict_deduplicated_and_capped(mock_provider):
    payload = _golden("search_plan")
    payload["searches"].append(
        {"query": "Senior Python Backend Engineer", "domain": "it", "type": "occupation", "language": "en"}
    )
    mock_provider.generate_structured_async.return_value = _result(payload)
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        plan = await LLMService().generate_search_plan(
            {"role_description": "Python backend", "search_strategy": "", "cv_content": "Python"},
            [],
            max_queries=2,
        )

    assert len(plan) == 2
    assert [item["query"] for item in plan] == [
        "Senior Python Backend Engineer",
        "Senior Python Backend Entwickler",
    ]


async def test_generate_search_plan_propagates_runtime_error(mock_provider):
    mock_provider.generate_structured_async.side_effect = OSError("local model offline")
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        with pytest.raises(OSError, match="offline"):
            await LLMService().generate_search_plan({}, [])


async def test_normalize_profile_uses_contract_then_maps_to_storage_shape(mock_provider):
    mock_provider.generate_structured_async.return_value = _result(_golden("profile_normalize"))
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        result = await LLMService().normalize_user_profile(
            "Senior Python engineer, 7 years", "Senior backend", ""
        )

    assert result["experience_years"] == 7
    assert result["domain"] == "it"
    assert result["intent_domain"] == "it"
    request = mock_provider.generate_structured_async.await_args.args[0]
    assert request.task_id == "profile_normalize"


async def test_normalize_job_batch_preserves_rows_and_validated_ranges(mock_provider):
    mock_provider.generate_structured_async.return_value = _result(_golden("job_normalize"))
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        rows = await LLMService().normalize_job_batch(
            [{"title": "Senior Backend Engineer", "description": "5 years Python, 80-100%"}]
        )

    assert len(rows) == 1
    assert rows[0]["experience_min_years"] == 5
    assert rows[0]["workload_max"] == 100
    assert rows[0]["role_type"] == "technical"
    assert mock_provider.generate_structured_async.await_args.args[0].task_id == "job_normalize"


async def test_normalize_job_batch_rejects_wrong_row_count(mock_provider):
    payload = _golden("job_normalize")
    mock_provider.generate_structured_async.return_value = _result(payload)
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        with pytest.raises(Exception):
            await LLMService().normalize_job_batch(
                [{"title": "One"}, {"title": "Two"}]
            )


async def test_match_returns_calibrated_dimension_scores(mock_provider):
    mock_provider.generate_structured_async.return_value = _result(_golden("job_match"))
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        rows = await LLMService().analyze_job_batch(
            [{"title": "Backend", "description": "Python C1"}],
            {"role_description": "Backend", "cv_summary": "7 years Python"},
        )

    assert rows[0]["affinity_score"] == 91
    assert rows[0]["skill_match_score"] == 95
    assert rows[0]["worth_applying"] is True
    assert mock_provider.generate_structured_async.await_args.args[0].task_id == "job_match"


async def test_critique_and_rerank_use_bounded_contracts(mock_provider):
    initial = [{"affinity_score": 70, "affinity_analysis": "Initial", "worth_applying": True}]
    mock_provider.generate_structured_async.return_value = _result(_golden("job_critique"))
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        critiqued = await service.critique_job_batch(
            [{"title": "Backend", "description": "Python"}], initial, {}
        )
        assert critiqued[0]["affinity_score"] == 72

        mock_provider.generate_structured_async.return_value = _result(_golden("job_rerank"))
        reranked = await service.rerank_top_jobs(
            [
                {"job_index": 3, "current_score": 84, "job_metadata": {"title": "A"}},
                {"job_index": 5, "current_score": 76, "job_metadata": {"title": "B"}},
            ],
            {},
        )

    assert [item["job_index"] for item in reranked] == [3, 5]
    assert [item["final_score"] for item in reranked] == [88, 74]


async def test_summarize_cv_keeps_local_text_timeout_boundary(mock_provider):
    mock_provider.generate_text_async.return_value = "- Experience: 5 years\n- Skills: Python"
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        summary = await LLMService().summarize_cv("Long CV")

    assert "Python" in summary
    assert mock_provider.generate_text_async.await_count == 1


def test_runtime_policy_clamps_small_context_batch_and_prompt(mock_provider):
    mock_provider.context_window = 4_096
    service = LLMService()
    with (
        patch.object(service, "_get_provider", return_value=mock_provider),
        patch.object(settings, "ANALYSIS_BATCH_SIZE", 5),
        patch.object(settings, "SEARCH_LOW_CONTEXT_ANALYSIS_BATCH_SIZE", 1),
        patch.object(settings, "MATCH_PROMPT_TARGET_CHARS", 12_000),
        patch.object(settings, "SEARCH_LOW_CONTEXT_MATCH_PROMPT_TARGET_CHARS", 3_600),
    ):
        policy = service.get_step_runtime_policy("match")

    assert policy["low_context"] is True
    assert policy["batch_size"] == 1
    assert policy["prompt_budget_chars"] <= 3_600


def test_normalize_searches_infers_types_and_drops_cosmetic_duplicates(llm_service):
    normalized = llm_service._normalize_searches(
        [
            {"query": "Senior Python Engineer", "domain": "IT", "language": "EN"},
            {"query": "senior-python engineer", "domain": "it", "language": "en"},
            {"query": "FastAPI", "domain": "it", "language": "en"},
        ]
    )

    assert len(normalized) == 2
    assert normalized[0]["type"] == "occupation"
    assert normalized[1]["type"] == "keyword"


def test_step_circuit_keys_are_model_and_task_scoped(mock_provider):
    service = LLMService()
    with (
        patch.object(service, "_get_provider", return_value=mock_provider),
        patch("backend.services.llm_service.circuit_registry.get") as get_breaker,
    ):
        get_breaker.return_value.state = CircuitState.CLOSED
        assert service.is_step_circuit_open("match") is False

    assert get_breaker.call_args.args[0] == "match:ollama-local/test-model"
