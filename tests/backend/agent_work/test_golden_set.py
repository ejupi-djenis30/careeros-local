from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.agent_work.proposal_service import ProposalService
from backend.agent_work.schemas import (
    AnalysisProposalPayload,
    DiscoveryProposalPayload,
    ProposalPayload,
)
from backend.agent_work.service import AgentWorkError
from backend.agent_work.validation import eligibility, validate_proposal_payload
from backend.career.models import CandidateProfile
from tests.backend.agent_work.helpers import analysis, make_work, submission

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "golden-v1.json"


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _request(case: dict[str, Any], context: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(work_kind=case["kind"], context_snapshot=context)


def _scores(payload: ProposalPayload) -> list[Any]:
    if isinstance(payload, DiscoveryProposalPayload):
        return [listing.scores for listing in payload.listings]
    if isinstance(payload, AnalysisProposalPayload):
        return [payload.scores]
    return []


def _gates(payload: ProposalPayload) -> list[list[Any]]:
    if isinstance(payload, DiscoveryProposalPayload):
        return [listing.gates for listing in payload.listings]
    if isinstance(payload, AnalysisProposalPayload):
        return [payload.gates]
    return []


def _evaluate(case: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"schema_valid": False, "outcome": None}
    try:
        payload = TypeAdapter(ProposalPayload).validate_python(case["proposal"])
        result["schema_valid"] = True
        validate_proposal_payload(_request(case, context), payload)
    except ValidationError:
        result["outcome"] = "schema_invalid"
        return result
    except AgentWorkError as exc:
        result["outcome"] = exc.code
        return result

    result["outcome"] = "accepted"
    result["overall_scores"] = [item.overall_score for item in _scores(payload)]
    result["eligibility"] = [eligibility(item) for item in _gates(payload)]
    if case["expected"].get("untrusted_source_preserved"):
        assert isinstance(payload, DiscoveryProposalPayload)
        result["untrusted_source_preserved"] = (
            payload.listings[0].source_text == case["proposal"]["listings"][0]["source_text"]
        )
    return result


@pytest.mark.parametrize("case", _fixture()["cases"], ids=lambda case: case["id"])
def test_versioned_agent_golden_case(case: dict[str, Any]) -> None:
    fixture = _fixture()
    actual = _evaluate(case, fixture["context"])
    expected = case["expected"]
    assert actual["schema_valid"] is True
    assert actual["outcome"] == expected["outcome"]
    if expected["outcome"] == "accepted" and "overall_score" in expected:
        assert actual["overall_scores"] == [expected["overall_score"]]
        assert actual["eligibility"] == [expected["eligibility"]]
    if expected.get("untrusted_source_preserved"):
        assert actual["untrusted_source_preserved"] is True


def test_versioned_golden_quality_metrics_meet_declared_thresholds() -> None:
    fixture = _fixture()
    cases = fixture["cases"]
    evaluated = [(case, _evaluate(case, fixture["context"])) for case in cases]
    score_cases = [pair for pair in evaluated if "overall_score" in pair[0]["expected"]]
    unsupported = [
        pair for pair in evaluated if pair[0]["expected"]["outcome"] == "evidence_invalid"
    ]
    metrics = {
        "schema_valid_rate": sum(actual["schema_valid"] for _, actual in evaluated) / len(evaluated),
        "expected_outcome_accuracy": sum(
            actual["outcome"] == case["expected"]["outcome"] for case, actual in evaluated
        )
        / len(evaluated),
        "derived_score_accuracy": sum(
            actual["overall_scores"] == [case["expected"]["overall_score"]]
            for case, actual in score_cases
        )
        / len(score_cases),
        "unsupported_claim_recall": sum(
            actual["outcome"] == "evidence_invalid" for _, actual in unsupported
        )
        / len(unsupported),
    }
    assert metrics == fixture["quality_thresholds"]


def test_eligible_location_and_contract_gates_must_match_candidate_preferences() -> None:
    fixture = _fixture()
    golden = next(case for case in fixture["cases"] if case["id"] == "analyze-evidence-bound")
    context = deepcopy(fixture["context"])
    context["target_job"].update(
        location="Berlin",
        description="Python Engineer English Berlin temporary posted today",
    )
    proposal = deepcopy(golden["proposal"])
    by_dimension = {gate["dimension"]: gate for gate in proposal["gates"]}
    by_dimension["location"]["quote_references"] = ["Berlin"]
    by_dimension["contract"]["quote_references"] = ["temporary"]
    payload = TypeAdapter(ProposalPayload).validate_python(proposal)
    with pytest.raises(AgentWorkError) as exc:
        validate_proposal_payload(_request(golden, context), payload)
    assert exc.value.code == "evidence_invalid"


def test_language_dimension_uses_cited_language_fact_instead_of_a_fixed_language_list() -> None:
    fixture = _fixture()
    golden = next(case for case in fixture["cases"] if case["id"] == "analyze-evidence-bound")
    context = deepcopy(fixture["context"])
    language_fact = context["facts"][1]
    language_fact.update(title="Polish", description="Polish C1", attributes={"language": "Polish"})
    context["target_job"]["description"] = (
        "Python Engineer Polish Zurich permanent posted today"
    )
    proposal = deepcopy(golden["proposal"])
    language_gate = next(gate for gate in proposal["gates"] if gate["dimension"] == "language")
    language_gate["quote_references"] = ["Polish"]
    payload = TypeAdapter(ProposalPayload).validate_python(proposal)
    validate_proposal_payload(_request(golden, context), payload)


@pytest.mark.parametrize("case", ["cross_dimension", "missing_freshness", "negated_requirement"])
def test_resolved_gates_require_server_classified_atomic_source_evidence(case: str) -> None:
    fixture = _fixture()
    context = deepcopy(fixture["context"])
    golden = next(item for item in fixture["cases"] if item["id"] == "analyze-evidence-bound")
    proposal = deepcopy(golden["proposal"])
    if case == "cross_dimension":
        for gate in proposal["gates"]:
            gate["quote_references"] = ["Python"]
    elif case == "missing_freshness":
        context["target_job"]["description"] = "Python Engineer English Zurich permanent"
        freshness = next(gate for gate in proposal["gates"] if gate["dimension"] == "freshness")
        freshness["quote_references"] = ["Python"]
    else:
        context["target_job"]["description"] += " Python not required"
        requirement = next(
            gate for gate in proposal["gates"] if gate["dimension"] == "requirements"
        )
        requirement["quote_references"] = ["Python not required"]
    payload = TypeAdapter(ProposalPayload).validate_python(proposal)
    with pytest.raises(AgentWorkError) as exc:
        validate_proposal_payload(_request(golden, context), payload)
    assert exc.value.code == "evidence_invalid"


def test_versioned_golden_stale_lifecycle_case(db_session, test_user) -> None:
    case = _fixture()["lifecycle_cases"][0]
    work, grant, _, fact = make_work(db_session, test_user.id, case["kind"])
    request = submission(work, analysis(fact.id))
    profile = db_session.query(CandidateProfile).filter_by(user_id=test_user.id).one()
    profile.display_name = "Changed after frozen context"
    profile.revision += 1
    db_session.commit()

    with pytest.raises(AgentWorkError) as exc:
        ProposalService(db_session).submit_proposal(grant.id, work.id, request)
    assert exc.value.code == case["expected"]["outcome"]
