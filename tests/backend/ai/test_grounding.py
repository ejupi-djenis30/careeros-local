from backend.ai.contracts import CoachResult, GroundedClaim, ValidationCode
from backend.ai.grounding import validate_grounding, validate_semantics
from backend.ai.retrieval import EvidenceDocument

FACT_ID = "11111111-1111-4111-8111-111111111111"


def _coach(text: str, fact_id: str = FACT_ID) -> CoachResult:
    return CoachResult(
        answer=text,
        claims=[GroundedClaim(text=text, fact_ids=[fact_id])],
        fact_citations=[fact_id],
        confidence=0.8,
    )


def test_grounding_rejects_unknown_evidence() -> None:
    issues = validate_grounding(_coach("Python engineering"), [])
    assert {item.code for item in issues} == {ValidationCode.EVIDENCE_UNKNOWN}


def test_grounding_rejects_lexically_unsupported_claim() -> None:
    evidence = [EvidenceDocument(id=FACT_ID, kind="fact", text="Hospitality manager")]
    issues = validate_grounding(_coach("Python engineering"), evidence)
    assert ValidationCode.UNSUPPORTED_CLAIM in {item.code for item in issues}


def test_grounding_accepts_supported_claim() -> None:
    evidence = [EvidenceDocument(id=FACT_ID, kind="fact", text="Python backend engineering")]
    assert validate_grounding(_coach("Python engineering"), evidence) == []


def test_semantic_validator_rejects_inverted_ranges() -> None:
    class _Payload:
        def model_dump(self, *, mode: str):
            assert mode == "json"
            return {"results": [{"experience_min_years": 8, "experience_max_years": 3}]}

    issues = validate_semantics("job_normalize", _Payload())  # type: ignore[arg-type]
    assert ValidationCode.SEMANTIC_INVALID in {item.code for item in issues}
