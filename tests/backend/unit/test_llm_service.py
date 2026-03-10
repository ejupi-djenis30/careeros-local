import pytest
from unittest.mock import MagicMock, patch
from tenacity import RetryError
from backend.services.llm_service import LLMService


@pytest.fixture
def mock_provider():
    return MagicMock()


@pytest.fixture
def llm_service(mock_provider):
    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        return LLMService()


def test_generate_search_plan_success(mock_provider):
    mock_provider.generate_json.return_value = {
        "searches": [
            {"domain": "it", "language": "en", "type": "occupation", "query": "Software Engineer"}
        ]
    }
    mock_provider.model_id = "groq/test-model"

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        profile = {"role_description": "Dev", "search_strategy": "Be aggressive", "cv_content": "Experienced"}
        providers = [{"name": "swissdevjobs", "description": "IT jobs"}]

        plan = service.generate_search_plan(profile, providers, max_queries=1)

        assert len(plan) == 1
        assert plan[0]["query"] == "Software Engineer"
        mock_provider.generate_json.assert_called_once()


def test_generate_search_plan_error(mock_provider):
    mock_provider.generate_json.side_effect = Exception("LLM Error")
    mock_provider.model_id = "groq/test-model"

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        with pytest.raises(RetryError):
            service.generate_search_plan({}, [])


def test_analyze_job_match(mock_provider):
    mock_provider.generate_json.return_value = {
        "affinity_score": 90,
        "affinity_analysis": "Perfect match",
        "worth_applying": True,
    }

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        res = service.analyze_job_match({"title": "Dev"}, {"role_description": "Dev"})
        assert res["affinity_score"] == 90
        assert res["worth_applying"] is True


def test_each_method_calls_correct_step(mock_provider):
    """Verify each method dispatches to the correct pipeline step."""
    mock_provider.generate_json.return_value = {"searches": []}
    mock_provider.model_id = "test/model"

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider) as mock_factory:
        service = LLMService()

        service.generate_search_plan({"role_description": "X", "search_strategy": "", "cv_content": ""}, [])
        mock_factory.assert_called_with("plan")

        mock_factory.reset_mock()
        mock_provider.generate_json.return_value = {"relevant": True, "affinity_score": 50, "affinity_analysis": "", "worth_applying": False}
        service.analyze_job_match({}, {})
        mock_factory.assert_called_with("match")


def test_generate_search_plan_respects_max_queries(mock_provider):
    """Verify the service truncates results when max_queries is given."""
    mock_provider.generate_json.return_value = {
        "searches": [
            {"domain": "it", "language": "en", "type": "occupation", "query": f"Job {i}"}
            for i in range(10)
        ]
    }
    mock_provider.model_id = "groq/test-model"

    with patch("backend.services.llm_service.get_provider_for_step", return_value=mock_provider):
        service = LLMService()
        plan = service.generate_search_plan({}, [], max_queries=3)
        assert len(plan) == 3
