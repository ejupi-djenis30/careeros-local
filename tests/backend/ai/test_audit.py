from __future__ import annotations

import json

from backend.ai.audit import AIExecutionAudit, fingerprint_references, record_execution
from backend.ai.models import AIExecution


def test_ai_audit_persists_only_fingerprints_and_controlled_metadata(db_session, test_user) -> None:
    fingerprint = fingerprint_references(
        task="coach",
        reference_ids=["fact-2", "fact-1"],
        contract_version="1.0.0",
    )
    execution = record_execution(
        db_session,
        AIExecutionAudit(
            user_id=test_user.id,
            task="coach",
            contract_version="1.0.0",
            model_id="llama-cpp-local/qwen3-1.7b-q8",
            input_fingerprint=fingerprint,
            output_fingerprint="b" * 64,
            evidence_count=2,
            accepted=True,
            repair_count=0,
            validation_codes=[],
            duration_ms=125,
            prompt_tokens=200,
            completion_tokens=40,
        ),
    )
    persisted = db_session.get(AIExecution, execution.id)
    serialized = json.dumps(
        {column.name: getattr(persisted, column.name) for column in AIExecution.__table__.columns},
        default=str,
    )
    assert "private prompt" not in serialized
    assert "model output" not in serialized
    assert fingerprint in serialized


def test_reference_fingerprint_is_stable_and_order_independent() -> None:
    first = fingerprint_references(
        task="coach", reference_ids=["b", "a", "a"], contract_version="1.0.0"
    )
    second = fingerprint_references(
        task="coach", reference_ids=["a", "b"], contract_version="1.0.0"
    )
    assert first == second
    assert len(first) == 64


def test_reference_fingerprint_distinguishes_reused_ids_with_different_content() -> None:
    first = fingerprint_references(
        task="job_match",
        reference_ids=["candidate:profile", "job:0"],
        contract_version="1.1.0",
        evidence_digests={"candidate:profile": "a" * 64, "job:0": "b" * 64},
    )
    second = fingerprint_references(
        task="job_match",
        reference_ids=["candidate:profile", "job:0"],
        contract_version="1.1.0",
        evidence_digests={"candidate:profile": "a" * 64, "job:0": "c" * 64},
    )

    assert first != second
