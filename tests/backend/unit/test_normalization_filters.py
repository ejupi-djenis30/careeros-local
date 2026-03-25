"""Unit tests for normalization-based profile matching.

Covers:
- SearchService._compute_profile_norm_fingerprint()
- SearchService._passes_normalization_filters()
- SearchService._normalize_user_profile()
- LLMService.normalize_user_profile()
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from backend.services.search_service import SearchService
from backend.services.llm_service import LLMService


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def service():
    return SearchService(job_repo=MagicMock(), profile_repo=MagicMock())


@pytest.fixture
def llm():
    return LLMService()


# ─── _compute_profile_norm_fingerprint ──────────────────────────────────────

class TestComputeProfileNormFingerprint:
    def test_reproducible(self, service):
        fp1 = service._compute_profile_norm_fingerprint("cv text", "developer role", "remote only")
        fp2 = service._compute_profile_norm_fingerprint("cv text", "developer role", "remote only")
        assert fp1 == fp2

    def test_different_inputs_produce_different_hashes(self, service):
        fp1 = service._compute_profile_norm_fingerprint("CV A", "role A", "")
        fp2 = service._compute_profile_norm_fingerprint("CV B", "role A", "")
        assert fp1 != fp2

    def test_empty_inputs_produce_valid_hash(self, service):
        fp = service._compute_profile_norm_fingerprint("", "", "")
        assert isinstance(fp, str)
        assert len(fp) == 64  # SHA-256 hex

    def test_none_inputs_fall_back_to_empty(self, service):
        fp_none = service._compute_profile_norm_fingerprint(None, None, None)
        fp_empty = service._compute_profile_norm_fingerprint("", "", "")
        assert fp_none == fp_empty

    def test_magicmock_inputs_are_coerced_to_string(self, service):
        """MagicMock objects must be str()-coerced, not left raw (prevents JSON error)."""
        mock_val = MagicMock()
        fp = service._compute_profile_norm_fingerprint(mock_val, mock_val, mock_val)
        assert isinstance(fp, str)
        assert len(fp) == 64


# ─── _passes_normalization_filters ──────────────────────────────────────────

class TestPassesNormalizationFilters:
    """Test each of the 4 filter checks independently."""

    # ── 1. Domain ────────────────────────────────────────────────────────────

    def test_domain_both_general_passes(self, service):
        ok, _ = service._passes_normalization_filters(
            {"domain": "general"}, {"domain": "general"}
        )
        assert ok

    def test_domain_same_non_general_passes(self, service):
        ok, _ = service._passes_normalization_filters(
            {"domain": "it"}, {"domain": "it"}
        )
        assert ok

    def test_domain_mismatch_rejected(self, service):
        ok, reason = service._passes_normalization_filters(
            {"domain": "it"}, {"domain": "finance"}
        )
        assert not ok
        assert reason == "norm_domain_mismatch"

    def test_domain_user_general_skips_check(self, service):
        """When the user is 'general', any job domain should pass."""
        ok, _ = service._passes_normalization_filters(
            {"domain": "finance"}, {"domain": "general"}
        )
        assert ok

    def test_domain_job_general_skips_check(self, service):
        """When the job is 'general', any user domain should pass."""
        ok, _ = service._passes_normalization_filters(
            {"domain": "general"}, {"domain": "finance"}
        )
        assert ok

    def test_domain_missing_on_job_passes(self, service):
        ok, _ = service._passes_normalization_filters(
            {}, {"domain": "it"}
        )
        assert ok

    def test_domain_missing_on_profile_passes(self, service):
        ok, _ = service._passes_normalization_filters(
            {"domain": "it"}, {}
        )
        assert ok

    # ── 2. Seniority ─────────────────────────────────────────────────────────

    def test_seniority_junior_vs_senior_overqualified(self, service):
        """junior user + senior job with high exp floor → rejected."""
        job_norm = {"seniority": "senior", "experience_min_years": 8}
        profile_norm = {"seniority": "junior", "experience_years": 1}
        ok, reason = service._passes_normalization_filters(job_norm, profile_norm)
        assert not ok
        assert reason == "norm_seniority_overqualified"

    def test_seniority_junior_vs_senior_within_tolerance(self, service):
        """junior user + senior job but exp floor within tolerance → passes."""
        job_norm = {"seniority": "senior", "experience_min_years": 3}
        profile_norm = {"seniority": "junior", "experience_years": 2}
        # tolerance=2 → 3 <= 2+2=4, so passes
        with patch("backend.services.search_service.settings") as mock_settings:
            mock_settings.SEARCH_NORMALIZATION_EXPERIENCE_TOLERANCE = 2
            mock_settings.SEARCH_ENABLE_NORMALIZATION_MATCHING = True
            ok, _ = service._passes_normalization_filters(job_norm, profile_norm)
        assert ok

    def test_seniority_junior_vs_senior_no_job_exp_floor_passes(self, service):
        """junior user + senior job label but no exp_min → benefit of doubt."""
        job_norm = {"seniority": "senior"}
        profile_norm = {"seniority": "junior", "experience_years": 1}
        ok, _ = service._passes_normalization_filters(job_norm, profile_norm)
        assert ok

    def test_seniority_senior_vs_junior_underqualified(self, service):
        """senior user (10 yrs) + junior-capped job (max 2 yrs) → rejected."""
        job_norm = {"seniority": "junior", "experience_max_years": 2}
        profile_norm = {"seniority": "senior", "experience_years": 10}
        ok, reason = service._passes_normalization_filters(job_norm, profile_norm)
        assert not ok
        assert reason == "norm_seniority_underqualified"

    def test_seniority_senior_vs_junior_no_exp_cap_passes(self, service):
        """senior user + junior job label but no experience_max_years → passes."""
        job_norm = {"seniority": "junior"}
        profile_norm = {"seniority": "senior", "experience_years": 10}
        ok, _ = service._passes_normalization_filters(job_norm, profile_norm)
        assert ok

    def test_seniority_mid_vs_senior_passes(self, service):
        """mid user + senior job → not covered by the junior/senior seniority check."""
        ok, _ = service._passes_normalization_filters(
            {"seniority": "senior", "experience_min_years": 10},
            {"seniority": "mid", "experience_years": 3},
        )
        # the qualification/seniority check only fires for junior↔senior pairs
        # (experience_floor may reject, but seniority sub-check shouldn't)
        # Here exp floor: 10 > 3+2=5 → rejected by experience floor, not seniority
        ok2, reason = service._passes_normalization_filters(
            {"seniority": "senior", "experience_min_years": 4},
            {"seniority": "mid", "experience_years": 3},
        )
        assert ok2  # 4 <= 3+2=5 → passes all checks

    def test_seniority_missing_passes(self, service):
        ok, _ = service._passes_normalization_filters({}, {})
        assert ok

    # ── 3. Qualification level ────────────────────────────────────────────────

    def test_qualification_job_requires_phd_user_has_bachelor_rejected(self, service):
        """bachelor (rank 2) vs phd job (rank 4): 4 > 2+1=3 → rejected."""
        ok, reason = service._passes_normalization_filters(
            {"qualification_level": "phd"},
            {"qualification_level": "bachelor"},
        )
        assert not ok
        assert reason == "norm_qualification_mismatch"

    def test_qualification_job_requires_master_user_has_bachelor_passes(self, service):
        """bachelor (rank 2) vs master (rank 3): 3 == 2+1 → passes."""
        ok, _ = service._passes_normalization_filters(
            {"qualification_level": "master"},
            {"qualification_level": "bachelor"},
        )
        assert ok

    def test_qualification_one_step_above_passes(self, service):
        """vocational (rank 1) vs bachelor (rank 2): 2 == 1+1 → passes."""
        ok, _ = service._passes_normalization_filters(
            {"qualification_level": "bachelor"},
            {"qualification_level": "vocational"},
        )
        assert ok

    def test_qualification_user_none_vs_bachelor_rejected(self, service):
        """none (rank 0) vs bachelor (rank 2): 2 > 0+1=1 → rejected."""
        ok, reason = service._passes_normalization_filters(
            {"qualification_level": "bachelor"},
            {"qualification_level": "none"},
        )
        assert not ok
        assert reason == "norm_qualification_mismatch"

    def test_qualification_missing_on_job_passes(self, service):
        ok, _ = service._passes_normalization_filters(
            {}, {"qualification_level": "bachelor"}
        )
        assert ok

    def test_qualification_missing_on_profile_passes(self, service):
        ok, _ = service._passes_normalization_filters(
            {"qualification_level": "master"}, {}
        )
        assert ok

    def test_qualification_unknown_string_passes(self, service):
        """Unknown qualification strings get rank -1 and are skipped."""
        ok, _ = service._passes_normalization_filters(
            {"qualification_level": "secret_degree"},
            {"qualification_level": "bachelor"},
        )
        assert ok

    # ── 4. Experience floor ───────────────────────────────────────────────────

    def test_experience_floor_exceeds_tolerance_rejected(self, service):
        """job_exp_min=7, user_exp=2, tolerance=2 → 7 > 4 → rejected."""
        ok, reason = service._passes_normalization_filters(
            {"experience_min_years": 7},
            {"experience_years": 2},
        )
        assert not ok
        assert reason == "norm_experience_floor"

    def test_experience_floor_exactly_at_tolerance_passes(self, service):
        """job_exp_min=4, user_exp=2, tolerance=2 → 4 == 4 → passes."""
        ok, _ = service._passes_normalization_filters(
            {"experience_min_years": 4},
            {"experience_years": 2},
        )
        assert ok

    def test_experience_floor_within_tolerance_passes(self, service):
        ok, _ = service._passes_normalization_filters(
            {"experience_min_years": 3},
            {"experience_years": 2},
        )
        assert ok

    def test_experience_floor_job_exp_min_none_passes(self, service):
        ok, _ = service._passes_normalization_filters(
            {},
            {"experience_years": 2},
        )
        assert ok

    def test_experience_floor_user_exp_none_passes(self, service):
        ok, _ = service._passes_normalization_filters(
            {"experience_min_years": 10},
            {},
        )
        assert ok

    def test_experience_floor_both_none_passes(self, service):
        ok, _ = service._passes_normalization_filters({}, {})
        assert ok

    # ── Combined happy path ───────────────────────────────────────────────────

    def test_all_fields_matching_passes(self, service):
        job_norm = {
            "domain": "it",
            "seniority": "mid",
            "qualification_level": "bachelor",
            "experience_min_years": 3,
        }
        profile_norm = {
            "domain": "it",
            "seniority": "mid",
            "qualification_level": "master",
            "experience_years": 5,
        }
        ok, reason = service._passes_normalization_filters(job_norm, profile_norm)
        assert ok
        assert reason == "ok"


# ─── _normalize_user_profile ────────────────────────────────────────────────

@pytest.mark.asyncio
class TestNormalizeUserProfile:
    async def test_returns_empty_when_no_cv_and_no_role(self, service):
        profile = MagicMock()
        profile_dict = {"cv_content": "", "role_description": ""}
        result = await service._normalize_user_profile(1, profile, profile_dict)
        assert result == {}

    async def test_cache_hit_returns_cached_data(self, service):
        """When fingerprint matches and status=normalized, skip LLM and return cached fields."""
        cv = "Long CV content"
        role = "Senior developer"
        fp = service._compute_profile_norm_fingerprint(cv, role, "")
        profile = MagicMock()
        profile.profile_normalization_status = "normalized"
        profile.profile_normalization_fingerprint = fp
        profile.profile_normalized_seniority = "senior"
        profile.profile_normalized_domain = "it"
        profile.profile_normalized_role_family = "Software Engineer"
        profile.profile_normalized_qualification_level = "bachelor"
        profile.profile_normalized_experience_years = 8
        profile.profile_normalized_languages = [{"code": "en", "level": "C2"}]
        profile.profile_normalized_skills = ["Python", "FastAPI"]
        profile_dict = {"cv_content": cv, "role_description": role}

        with patch("backend.services.search_service.llm_service") as mock_llm:
            result = await service._normalize_user_profile(1, profile, profile_dict)

        mock_llm.normalize_user_profile.assert_not_called()
        assert result["seniority"] == "senior"
        assert result["domain"] == "it"
        assert result["experience_years"] == 8

    async def test_cache_miss_calls_llm_and_persists(self, service):
        """When fingerprint does not match, call LLM and persist result."""
        profile = MagicMock()
        profile.profile_normalization_status = "pending"
        profile.profile_normalization_fingerprint = "old_fp"
        profile_dict = {"cv_content": "My CV text", "role_description": "Python developer"}

        normalized_result = {
            "seniority": "mid", "domain": "it", "role_family": "Backend Dev",
            "qualification_level": "bachelor", "experience_years": 4,
            "languages": [], "skills": ["Python"], "confidence": 0.9,
        }

        with patch("backend.services.search_service.llm_service") as mock_llm:
            mock_llm.normalize_user_profile = AsyncMock(return_value=normalized_result)
            result = await service._normalize_user_profile(1, profile, profile_dict)

        mock_llm.normalize_user_profile.assert_called_once()
        service.profile_repo.update_normalized_profile.assert_called_once()
        assert result["seniority"] == "mid"

    async def test_force_flag_bypasses_cache(self, service):
        """force=True should skip the cache even if fingerprint matches."""
        cv = "My CV"
        role = "Developer"
        fp = service._compute_profile_norm_fingerprint(cv, role, "")
        profile = MagicMock()
        profile.profile_normalization_status = "normalized"
        profile.profile_normalization_fingerprint = fp
        profile_dict = {"cv_content": cv, "role_description": role}
        normalized_result = {"seniority": "junior", "domain": "it", "role_family": "Dev",
                             "qualification_level": "none", "experience_years": 1,
                             "languages": [], "skills": [], "confidence": 0.7}

        with patch("backend.services.search_service.llm_service") as mock_llm:
            mock_llm.normalize_user_profile = AsyncMock(return_value=normalized_result)
            result = await service._normalize_user_profile(1, profile, profile_dict, force=True)

        mock_llm.normalize_user_profile.assert_called_once()

    async def test_llm_failure_returns_empty_dict(self, service):
        """Any exception from LLM must be caught and return {} (non-fatal)."""
        profile = MagicMock()
        profile.profile_normalization_status = "pending"
        profile_dict = {"cv_content": "Some CV", "role_description": "Some role"}

        with patch("backend.services.search_service.llm_service") as mock_llm:
            mock_llm.normalize_user_profile = AsyncMock(side_effect=Exception("LLM failure"))
            result = await service._normalize_user_profile(1, profile, profile_dict)

        assert result == {}


# ─── LLMService.normalize_user_profile ──────────────────────────────────────

@pytest.mark.asyncio
class TestLLMServiceNormalizeUserProfile:
    async def test_returns_empty_dict_on_non_dict_llm_response(self, llm):
        """If LLM returns non-dict (e.g. None, list), should return {}."""
        with patch.object(llm, "_get_provider") as mock_get_prov:
            mock_provider = AsyncMock()
            mock_provider.generate_json_async = AsyncMock(return_value=None)
            mock_get_prov.return_value = mock_provider
            result = await llm.normalize_user_profile("cv text", "developer", "")
        assert result == {}

    async def test_valid_response_passes_through(self, llm):
        """Valid LLM dict response is validated and returned with normalized fields."""
        valid_llm_output = {
            "seniority": "mid",
            "domain": "it",
            "role_family": "Backend Engineer",
            "qualification_level": "bachelor",
            "experience_years": 5,
            "languages": [{"code": "en", "level": "C2"}],
            "skills": ["Python", "FastAPI"],
            "confidence": 0.9,
        }
        with patch.object(llm, "_get_provider") as mock_get_prov:
            mock_provider = AsyncMock()
            mock_provider.generate_json_async = AsyncMock(return_value=valid_llm_output)
            mock_get_prov.return_value = mock_provider
            result = await llm.normalize_user_profile("cv text", "Python developer", "")

        assert result["seniority"] == "mid"
        assert result["domain"] == "it"
        assert result["experience_years"] == 5
        assert result["confidence"] == 0.9

    async def test_invalid_seniority_coerced_to_none(self, llm):
        """Unknown seniority value must be coerced to None."""
        llm_output = {
            "seniority": "executive",  # not in allowlist
            "domain": "it",
            "role_family": "Manager",
            "qualification_level": "master",
            "experience_years": 10,
            "languages": [],
            "skills": [],
            "confidence": 0.7,
        }
        with patch.object(llm, "_get_provider") as mock_get_prov:
            mock_provider = AsyncMock()
            mock_provider.generate_json_async = AsyncMock(return_value=llm_output)
            mock_get_prov.return_value = mock_provider
            result = await llm.normalize_user_profile("cv text", "executive role", "")

        assert result["seniority"] is None

    async def test_invalid_qualification_level_coerced_to_none(self, llm):
        """Unknown qualification level must be coerced to None."""
        llm_output = {
            "seniority": "mid",
            "domain": "it",
            "role_family": "Engineer",
            "qualification_level": "diploma",  # not in allowlist
            "experience_years": 3,
            "languages": [],
            "skills": [],
            "confidence": 0.6,
        }
        with patch.object(llm, "_get_provider") as mock_get_prov:
            mock_provider = AsyncMock()
            mock_provider.generate_json_async = AsyncMock(return_value=llm_output)
            mock_get_prov.return_value = mock_provider
            result = await llm.normalize_user_profile("cv", "developer", "")

        assert result["qualification_level"] is None

    async def test_negative_experience_clamped_to_zero(self, llm):
        """Negative experience years must be clamped to 0."""
        llm_output = {
            "seniority": "junior",
            "domain": "it",
            "role_family": "Dev",
            "qualification_level": "none",
            "experience_years": -3,  # invalid
            "languages": [],
            "skills": [],
            "confidence": 0.5,
        }
        with patch.object(llm, "_get_provider") as mock_get_prov:
            mock_provider = AsyncMock()
            mock_provider.generate_json_async = AsyncMock(return_value=llm_output)
            mock_get_prov.return_value = mock_provider
            result = await llm.normalize_user_profile("cv", "junior dev", "")

        assert result["experience_years"] == 0

    async def test_confidence_clamped_to_range(self, llm):
        """Confidence outside [0, 1] must be clamped."""
        llm_output = {
            "seniority": "mid", "domain": "it", "role_family": "Dev",
            "qualification_level": "bachelor", "experience_years": 3,
            "languages": [], "skills": [], "confidence": 5.0,  # out of range
        }
        with patch.object(llm, "_get_provider") as mock_get_prov:
            mock_provider = AsyncMock()
            mock_provider.generate_json_async = AsyncMock(return_value=llm_output)
            mock_get_prov.return_value = mock_provider
            result = await llm.normalize_user_profile("cv", "developer", "")

        assert result["confidence"] == 1.0
