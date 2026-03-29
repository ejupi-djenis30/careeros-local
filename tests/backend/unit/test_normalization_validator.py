"""Unit tests for backend/services/search/normalization_validator.py.

Covers:
- validate_normalized_job: valid values pass through, hallucinations remapped,
  invalid values nulled, confidence clamped, int fields coerced/clamped
- validate_normalized_batch: batch wrapper + indices_needing_review tracking
"""

from backend.services.search.normalization_validator import (
    validate_normalized_batch,
    validate_normalized_job,
)

# ─── validate_normalized_job ──────────────────────────────────────────────────


class TestValidateNormalizedJob:
    def test_valid_values_pass_through_unchanged(self):
        raw = {
            "domain": "it",
            "seniority": "senior",
            "role_type": "technical",
            "employment_mode": "remote",
            "contract_type": "permanent",
            "qualification_level": "bachelor",
            "entry_barrier": "medium",
            "confidence": 0.9,
        }
        corrected, fields = validate_normalized_job(raw)
        assert fields == []
        assert corrected["domain"] == "it"
        assert corrected["seniority"] == "senior"

    def test_valid_value_casing_normalised(self):
        raw = {"seniority": "Senior"}  # uppercase — should be lowercased
        corrected, fields = validate_normalized_job(raw)
        assert corrected["seniority"] == "senior"
        # Casing fix: not counted as a corrected field
        assert "seniority" not in fields

    def test_hallucination_seniority_remapped(self):
        raw = {"seniority": "entry-level"}
        corrected, fields = validate_normalized_job(raw)
        assert corrected["seniority"] == "junior"
        assert "seniority" in fields

    def test_hallucination_domain_remapped(self):
        raw = {"domain": "software development"}
        corrected, fields = validate_normalized_job(raw)
        assert corrected["domain"] == "it"
        assert "domain" in fields

    def test_hallucination_employment_mode_remapped(self):
        raw = {"employment_mode": "home office"}
        corrected, fields = validate_normalized_job(raw)
        assert corrected["employment_mode"] == "remote"
        assert "employment_mode" in fields

    def test_hallucination_contract_type_remapped(self):
        raw = {"contract_type": "fixed-term"}
        corrected, fields = validate_normalized_job(raw)
        assert corrected["contract_type"] == "temporary"
        assert "contract_type" in fields

    def test_hallucination_qualification_level_remapped(self):
        raw = {"qualification_level": "bachelor's"}
        corrected, fields = validate_normalized_job(raw)
        assert corrected["qualification_level"] == "bachelor"
        assert "qualification_level" in fields

    def test_hallucination_entry_barrier_remapped(self):
        raw = {"entry_barrier": "moderate"}
        corrected, fields = validate_normalized_job(raw)
        assert corrected["entry_barrier"] == "medium"
        assert "entry_barrier" in fields

    def test_unresolvable_value_nulled(self):
        raw = {"seniority": "totally_invalid_garbage"}
        corrected, fields = validate_normalized_job(raw)
        assert corrected["seniority"] is None
        assert "seniority" in fields

    def test_none_field_left_alone(self):
        raw = {"seniority": None, "domain": None}
        corrected, fields = validate_normalized_job(raw)
        assert corrected["seniority"] is None
        assert corrected["domain"] is None
        assert fields == []

    def test_confidence_clamped_above_one(self):
        raw = {"confidence": 1.5}
        corrected, fields = validate_normalized_job(raw)
        assert corrected["confidence"] == 1.0

    def test_confidence_clamped_below_zero(self):
        raw = {"confidence": -0.5}
        corrected, fields = validate_normalized_job(raw)
        assert corrected["confidence"] == 0.0

    def test_confidence_invalid_type_set_to_zero(self):
        raw = {"confidence": "not-a-number"}
        corrected, fields = validate_normalized_job(raw)
        assert corrected["confidence"] == 0.0
        assert "confidence" in fields

    def test_negative_integer_field_clamped_to_zero(self):
        raw = {"experience_min_years": -3}
        corrected, fields = validate_normalized_job(raw)
        assert corrected["experience_min_years"] == 0
        assert "experience_min_years" in fields

    def test_invalid_integer_field_nulled(self):
        raw = {"salary_max_chf": "not-an-int"}
        corrected, fields = validate_normalized_job(raw)
        assert corrected["salary_max_chf"] is None
        assert "salary_max_chf" in fields

    def test_career_changer_friendly_string_true_coerced(self):
        raw = {"career_changer_friendly": "true"}
        corrected, _ = validate_normalized_job(raw)
        assert corrected["career_changer_friendly"] is True

    def test_career_changer_friendly_string_false_coerced(self):
        raw = {"career_changer_friendly": "false"}
        corrected, _ = validate_normalized_job(raw)
        assert corrected["career_changer_friendly"] is False

    def test_career_changer_friendly_int_coerced(self):
        raw = {"career_changer_friendly": 1}
        corrected, _ = validate_normalized_job(raw)
        assert corrected["career_changer_friendly"] is True

    def test_original_dict_not_mutated(self):
        raw = {"seniority": "entry-level", "confidence": 2.0}
        original_seniority = raw["seniority"]
        validate_normalized_job(raw)
        assert raw["seniority"] == original_seniority  # raw unchanged

    def test_extra_keys_preserved(self):
        raw = {"custom_key": "some_value", "seniority": "junior"}
        corrected, _ = validate_normalized_job(raw)
        assert corrected["custom_key"] == "some_value"

    def test_role_type_remapped(self):
        raw = {"role_type": "physical"}
        corrected, fields = validate_normalized_job(raw)
        assert corrected["role_type"] == "manual"
        assert "role_type" in fields


# ─── validate_normalized_batch ────────────────────────────────────────────────


class TestValidateNormalizedBatch:
    def test_batch_returns_corrected_rows(self):
        rows = [
            {"seniority": "junior", "domain": "it"},
            {"seniority": "entry-level", "domain": "software"},
        ]
        corrected_rows, indices = validate_normalized_batch(rows)
        assert len(corrected_rows) == 2
        assert corrected_rows[1]["seniority"] == "junior"
        assert corrected_rows[1]["domain"] == "it"

    def test_batch_indices_needing_review_populated(self):
        rows = [
            {"seniority": "junior"},  # valid → no correction
            {"seniority": "entry-level"},  # hallucination → corrected
        ]
        _, indices = validate_normalized_batch(rows)
        assert 1 in indices
        assert 0 not in indices

    def test_batch_returns_empty_for_empty_input(self):
        rows = []
        corrected_rows, indices = validate_normalized_batch(rows)
        assert corrected_rows == []
        assert indices == []

    def test_batch_all_valid_no_review_indices(self):
        rows = [
            {"seniority": "junior", "domain": "it", "role_type": "technical"},
            {"seniority": "senior", "domain": "finance", "role_type": "managerial"},
        ]
        _, indices = validate_normalized_batch(rows)
        assert indices == []
