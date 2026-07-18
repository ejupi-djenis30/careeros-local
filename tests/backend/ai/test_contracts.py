from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.ai.contracts import CoachResult, GroundedClaim
from backend.ai.task_specs import TASK_SPECS


def test_every_task_contract_is_deterministic_strict_and_versioned() -> None:
    assert {"coach", "profile_normalize", "search_plan", "job_normalize", "job_match"} <= set(
        TASK_SPECS
    )
    for task_id, spec in TASK_SPECS.items():
        assert spec.task_id == task_id
        assert spec.temperature == 0.0
        assert spec.max_output_tokens > 0
        assert spec.max_context_chars > 0
        assert spec.version.count(".") == 2
        assert spec.schema()["additionalProperties"] is False


def test_grounded_coach_contract_rejects_unbounded_or_extra_output() -> None:
    valid = CoachResult(
        answer="Use the verified delivery result.",
        claims=[
            GroundedClaim(
                text="Delivery improved.",
                fact_ids=["00000000-0000-0000-0000-000000000001"],
                job_ids=[],
            )
        ],
        fact_citations=["00000000-0000-0000-0000-000000000001"],
        job_citations=[],
        confidence=0.8,
        missing_evidence=[],
    )
    assert valid.confidence == 0.8
    with pytest.raises(ValidationError):
        CoachResult.model_validate({**valid.model_dump(), "private_reasoning": "secret"})
