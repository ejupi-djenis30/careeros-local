import pytest

from backend.ai.contracts import CoachResult, ValidationCode
from backend.ai.match_evidence import candidate_evidence_document, job_evidence_document
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
                evidence=(EvidenceDocument(id=FACT_ID, kind="fact", text="Hospitality manager"),),
            )
        )
    except AIValidationError as exc:
        assert ValidationCode.UNSUPPORTED_CLAIM in {item.code for item in exc.issues}
    else:
        raise AssertionError("unsupported output must fail closed")

    assert len(provider.requests) == 2


async def test_coach_rejects_broad_claim_with_only_one_shared_token() -> None:
    broad = {
        "answer": "Python architect led a global transformation and saved millions.",
        "claims": [
            {
                "text": "Python architect led a global transformation and saved millions.",
                "fact_ids": [FACT_ID],
                "job_ids": [],
            }
        ],
        "fact_citations": [FACT_ID],
        "job_citations": [],
        "confidence": 0.9,
        "missing_evidence": [],
    }
    provider = _Provider([broad, broad])
    orchestrator = LocalAIOrchestrator(provider)  # type: ignore[arg-type]

    with pytest.raises(AIValidationError) as caught:
        await orchestrator.execute(
            OrchestrationRequest(
                task_id="coach",
                user_prompt="What should I emphasize?",
                evidence=(
                    EvidenceDocument(
                        id=FACT_ID,
                        kind="fact",
                        text="Python backend engineering",
                    ),
                ),
            )
        )

    assert ValidationCode.UNSUPPORTED_CLAIM in {issue.code for issue in caught.value.issues}


async def test_coach_rejects_one_invented_fact_despite_high_global_overlap() -> None:
    invented = {
        "answer": (
            "Python backend engineering delivered APIs for clients and won an international award."
        ),
        "claims": [
            {
                "text": (
                    "Python backend engineering delivered APIs for clients and won an "
                    "international award."
                ),
                "fact_ids": [FACT_ID],
                "job_ids": [],
            }
        ],
        "fact_citations": [FACT_ID],
        "job_citations": [],
        "confidence": 0.9,
        "missing_evidence": [],
    }
    provider = _Provider([invented, invented])

    with pytest.raises(AIValidationError) as caught:
        await LocalAIOrchestrator(provider).execute(  # type: ignore[arg-type]
            OrchestrationRequest(
                task_id="coach",
                user_prompt="What should I emphasize?",
                evidence=(
                    EvidenceDocument(
                        id=FACT_ID,
                        kind="fact",
                        text="Python backend engineering delivered APIs for clients.",
                    ),
                ),
            )
        )

    assert ValidationCode.UNSUPPORTED_CLAIM in {issue.code for issue in caught.value.issues}


async def test_coach_rejects_answer_with_no_claims_even_with_aggregate_citation() -> None:
    payload = {
        "answer": "Invented executive leadership result.",
        "claims": [],
        "fact_citations": [FACT_ID],
        "job_citations": [],
        "confidence": 0.9,
        "missing_evidence": [],
    }
    provider = _Provider([payload, payload])

    with pytest.raises(AIValidationError) as caught:
        await LocalAIOrchestrator(provider).execute(  # type: ignore[arg-type]
            OrchestrationRequest(
                task_id="coach",
                user_prompt="What should I emphasize?",
                evidence=(EvidenceDocument(id=FACT_ID, kind="fact", text="Python delivery."),),
            )
        )

    assert ValidationCode.SCHEMA_INVALID in {issue.code for issue in caught.value.issues}


async def test_coach_rejects_claim_assembled_from_multiple_unrelated_facts() -> None:
    fact_two = "22222222-2222-4222-8222-222222222222"
    fact_three = "33333333-3333-4333-8333-333333333333"
    collage = {
        "answer": "Python architecture earned international awards.",
        "claims": [
            {
                "text": "Python architecture earned international awards.",
                "fact_ids": [FACT_ID, fact_two, fact_three],
                "job_ids": [],
            }
        ],
        "fact_citations": [FACT_ID, fact_two, fact_three],
        "job_citations": [],
        "confidence": 0.9,
        "missing_evidence": [],
    }
    provider = _Provider([collage, collage])

    with pytest.raises(AIValidationError) as caught:
        await LocalAIOrchestrator(provider).execute(  # type: ignore[arg-type]
            OrchestrationRequest(
                task_id="coach",
                user_prompt="What should I emphasize?",
                evidence=(
                    EvidenceDocument(id=FACT_ID, kind="fact", text="Python delivery."),
                    EvidenceDocument(id=fact_two, kind="fact", text="Architecture reviews."),
                    EvidenceDocument(id=fact_three, kind="fact", text="International awards."),
                ),
            )
        )

    assert ValidationCode.UNSUPPORTED_CLAIM in {issue.code for issue in caught.value.issues}


@pytest.mark.parametrize(
    "claim_text",
    ["You led AI.", "You are CEO.", "I ran ML.", "Use Go."],
)
async def test_coach_short_technical_claims_require_real_support(claim_text: str) -> None:
    payload = {
        "answer": claim_text,
        "claims": [{"text": claim_text, "fact_ids": [FACT_ID], "job_ids": []}],
        "fact_citations": [FACT_ID],
        "job_citations": [],
        "confidence": 0.9,
        "missing_evidence": [],
    }
    provider = _Provider([payload, payload])

    with pytest.raises(AIValidationError) as caught:
        await LocalAIOrchestrator(provider).execute(  # type: ignore[arg-type]
            OrchestrationRequest(
                task_id="coach",
                user_prompt="What should I say?",
                evidence=(
                    EvidenceDocument(
                        id=FACT_ID,
                        kind="fact",
                        text="Managed a retail store and scheduled staff.",
                    ),
                ),
            )
        )

    assert ValidationCode.UNSUPPORTED_CLAIM in {issue.code for issue in caught.value.issues}


async def test_coach_answer_is_materialized_only_from_validated_claims() -> None:
    payload = _valid_payload()
    payload["answer"] = "Invented executive leadership result."
    provider = _Provider([payload])

    result = await LocalAIOrchestrator(provider).execute(  # type: ignore[arg-type]
        OrchestrationRequest(
            task_id="coach",
            user_prompt="What should I emphasize?",
            evidence=(
                EvidenceDocument(id=FACT_ID, kind="fact", text="Python engineering is supported."),
            ),
        )
    )

    assert result.output.answer == "Python engineering is supported."


async def test_job_match_rejects_unattested_free_form_claims() -> None:
    payload = {
        "results": [
            {
                "affinity_score": 100,
                "affinity_analysis": "Won a Nobel Prize and has 30 years of quantum research.",
                "worth_applying": True,
                "skill_match_score": 100,
                "experience_match_score": 100,
                "intent_match_score": 100,
                "language_match_score": 100,
                "location_match_score": 100,
                "transferability_score": 100,
                "qualification_gap_score": 100,
                "analysis_structured": {
                    "recommendation": "strong_fit",
                    "strengths": ["Nobel Prize"],
                    "evidence_citations": [
                        {
                            "type": "skill",
                            "assessment": "strength",
                            "job_evidence_id": "job:0",
                            "candidate_evidence_id": "candidate:profile",
                            "job_evidence": "Engineer",
                            "candidate_evidence": "Engineer",
                        },
                        {
                            "type": "experience",
                            "assessment": "strength",
                            "job_evidence_id": "job:0",
                            "candidate_evidence_id": "candidate:profile",
                            "job_evidence": "Engineer",
                            "candidate_evidence": "Engineer",
                        },
                    ],
                },
                "red_flags": ["quantum"],
            }
        ]
    }
    provider = _Provider([payload, payload])
    orchestrator = LocalAIOrchestrator(provider)  # type: ignore[arg-type]

    try:
        await orchestrator.execute(
            OrchestrationRequest(
                task_id="job_match",
                user_prompt="Compare candidate:profile with job:0",
                evidence=(
                    EvidenceDocument(
                        id="candidate:profile",
                        kind="candidate",
                        text="Engineer",
                    ),
                    EvidenceDocument(id="job:0", kind="job", text="Engineer"),
                ),
                expected_rows=1,
            )
        )
    except AIValidationError as exc:
        assert ValidationCode.SCHEMA_INVALID in {item.code for item in exc.issues}
    else:
        raise AssertionError("free-form match claims must fail closed")


async def test_job_match_rejects_model_supplied_redundant_citations() -> None:
    payload = {
        "results": [
            {
                "skill_match_score": 70,
                "experience_match_score": 50,
                "intent_match_score": 50,
                "language_match_score": 50,
                "location_match_score": 50,
                "transferability_score": 50,
                "qualification_gap_score": 50,
                "analysis_structured": {
                    "evidence_citations": [
                        {
                            "type": "skill",
                            "job_evidence_id": "job:1",
                            "candidate_evidence_id": "candidate:profile",
                            "job_quote_id": "job:1:skill:0",
                            "candidate_quote_id": "candidate:profile:skill:0",
                        }
                    ],
                },
            }
        ]
    }
    provider = _Provider([payload, payload])
    orchestrator = LocalAIOrchestrator(provider)  # type: ignore[arg-type]

    try:
        await orchestrator.execute(
            OrchestrationRequest(
                task_id="job_match",
                user_prompt="Compare candidate:profile with job:0",
                evidence=(
                    candidate_evidence_document({"cv_content": "Python engineer"}),
                    job_evidence_document(
                        {"description": "Python engineer"}, 0, description_limit=1800
                    ),
                    job_evidence_document(
                        {"description": "Python engineer"}, 1, description_limit=1800
                    ),
                ),
                expected_rows=1,
            )
        )
    except AIValidationError as exc:
        assert ValidationCode.SCHEMA_INVALID in {item.code for item in exc.issues}
    else:
        raise AssertionError("cross-row match citations must fail closed")
