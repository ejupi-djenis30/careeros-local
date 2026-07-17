from datetime import date

import pytest
from pydantic import ValidationError

from backend.career.schemas import CareerFactInput


def test_experience_end_date_cannot_precede_start_date():
    with pytest.raises(ValidationError, match="end_date"):
        CareerFactInput(
            fact_type="experience",
            payload={
                "role": "Engineer",
                "organization": "Example",
                "start_date": date(2025, 1, 1),
                "end_date": date(2024, 1, 1),
            },
        )


def test_language_fact_uses_cefr_or_native_level():
    fact = CareerFactInput(
        fact_type="language",
        payload={"language": "Italian", "level": "native"},
    )
    assert fact.payload["level"] == "native"

    with pytest.raises(ValidationError, match="level"):
        CareerFactInput(
            fact_type="language",
            payload={"language": "German", "level": "fluent-ish"},
        )


def test_external_profile_links_reject_unsafe_schemes():
    with pytest.raises(ValidationError, match="url"):
        CareerFactInput(
            fact_type="link",
            payload={"label": "Portfolio", "url": "javascript:alert(1)"},
        )
