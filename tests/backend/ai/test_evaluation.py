import os

from backend.ai.evaluation import (
    evaluate_case,
    list_reports,
    load_dataset,
    persist_report,
    run_live_evaluation,
    validate_offline_dataset,
)
from backend.inference.ports import InferenceUsage, StructuredInferenceResult


class _GoldenProvider:
    model_id = "test/compact-local"
    runtime_capabilities = frozenset({"json-schema", "seed"})
    process_id = os.getpid()

    def __init__(self) -> None:
        self.outputs = {
            case.task_id: case.expected_output for case in load_dataset().cases
        }

    async def generate_structured_async(self, request):
        return StructuredInferenceResult(
            payload=self.outputs[request.task_id],
            model_id=self.model_id,
            runtime="test",
            usage=InferenceUsage(prompt_tokens=10, completion_tokens=10),
            duration_ms=1,
        )


def test_offline_evaluator_reports_all_metrics_without_model_or_network() -> None:
    report = validate_offline_dataset()

    assert report.case_count == 8
    assert report.passed is True
    assert report.schema_pass_rate == 1
    assert report.semantic_pass_rate == 1
    assert report.grounding_pass_rate == 1
    assert report.assertion_pass_rate == 1
    assert len(report.result_fingerprint) == 64


def test_evaluator_detects_schema_and_expectation_regression() -> None:
    case = load_dataset().cases[0]
    metrics = evaluate_case(case, {"answer": "missing required fields"})

    assert metrics.schema_valid is False
    assert metrics.passed is False
    assert metrics.assertions_passed == 0


def test_aggregate_report_persistence_contains_no_case_content(db_session) -> None:
    report = validate_offline_dataset()
    persisted = persist_report(db_session, report)

    assert persisted.passed is True
    assert persisted.metrics["schema_pass_rate"] == 1
    assert "cases" not in persisted.metrics
    assert list_reports(db_session)[0].result_fingerprint == report.result_fingerprint


async def test_live_evaluator_records_local_model_profile_and_peak_memory() -> None:
    report = await run_live_evaluation(_GoldenProvider())  # type: ignore[arg-type]

    assert report.passed is True
    assert report.peak_memory_bytes is not None
    assert report.peak_memory_bytes > 0
    assert report.model_profile["model_id"] == "test/compact-local"
    assert report.model_profile["runtime_capabilities"] == ["json-schema", "seed"]
    assert report.model_profile["memory_scope"] == "evaluator-process-rss"
