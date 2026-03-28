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

    def test_domain_related_domains_passes(self, service):
        ok, _ = service._passes_normalization_filters(
            {"domain": "engineering"}, {"domain": "it"}
        )
        assert ok

    def test_domain_unrelated_domains_rejected(self, service):
        ok, reason = service._passes_normalization_filters(
            {"domain": "medical"}, {"domain": "it"}
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

    def test_seniority_junior_vs_senior_user_exp_none_passes(self, service):
        """If candidate experience is unknown, do not reject by seniority overqualification."""
        job_norm = {"seniority": "senior", "experience_min_years": 8}
        profile_norm = {"seniority": "junior", "experience_years": None}
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

    def test_qualification_job_requires_phd_user_has_bachelor_passes(self, service):
        """bachelor (rank 2) vs phd job (rank 4): 4 == 2+2 → passes."""
        ok, _ = service._passes_normalization_filters(
            {"qualification_level": "phd"},
            {"qualification_level": "bachelor"},
        )
        assert ok

    def test_qualification_job_requires_phd_user_has_vocational_rejected(self, service):
        """vocational (rank 1) vs phd job (rank 4): 4 > 1+2=3 → rejected."""
        ok, reason = service._passes_normalization_filters(
            {"qualification_level": "phd"},
            {"qualification_level": "vocational"},
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

    def test_qualification_user_none_vs_bachelor_passes(self, service):
        """none (rank 0) vs bachelor (rank 2): 2 == 0+2 → passes."""
        ok, _ = service._passes_normalization_filters(
            {"qualification_level": "bachelor"},
            {"qualification_level": "none"},
        )
        assert ok

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
        """job_exp_min=7, user_exp=2, tolerance=3 → 7 > 5 → rejected."""
        ok, reason = service._passes_normalization_filters(
            {"experience_min_years": 7},
            {"experience_years": 2},
        )
        assert not ok
        assert reason == "norm_experience_floor"

    def test_experience_floor_exactly_at_tolerance_passes(self, service):
        """job_exp_min=5, user_exp=2, tolerance=3 → 5 == 5 → passes."""
        ok, _ = service._passes_normalization_filters(
            {"experience_min_years": 5},
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
            "languages": [], "skills": ["Python"],
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
                             "languages": [], "skills": []}

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
            mock_provider.generate_json_async_with_timeout = mock_provider.generate_json_async
            mock_provider.model_id = "test/mock-model"
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
            mock_provider.generate_json_async_with_timeout = mock_provider.generate_json_async
            mock_provider.model_id = "test/mock-model"
            mock_get_prov.return_value = mock_provider
            result = await llm.normalize_user_profile("cv text", "Python developer", "")

        assert result["seniority"] == "mid"
        assert result["domain"] == "it"
        assert result["experience_years"] == 5

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
            mock_provider.generate_json_async_with_timeout = mock_provider.generate_json_async
            mock_provider.model_id = "test/mock-model"
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
            mock_provider.generate_json_async_with_timeout = mock_provider.generate_json_async
            mock_provider.model_id = "test/mock-model"
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
            mock_provider.generate_json_async_with_timeout = mock_provider.generate_json_async
            mock_provider.model_id = "test/mock-model"
            mock_get_prov.return_value = mock_provider
            result = await llm.normalize_user_profile("cv", "junior dev", "")

        assert result["experience_years"] == 0


# ─── Intent-aware normalization filter tests ────────────────────────────────

class TestIntentAwareFilters:
    """Tests for the intent-first behavior of _passes_normalization_filters."""

    # ── open_to_unrelated bypasses domain and skills checks ──────────────────

    def test_open_to_unrelated_bypasses_domain_mismatch(self, service):
        """A developer searching manual-labor jobs → domain mismatch must be bypassed."""
        ok, reason = service._passes_normalization_filters(
            {"domain": "logistics", "required_skills": ["forklift", "packing", "warehouse"]},
            {
                "domain": "it", "skills": ["Python", "React", "Docker"],
                "open_to_unrelated": True,
                "intent_domain": "logistics",
                "intent_skills": ["forklift"],
            },
        )
        assert ok, f"Expected pass but got: {reason}"

    def test_open_to_unrelated_bypasses_skills_disjoint(self, service):
        """When open_to_unrelated=True, zero skills overlap must NOT reject the job."""
        ok, reason = service._passes_normalization_filters(
            {"domain": "hospitality", "required_skills": ["cooking", "cleaning", "service"]},
            {
                "domain": "it", "skills": ["Python", "FastAPI", "PostgreSQL"],
                "open_to_unrelated": True,
                "intent_domain": "hospitality",
                "intent_skills": [],
            },
        )
        assert ok, f"Expected pass with open_to_unrelated=True but got: {reason}"

    def test_open_to_unrelated_false_domain_mismatch_still_rejected(self, service):
        """Without open_to_unrelated, domain mismatch should still be rejected."""
        ok, reason = service._passes_normalization_filters(
            {"domain": "medical"},
            {"domain": "it", "open_to_unrelated": False},
        )
        assert not ok
        assert reason == "norm_domain_mismatch"

    # ── intent_domain takes priority over CV domain ──────────────────────────

    def test_intent_domain_overrides_cv_domain(self, service):
        """If CV says 'it' but intent says 'logistics', job in logistics should pass."""
        ok, reason = service._passes_normalization_filters(
            {"domain": "logistics"},
            {
                "domain": "it",
                "intent_domain": "logistics",
                "open_to_unrelated": False,
            },
        )
        assert ok, f"Expected pass using intent_domain but got: {reason}"

    def test_intent_domain_mismatch_is_rejected(self, service):
        """If CV says 'it' but intent says 'logistics', a 'medical' job should still fail."""
        ok, reason = service._passes_normalization_filters(
            {"domain": "medical"},
            {
                "domain": "it",
                "intent_domain": "logistics",
                "open_to_unrelated": False,
            },
        )
        assert not ok
        assert reason == "norm_domain_mismatch"

    def test_intent_domain_fallback_to_cv_domain_when_absent(self, service):
        """If intent_domain is missing, fall back to CV domain (backward compat)."""
        ok, reason = service._passes_normalization_filters(
            {"domain": "it"},
            {"domain": "it"},  # no intent_domain
        )
        assert ok

    # ── intent_skills combined with CV skills for overlap check ─────────────

    def test_intent_skills_pools_with_cv_skills_for_overlap(self, service):
        """Intent skills should be pooled with CV skills for the disjoint check."""
        ok, reason = service._passes_normalization_filters(
            {"domain": "logistics", "required_skills": ["excel", "sap", "logistics"]},
            {
                "domain": "it",
                "skills": ["Python", "React", "Docker"],   # no overlap with job
                "intent_skills": ["excel", "logistics"],   # overlap with job!
                "open_to_unrelated": False,
                "intent_domain": "logistics",
            },
        )
        assert ok, f"Expected pass due to intent_skills overlap but got: {reason}"

    def test_skills_disjoint_still_rejects_when_no_overlap_and_not_manual(self, service):
        """When skills are truly disjoint and no open_to_unrelated, should reject."""
        ok, reason = service._passes_normalization_filters(
            {"domain": "it", "required_skills": ["COBOL", "FORTRAN", "Assembly"]},
            {
                "domain": "it",
                "skills": ["Python", "React", "Docker"],
                "intent_skills": ["TypeScript"],
                "open_to_unrelated": False,
            },
        )
        assert not ok
        assert reason == "norm_skills_disjoint"

    # ── skill aliases (JS ↔ javascript) ─────────────────────────────────────

    def test_skill_alias_js_matches_javascript(self, service):
        """'JS' in job skills and 'javascript' in profile skills → overlap via alias."""
        ok, reason = service._passes_normalization_filters(
            {"domain": "it", "required_skills": ["JS", "Node.js", "CSS"]},
            {"domain": "it", "skills": ["javascript", "html", "css"]},
        )
        assert ok, f"Expected alias match to prevent disjoint rejection but got: {reason}"

    def test_skill_alias_k8s_matches_kubernetes(self, service):
        """'k8s' → 'kubernetes' alias should allow overlap."""
        ok, reason = service._passes_normalization_filters(
            {"domain": "it", "required_skills": ["k8s", "docker", "helm"]},
            {"domain": "it", "skills": ["kubernetes", "docker", "terraform"]},
        )
        assert ok, f"Expected k8s→kubernetes alias but got: {reason}"

    # ── intent_seniority takes priority over CV seniority ────────────────────

    def test_intent_seniority_overrides_cv_seniority(self, service):
        """Senior dev who targets junior positions: intent_seniority=junior, job=junior → pass."""
        ok, reason = service._passes_normalization_filters(
            {"seniority": "junior", "experience_max_years": 2},
            {
                "seniority": "senior",
                "experience_years": 8,
                "intent_seniority": "junior",
            },
        )
        # With intent_seniority=junior and experience_max_years=2, user_exp=8;
        # the underqualified check: 2 < 8-3=5 → rejected by underqualified... UNLESS
        # the intent signals they WANT junior, which means we should pass this.
        # The current logic uses intent_seniority as "effective_seniority" so
        # "junior" checking "junior" job → no check fires → passes.
        assert ok, f"Expected pass when intent_seniority matches job seniority but got: {reason}"

    # ── intent_qualification_level takes priority ─────────────────────────────

    def test_intent_qualification_level_overrides_cv_qualification(self, service):
        """User has 'vocational' CV but targets 'bachelor' jobs via intent."""
        ok, reason = service._passes_normalization_filters(
            {"qualification_level": "master"},
            {
                "qualification_level": "vocational",
                "intent_qualification_level": "bachelor",
            },
        )
        # bachelor (rank 2) vs master (rank 3): 3 <= 2+2=4 → passes
        assert ok, f"Expected pass with intent_qualification_level=bachelor but got: {reason}"

    # ── manual work signals bypass skills check ──────────────────────────────

    def test_manual_intent_keyword_bypasses_skills_check(self, service):
        """If intent_keywords contain 'manual', skills disjoint check is skipped."""
        ok, reason = service._passes_normalization_filters(
            {"domain": "general", "required_skills": ["forklift", "packing", "heavy lifting"]},
            {
                "domain": "it",
                "skills": ["Python", "React", "Docker"],
                "intent_keywords": ["manual", "warehouse"],
                "open_to_unrelated": False,
                "intent_domain": "general",
            },
        )
        assert ok, f"Expected manual keyword to bypass skills check but got: {reason}"


# ─── V2 Advanced Matching Tests ─────────────────────────────────────────────

class TestV2AdvancedMatching:
    """Tests for V2 features: role_type, dealbreakers, transferable skills,
    career_changer_friendly, seniority range, entry_barrier."""

    # ── Role-type matching ───────────────────────────────────────────────────

    def test_role_type_mismatch_rejected(self, service):
        """Developer (technical CV) with intent_role_type=manual should reject a technical job."""
        ok, reason = service._passes_normalization_filters(
            {"domain": "it", "role_type": "technical"},
            {
                "domain": "it",
                "intent_role_type": "manual",
                "open_to_unrelated": False,
                "flexibility": {},
            },
        )
        assert not ok
        assert reason == "norm_role_type_mismatch"

    def test_role_type_same_family_accepted(self, service):
        """manual intent + service job → same family → accepted."""
        ok, reason = service._passes_normalization_filters(
            {"role_type": "service"},
            {
                "intent_role_type": "manual",
                "open_to_unrelated": False,
                "flexibility": {},
            },
        )
        assert ok, f"Expected service job to pass for manual intent but got: {reason}"

    def test_role_type_flexible_domain_bypasses_mismatch(self, service):
        """flexibility.domain=True should bypass role_type mismatch."""
        ok, reason = service._passes_normalization_filters(
            {"role_type": "technical"},
            {
                "intent_role_type": "manual",
                "open_to_unrelated": False,
                "flexibility": {"domain": True},
            },
        )
        assert ok, f"Expected flexible domain to bypass role_type check but got: {reason}"

    def test_role_type_open_to_unrelated_bypasses_mismatch(self, service):
        """open_to_unrelated=True should bypass role_type mismatch."""
        ok, reason = service._passes_normalization_filters(
            {"role_type": "technical"},
            {
                "intent_role_type": "manual",
                "open_to_unrelated": True,
            },
        )
        assert ok, f"Expected open_to_unrelated to bypass role_type check but got: {reason}"

    def test_role_type_both_missing_no_rejection(self, service):
        """If neither intent_role_type nor job role_type is set, check is skipped."""
        ok, reason = service._passes_normalization_filters({}, {})
        assert ok

    def test_role_type_only_intent_set_no_rejection(self, service):
        """If job doesn't have role_type, check is skipped gracefully."""
        ok, _ = service._passes_normalization_filters(
            {},
            {"intent_role_type": "manual"},
        )
        assert ok

    # ── Dealbreaker rejection ────────────────────────────────────────────────

    def test_dealbreaker_matching_hard_blocker_rejected(self, service):
        """Dealbreaker 'night shift' matches hard_blocker → rejected."""
        ok, reason = service._passes_normalization_filters(
            {"hard_blockers": ["mandatory night shift", "weekend availability required"]},
            {"dealbreakers": ["night shift"]},
        )
        assert not ok
        assert reason == "norm_dealbreaker_hit"

    def test_dealbreaker_matching_key_requirement_rejected(self, service):
        """Dealbreaker matching key_requirements → rejected."""
        ok, reason = service._passes_normalization_filters(
            {"key_requirements": ["must have security clearance", "active clearance required"]},
            {"dealbreakers": ["security clearance"]},
        )
        assert not ok
        assert reason == "norm_dealbreaker_hit"

    def test_dealbreaker_no_match_passes(self, service):
        """Dealbreaker not present in job requirements → passes."""
        ok, reason = service._passes_normalization_filters(
            {"hard_blockers": ["fluent German required"], "key_requirements": ["python"]},
            {"dealbreakers": ["night shift", "relocation required"]},
        )
        assert ok, f"Expected no dealbreaker hit but got: {reason}"

    def test_dealbreaker_empty_list_no_rejection(self, service):
        """Empty dealbreakers list → no rejection."""
        ok, _ = service._passes_normalization_filters(
            {"hard_blockers": ["night shift"]},
            {"dealbreakers": []},
        )
        assert ok

    # ── Career changer friendly bypass ──────────────────────────────────────

    def test_career_changer_friendly_bypasses_skills_disjoint(self, service):
        """career_changer_friendly=True → zero skills overlap is acceptable."""
        ok, reason = service._passes_normalization_filters(
            {
                "domain": "logistics",
                "required_skills": ["forklift", "warehouse management", "packing"],
                "career_changer_friendly": True,
            },
            {
                "domain": "logistics",
                "skills": ["Python", "FastAPI", "PostgreSQL"],  # no overlap
                "intent_skills": [],
                "transferable_skills": [],
                "open_to_unrelated": False,
            },
        )
        assert ok, f"Expected career_changer_friendly to bypass skills check but got: {reason}"

    def test_career_changer_not_friendly_skills_disjoint_rejected(self, service):
        """career_changer_friendly=False and no manual intent → skills disjoint rejects."""
        ok, reason = service._passes_normalization_filters(
            {
                "domain": "it",
                "required_skills": ["COBOL", "FORTRAN", "Assembly"],
                "career_changer_friendly": False,
            },
            {
                "domain": "it",
                "skills": ["Python", "React", "Docker"],
                "intent_skills": [],
                "transferable_skills": [],
                "open_to_unrelated": False,
            },
        )
        assert not ok
        assert reason == "norm_skills_disjoint"

    # ── Transferable skills extend overlap pool ──────────────────────────────

    def test_transferable_skills_allow_overlap(self, service):
        """Developer with transferable 'project management' skill
        overlaps with project-management job → passes skills check."""
        ok, reason = service._passes_normalization_filters(
            {
                "domain": "administration",
                "required_skills": ["project management", "excel", "reporting"],
            },
            {
                "domain": "administration",
                "skills": ["Python", "FastAPI", "Docker"],          # no direct overlap
                "intent_skills": [],
                "transferable_skills": ["project management", "excel", "communication"],
                "open_to_unrelated": False,
            },
        )
        assert ok, f"Expected transferable skills to close overlap gap but got: {reason}"

    # ── Seniority range ──────────────────────────────────────────────────────

    def test_seniority_range_job_within_range_passes(self, service):
        """intent_seniority_min=junior, max=mid — mid job → passes."""
        ok, reason = service._passes_normalization_filters(
            {"seniority": "mid", "experience_min_years": 2},
            {
                "seniority": "junior",
                "experience_years": 3,
                "intent_seniority_min": "junior",
                "intent_seniority_max": "mid",
            },
        )
        assert ok, f"Expected mid job to be within junior-mid range but got: {reason}"

    def test_seniority_range_job_exceeds_max_rejected(self, service):
        """intent max=mid, senior job with high exp_min → rejected."""
        ok, reason = service._passes_normalization_filters(
            {"seniority": "senior", "experience_min_years": 8},
            {
                "seniority": "junior",
                "experience_years": 2,
                "intent_seniority_min": "junior",
                "intent_seniority_max": "mid",
            },
        )
        assert not ok
        assert reason == "norm_seniority_overqualified"

    def test_seniority_range_job_exceeds_max_but_exp_ok_passes(self, service):
        """intent max=mid, senior job but exp_min within tolerance → passes."""
        ok, reason = service._passes_normalization_filters(
            {"seniority": "senior", "experience_min_years": 3},
            {
                "seniority": "junior",
                "experience_years": 2,
                "intent_seniority_min": "junior",
                "intent_seniority_max": "mid",
            },
        )
        # 3 <= 2+2=4 → passes
        assert ok, f"Expected exp tolerance to allow senior job but got: {reason}"

    # ── Entry barrier gate ───────────────────────────────────────────────────

    def test_entry_barrier_high_open_to_unrelated_rejected(self, service):
        """Cross-domain explorer (open_to_unrelated) + high barrier job → rejected."""
        ok, reason = service._passes_normalization_filters(
            {"entry_barrier": "high", "domain": "medical"},
            {
                "domain": "it",
                "open_to_unrelated": True,
                "intent_domain": "medical",
            },
        )
        assert not ok
        assert reason == "norm_entry_barrier_high"

    def test_entry_barrier_medium_open_to_unrelated_passes(self, service):
        """Cross-domain explorer + medium barrier job → passes (only high is blocked)."""
        ok, reason = service._passes_normalization_filters(
            {"entry_barrier": "medium", "domain": "logistics"},
            {
                "domain": "it",
                "open_to_unrelated": True,
                "intent_domain": "logistics",
            },
        )
        assert ok, f"Expected medium barrier to pass for open_to_unrelated but got: {reason}"

    def test_entry_barrier_high_not_open_to_unrelated_passes(self, service):
        """High barrier job but NOT open_to_unrelated → entry barrier gate not triggered."""
        ok, reason = service._passes_normalization_filters(
            {"entry_barrier": "high", "domain": "it"},
            {
                "domain": "it",
                "open_to_unrelated": False,
                "qualification_level": "bachelor",  # may still pass via qual check
            },
        )
        # Entry barrier doesn't block; qualification check may or may not block
        assert reason != "norm_entry_barrier_high"

    # ── Qualification bypass for career_changer_friendly jobs ───────────────

    def test_career_changer_job_skips_qualification_check(self, service):
        """career_changer_friendly=True → qualification mismatch is not applied."""
        ok, reason = service._passes_normalization_filters(
            {
                "qualification_level": "master",  # would normally be too high for 'none'
                "career_changer_friendly": True,
            },
            {"qualification_level": "none"},
        )
        assert ok, f"Expected career_changer_friendly to skip qual check but got: {reason}"

    def test_entry_barrier_none_job_skips_qualification_check(self, service):
        """entry_barrier=none → qualification mismatch not applied."""
        ok, reason = service._passes_normalization_filters(
            {
                "qualification_level": "phd",  # very high rank
                "entry_barrier": "none",
            },
            {"qualification_level": "none"},
        )
        assert ok, f"Expected entry_barrier=none to skip qual check but got: {reason}"


