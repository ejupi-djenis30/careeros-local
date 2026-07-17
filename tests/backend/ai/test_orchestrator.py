from backend.ai.contracts import CoachResult, ValidationCode
from backend.ai.orchestrator import AIValidationError, LocalAIOrchestrator, OrchestrationRequest
from backend.ai.retrieval import EvidenceDocument
from backend.inference.ports import InferenceUsage, StructuredInferenceResult

FACT_ID = "11111111-1111-4111-8111-111111111111"


class _Provider:
    model_id = "test/compact"

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads
        self.requests = []

    async def generate_structured_async(self, request):
        self.requests.append(request)
        payload = self.payloads.pop(0)
        return StructuredInferenceResult(
            payload=payload,
            model_id=self.model_id,
            runtime="test",
            usage=InferenceUsage(prompt_tokens=10, completion_tokens=5),
            duration_ms=2,
        )


def _valid_payload() -> dict:
    return {
        "answer": "Python engineering is supported.",
        "claims": [
            {
                "text": "Python engineering is supported.",
                "fact_ids": [FACT_ID],
                "job_ids": [],
            }
        ],
        "fact_citations": [FACT_ID],
        "job_citations": [],
        "confidence": 0.8,
        "missing_evidence": [],
    }


async def test_orchestrator_repairs_schema_once_and_returns_typed_output() -> None:
    invalid = _valid_payload()
    invalid["fact_citations"] = []
    provider = _Provider([invalid, _valid_payload()])
    orchestrator = LocalAIOrchestrator(provider)  # type: ignore[arg-type]

    result = await orchestrator.execute(
        OrchestrationRequest(
            task_id="coach",
            user_prompt="Help with Python engineering",
            evidence=(
                EvidenceDocument(id=FACT_ID, kind="fact", text="Python backend engineering"),
            ),
        )
    )

    assert isinstance(result.output, CoachResult)
    assert result.repair_count == 1
    assert len(provider.requests) == 2
    assert "REPAIR_ONCE" in provider.requests[1].user_prompt
    assert result.usage == {"prompt_tokens": 20, "completion_tokens": 10}


async def test_orchestrator_never_performs_a_second_repair() -> None:
    unsupported = _valid_payload()
    provider = _Provider([unsupported, unsupported])
    orchestrator = LocalAIOrchestrator(provider)  # type: ignore[arg-type]

    try:
        await orchestrator.execute(
            OrchestrationRequest(
                task_id="coach",
                user_prompt="Python",
                evidence=(
                    EvidenceDocument(id=FACT_ID, kind="fact", text="Hospitality manager"),
                ),
            )
        )
    except AIValidationError as exc:
        assert ValidationCode.UNSUPPORTED_CLAIM in {item.code for item in exc.issues}
    else:
        raise AssertionError("unsupported output must fail closed")

    assert len(provider.requests) == 2
