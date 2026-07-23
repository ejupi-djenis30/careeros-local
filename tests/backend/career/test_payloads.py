from copy import deepcopy

import pytest
from pydantic import ValidationError

from backend.career.payloads import PAYLOAD_SCHEMAS, CareerPreferences
from backend.career.schemas import CareerFactInput, CareerProfileWrite

FACT_PAYLOADS = {
    "experience": {"role": "Engineer", "organization": "Local Co"},
    "education": {"institution": "ETH", "qualification": "MSc"},
    "project": {"name": "Private portfolio"},
    "skill": {"name": "Python", "level": "advanced"},
    "language": {"language": "Italian", "level": "native"},
    "certification": {"name": "Security", "issuer": "Local Institute"},
    "achievement": {"title": "Reduced lead time", "metric_value": 40},
    "volunteering": {"title": "Mentor", "organization": "Community"},
    "publication": {"title": "Reliable local agents"},
    "link": {"label": "Portfolio", "url": "https://portfolio.example"},
    "award": {"title": "Engineering award", "issuer": "Industry Guild"},
    "membership": {"organization": "Engineering Guild", "role": "Member"},
    "reference": {
        "name": "A. Manager",
        "relationship": "Former manager",
        "permission_to_contact": False,
    },
    "portfolio": {"name": "Architecture case studies", "url": "https://work.example"},
}


def test_every_supported_fact_type_has_a_strict_typed_payload():
    assert set(FACT_PAYLOADS) == set(PAYLOAD_SCHEMAS)
    for fact_type, payload in FACT_PAYLOADS.items():
        fact = CareerFactInput(fact_type=fact_type, payload=payload)
        assert fact.payload


@pytest.mark.parametrize(
    ("fact_type", "payload", "message"),
    [
        (
            "experience",
            {
                "role": "Engineer",
                "organization": "Local Co",
                "responsibilities": ["Delivery", " delivery "],
            },
            "unique",
        ),
        (
            "membership",
            {
                "organization": "Guild",
                "role": "Member",
                "start_date": "2026-01-01",
                "end_date": "2025-01-01",
            },
            "end_date",
        ),
        (
            "reference",
            {
                "name": "A. Manager",
                "relationship": "Former manager",
                "permission_to_contact": True,
            },
            "email or phone",
        ),
        (
            "portfolio",
            {"name": "Unsafe", "url": "file:///private/data"},
            "http",
        ),
    ],
)
def test_nested_payloads_reject_ambiguous_or_unsafe_data(fact_type, payload, message):
    with pytest.raises(ValidationError, match=message):
        CareerFactInput(fact_type=fact_type, payload=payload)


def test_imported_facts_require_complete_source_provenance():
    with pytest.raises(ValidationError, match="source document"):
        CareerFactInput(
            fact_type="achievement",
            payload={"title": "Imported claim"},
            verification_status="imported",
            confidence=0.8,
        )
    with pytest.raises(ValidationError, match="confidence"):
        CareerFactInput(
            fact_type="achievement",
            payload={"title": "Imported claim"},
            verification_status="imported",
            source_document_id="10000000-0000-4000-8000-000000000001",
        )


def test_preferences_capture_constraints_and_reject_contradictions():
    preferences = CareerPreferences.model_validate(
        {
            "target_roles": ["Staff Engineer"],
            "target_industries": ["Privacy software"],
            "preferred_work_modes": ["hybrid", "remote"],
            "contract_types": ["permanent"],
            "salary": {"currency": "CHF", "minimum": 150000, "period": "year"},
            "relocation": "within_country",
            "travel_max_percent": 20,
            "notice_period_days": 60,
            "company_values": ["Autonomy", "Sustainability"],
            "excluded_industries": ["Gambling"],
        }
    )
    assert preferences.target_roles == ["Staff Engineer"]
    assert preferences.salary.currency == "CHF"
    with pytest.raises(ValidationError, match="remote_only"):
        CareerPreferences.model_validate(
            {"remote_only": True, "preferred_work_modes": ["onsite"]}
        )


def test_profile_rejects_cross_fact_self_evidence():
    fact_id = "10000000-0000-4000-8000-000000000001"
    payload = {
        "expected_revision": 0,
        "display_name": "Mira",
        "facts": [
            {
                "id": fact_id,
                "fact_type": "skill",
                "payload": {"name": "Python", "evidence_fact_ids": [fact_id]},
            }
        ],
    }
    with pytest.raises(ValidationError, match="cannot reference itself"):
        CareerProfileWrite.model_validate(deepcopy(payload))
