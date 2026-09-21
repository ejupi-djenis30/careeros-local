from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.agent_work.schemas import (
    AnalysisProposalPayload,
    DiscoveryProposalPayload,
    ProposalPayload,
    ProposalSubmissionRequest,
    WorkScores,
)


def _sample_scores() -> dict:
    return {
        "role": {"score": 85, "explanation": "Strong fit for Python engineer"},
        "requirements": {"score": 90, "explanation": "Meets backend requirements"},
        "language": {"score": 100, "explanation": "Fluent English"},
        "location": {"score": 80, "explanation": "Hybrid Zurich"},
        "contract": {"score": 100, "explanation": "Permanent full-time"},
        "freshness": {"score": 95, "explanation": "Posted 2 days ago"},
        "overall_score": 90,
    }


def _sample_gates() -> list[dict]:
    from tests.backend.agent_work.helpers import gates

    return gates("c2b535fa-92b0-4f51-b0fa-d204d80a1001")


def test_discovery_proposal_schema_success() -> None:
    data = {
        "kind": "discover",
        "listings": [
            {
                "title": "Senior Python Engineer",
                "company": "Tech Corp",
                "location": "Zurich, Switzerland",
                "external_url": "https://example.com/jobs/123",
                "source_text": "We are looking for a Senior Python Engineer in Zurich. Fluent English required.",
                "observed_at": datetime.now(UTC).isoformat(),
                "source_platform": "company_careers",
                "gates": _sample_gates(),
                "scores": _sample_scores(),
            }
        ],
    }
    adapter = TypeAdapter(ProposalPayload)
    validated = adapter.validate_python(data)
    assert isinstance(validated, DiscoveryProposalPayload)
    assert validated.kind == "discover"
    assert len(validated.listings) == 1
    assert validated.listings[0].company == "Tech Corp"


@pytest.mark.parametrize(
    "observed_at",
    [datetime.now().replace(microsecond=0).isoformat(), (datetime.now(UTC) + timedelta(hours=1)).isoformat()],
)
def test_discovery_requires_current_timezone_aware_observation(observed_at):
    from tests.backend.agent_work.helpers import discovery

    payload = discovery()
    payload["listings"][0]["observed_at"] = observed_at
    with pytest.raises(ValidationError):
        DiscoveryProposalPayload.model_validate(payload)


def test_discovery_proposal_rejects_unknown_fields() -> None:
    data = {
        "kind": "discover",
        "listings": [
            {
                "title": "Engineer",
                "company": "Corp",
                "source_text": "Python role",
                "observed_at": datetime.now(UTC).isoformat(),
                "unknown_extra_field": "disallowed",
            }
        ],
    }
    adapter = TypeAdapter(ProposalPayload)
    with pytest.raises(ValidationError) as exc:
        adapter.validate_python(data)
    assert "extra_forbidden" in str(exc.value)


def test_discovery_proposal_rejects_unsafe_url() -> None:
    data = {
        "kind": "discover",
        "listings": [
            {
                "title": "Engineer",
                "company": "Corp",
                "external_url": "javascript:alert(1)",
                "source_text": "Python role",
                "observed_at": datetime.now(UTC).isoformat(),
            }
        ],
    }
    adapter = TypeAdapter(ProposalPayload)
    with pytest.raises(ValidationError):
        adapter.validate_python(data)


def test_discovery_proposal_rejects_oversized_listings() -> None:
    data = {
        "kind": "discover",
        "listings": [
            {
                "title": f"Engineer {i}",
                "company": "Corp",
                "source_text": "Python role",
                "observed_at": datetime.now(UTC).isoformat(),
            }
            for i in range(21)  # Max is 20
        ],
    }
    adapter = TypeAdapter(ProposalPayload)
    with pytest.raises(ValidationError):
        adapter.validate_python(data)


def test_analysis_proposal_schema_success() -> None:
    data = {
        "kind": "analyze",
        "gates": _sample_gates(),
        "scores": _sample_scores(),
        "claims": [
            {
                "claim_text": "Candidate has 5 years Python experience matching requirement",
                "fact_ids": ["c2b535fa-92b0-4f51-b0fa-d204d80a1001"],
                "quote_text": "At least 3 years of Python required",
            }
        ],
        "recommendation": "strong_fit",
    }
    adapter = TypeAdapter(ProposalPayload)
    validated = adapter.validate_python(data)
    assert isinstance(validated, AnalysisProposalPayload)
    assert validated.recommendation == "strong_fit"
    assert validated.scores.overall_score == 90


def test_scores_reject_out_of_range() -> None:
    scores = _sample_scores()
    scores["role"]["score"] = 101  # > 100
    with pytest.raises(ValidationError):
        WorkScores.model_validate(scores)


def test_submission_request_validates_digest_and_request_id() -> None:
    sub = {
        "request_id": "c2b535fa-92b0-4f51-b0fa-d204d80a1001",
        "input_digest": "a" * 64,
        "idempotency_key": "key-12345",
        "client": "Claude Code",
        "model": "claude-3-7-sonnet",
        "result": {
            "kind": "analyze",
            "gates": _sample_gates(),
            "scores": _sample_scores(),
            "claims": [
                {
                    "claim_text": "5 years experience",
                    "fact_ids": ["c2b535fa-92b0-4f51-b0fa-d204d80a1001"],
                }
            ],
            "recommendation": "consider",
        },
    }
    req = ProposalSubmissionRequest.model_validate(sub)
    assert req.client == "Claude Code"
    assert req.result.kind == "analyze"


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@example.com/job",
        "https://example.com\n/job",
        "https://[broken/job",
        "https:relative",
        "https://example.com:bad/job",
    ],
)
def test_source_urls_reject_credentials_controls_and_malformed_authority(url):
    from tests.backend.agent_work.helpers import discovery

    value = discovery()
    value["listings"][0]["external_url"] = url
    with pytest.raises(ValidationError):
        TypeAdapter(ProposalPayload).validate_python(value)


def test_material_payload_has_no_untyped_escape_hatches():
    from backend.agent_work.schemas import MaterialsProposalPayload

    schema = MaterialsProposalPayload.model_json_schema()
    for definition in schema["$defs"].values():
        if definition.get("type") == "object":
            assert definition.get("additionalProperties") is False
