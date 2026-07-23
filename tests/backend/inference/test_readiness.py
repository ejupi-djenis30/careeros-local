import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from backend.ai.task_specs import TASK_SPECS
from backend.inference import service as readiness_service
from backend.inference.ports import StructuredInferenceResult
from backend.inference.service import (
    LocalModelStatus,
    check_local_model_readiness,
    clear_local_model_readiness_cache,
)


def _ready_payload():
    return {
        "results": [
            {
                "skill_match_score": 50,
                "experience_match_score": 50,
                "intent_match_score": 50,
                "language_match_score": 50,
                "location_match_score": 50,
                "transferability_score": 50,
                "qualification_gap_score": 50,
            }
        ]
    }


def _coach_payload():
    return {
        "answer": "Synthetic evidence only.",
        "claims": [
            {
                "text": "Synthetic evidence only.",
                "fact_ids": ["11111111-1111-4111-8111-111111111111"],
                "job_ids": [],
            }
        ],
        "fact_citations": ["11111111-1111-4111-8111-111111111111"],
        "job_citations": [],
        "confidence": 1.0,
        "missing_evidence": [],
    }


@pytest.fixture(autouse=True)
def _reset_readiness_state(monkeypatch):
    monkeypatch.setattr(readiness_service, "_readiness_lock", asyncio.Lock())
    clear_local_model_readiness_cache()
    yield
    clear_local_model_readiness_cache()


def _status(
    *,
    available: bool,
    ready: bool,
    error_code: str | None = None,
    runtime: str = "llama.cpp",
) -> LocalModelStatus:
    return LocalModelStatus(
        available=available,
        ready=ready,
        endpoint="http://127.0.0.1:43001",
        configured_model="compact-local",
        installed_models=["compact-local"] if available else [],
        error_code=error_code,
        runtime=runtime,
    )


@pytest.mark.asyncio
async def test_readiness_fails_without_contacting_inference_when_runtime_is_missing() -> None:
    with (
        patch(
            "backend.inference.service.get_local_model_status",
            new=AsyncMock(
                return_value=_status(
                    available=False,
                    ready=False,
                    error_code="local_runtime_unreachable",
                )
            ),
        ),
        patch("backend.inference.service.get_provider_for_step") as provider_factory,
    ):
        result = await check_local_model_readiness()

    assert result.ready is False
    assert result.error_code == "local_runtime_unreachable"
    assert [check.status for check in result.checks] == [
        "passed",
        "failed",
        "failed",
        "failed",
    ]
    provider_factory.assert_not_called()


@pytest.mark.asyncio
async def test_readiness_requires_schema_valid_content_free_output() -> None:
    provider = AsyncMock()
    provider.model_id = "llama.cpp/compact-local"
    provider.runtime_name = "llama.cpp"
    provider.endpoint = "http://127.0.0.1:43001"
    provider.model = "compact-local"
    provider.generate_structured_async.side_effect = [
        StructuredInferenceResult(
            payload=_ready_payload(),
            model_id=provider.model_id,
            runtime="llama.cpp",
        ),
        StructuredInferenceResult(
            payload=_coach_payload(),
            model_id=provider.model_id,
            runtime="llama.cpp",
        ),
    ]
    with (
        patch(
            "backend.inference.service.get_local_model_status",
            new=AsyncMock(return_value=_status(available=True, ready=True)),
        ),
        patch("backend.inference.service.get_provider_for_step", return_value=provider),
    ):
        result = await check_local_model_readiness()

    match_request = provider.generate_structured_async.await_args_list[0].args[0]
    coach_request = provider.generate_structured_async.await_args_list[1].args[0]
    assert match_request.task_id == "readiness"
    assert match_request.temperature == 0
    assert "MatchEvidence" not in str(match_request.json_schema)
    assert "analysis_structured" not in str(match_request.json_schema)
    assert "CoachResult" in str(coach_request.json_schema)
    assert coach_request.max_tokens == TASK_SPECS["coach"].max_output_tokens == 600
    assert provider.generate_structured_async.await_count == 2
    assert "career" not in match_request.user_prompt.casefold()
    assert result.ready is True
    assert result.model_id == "llama.cpp/compact-local"
    assert all(check.status == "passed" for check in result.checks)


@pytest.mark.asyncio
async def test_readiness_rejects_invalid_structured_output_without_exposing_it() -> None:
    provider = AsyncMock()
    provider.model_id = "ollama-local/local-model"
    provider.runtime_name = "ollama"
    provider.endpoint = "http://127.0.0.1:43001"
    provider.model = "compact-local"
    provider.generate_structured_async.return_value = StructuredInferenceResult(
        payload={"results": [], "private": "must-not-escape"},
        model_id=provider.model_id,
        runtime="ollama",
    )
    with (
        patch(
            "backend.inference.service.get_local_model_status",
            new=AsyncMock(return_value=_status(available=True, ready=True, runtime="ollama")),
        ),
        patch("backend.inference.service.get_provider_for_step", return_value=provider),
    ):
        result = await check_local_model_readiness()

    assert result.ready is False
    assert result.error_code == "structured_probe_failed"
    assert "must-not-escape" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_readiness_rejects_provider_identity_race_before_generation() -> None:
    provider = AsyncMock()
    provider.model_id = "ollama-local/compact-local"
    provider.runtime_name = "ollama"
    provider.endpoint = "http://127.0.0.1:43001"
    provider.model = "compact-local"
    with (
        patch(
            "backend.inference.service.get_local_model_status",
            new=AsyncMock(return_value=_status(available=True, ready=True)),
        ),
        patch("backend.inference.service.get_provider_for_step", return_value=provider),
    ):
        result = await check_local_model_readiness()

    assert result.ready is False
    assert result.error_code == "provider_identity_changed"
    provider.generate_structured_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_readiness_rejects_endpoint_outside_local_boundary() -> None:
    status = _status(available=True, ready=True)
    status.endpoint = "http://remote.example:11434"
    with (
        patch(
            "backend.inference.service.get_local_model_status",
            new=AsyncMock(return_value=status),
        ),
        patch("backend.inference.service.get_provider_for_step") as provider_factory,
    ):
        result = await check_local_model_readiness()

    assert result.ready is False
    assert result.error_code == "inference_endpoint_not_allowed"
    assert result.checks[0].code == "endpoint_allowed"
    assert result.checks[0].status == "failed"
    provider_factory.assert_not_called()


@pytest.mark.asyncio
async def test_readiness_uses_one_global_deadline_for_both_contract_probes() -> None:
    provider = AsyncMock()
    provider.model_id = "ollama/compact-local"
    provider.runtime_name = "ollama"
    provider.endpoint = "http://127.0.0.1:43001"
    provider.model = "compact-local"

    async def slow_generation(request):
        is_match = request.json_schema.get("title") == "JobMatchResult"
        await asyncio.sleep(0.02 if is_match else 0.08)
        payload = _ready_payload() if is_match else _coach_payload()
        return StructuredInferenceResult(
            payload=payload,
            model_id=provider.model_id,
            runtime="ollama",
        )

    provider.generate_structured_async.side_effect = slow_generation
    started = time.monotonic()
    with (
        patch(
            "backend.inference.service.get_local_model_status",
            new=AsyncMock(return_value=_status(available=True, ready=True, runtime="ollama")),
        ),
        patch("backend.inference.service.get_provider_for_step", return_value=provider),
    ):
        result = await check_local_model_readiness(timeout_seconds=0.07)

    assert time.monotonic() - started < 0.12
    assert result.ready is False
    assert result.error_code == "structured_probe_timeout"
    # Under load, the shared deadline may be exhausted immediately after the
    # first probe; otherwise the second probe starts and is cancelled by it.
    assert provider.generate_structured_async.await_count in {1, 2}


@pytest.mark.asyncio
async def test_readiness_deadline_bounds_slow_status_retrieval() -> None:
    async def slow_status() -> LocalModelStatus:
        await asyncio.sleep(1)
        return _status(available=True, ready=True)

    status_lookup = AsyncMock(side_effect=slow_status)
    started = time.monotonic()
    with (
        patch("backend.inference.service.get_local_model_status", new=status_lookup),
        patch("backend.inference.service.get_provider_for_step") as provider_factory,
    ):
        result = await check_local_model_readiness(timeout_seconds=0.03, force=True)

    assert time.monotonic() - started < 0.15
    assert result.ready is False
    assert result.error_code == "structured_probe_timeout"
    assert result.runtime == "unknown"
    assert status_lookup.await_count == 1
    provider_factory.assert_not_called()


@pytest.mark.asyncio
async def test_readiness_deadline_bounds_lock_contention() -> None:
    status_lookup = AsyncMock(return_value=_status(available=True, ready=True))
    readiness_lock = readiness_service._readiness_lock
    await readiness_lock.acquire()
    started = time.monotonic()
    try:
        with (
            patch("backend.inference.service.get_local_model_status", new=status_lookup),
            patch("backend.inference.service.get_provider_for_step") as provider_factory,
        ):
            result = await check_local_model_readiness(timeout_seconds=0.03, force=True)
    finally:
        readiness_lock.release()

    assert time.monotonic() - started < 0.15
    assert result.ready is False
    assert result.error_code == "structured_probe_timeout"
    assert [check.status for check in result.checks] == [
        "passed",
        "passed",
        "passed",
        "failed",
    ]
    assert status_lookup.await_count == 1
    provider_factory.assert_not_called()


@pytest.mark.asyncio
async def test_concurrent_forced_readiness_calls_share_one_probe() -> None:
    provider = AsyncMock()
    provider.model_id = "ollama/compact-local"
    provider.runtime_name = "ollama"
    provider.endpoint = "http://127.0.0.1:43001"
    provider.model = "compact-local"

    async def generation(request):
        await asyncio.sleep(0.01)
        payload = (
            _ready_payload()
            if request.json_schema.get("title") == "JobMatchResult"
            else _coach_payload()
        )
        return StructuredInferenceResult(
            payload=payload,
            model_id=provider.model_id,
            runtime="ollama",
        )

    provider.generate_structured_async.side_effect = generation
    with (
        patch(
            "backend.inference.service.get_local_model_status",
            new=AsyncMock(return_value=_status(available=True, ready=True, runtime="ollama")),
        ),
        patch("backend.inference.service.get_provider_for_step", return_value=provider),
    ):
        first, second = await asyncio.gather(
            check_local_model_readiness(force=True),
            check_local_model_readiness(force=True),
        )

    assert first.ready is second.ready is True
    assert provider.generate_structured_async.await_count == 2
