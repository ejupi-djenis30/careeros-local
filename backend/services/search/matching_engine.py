from __future__ import annotations

from typing import Any, Dict, Optional

from backend.core.config import settings
from backend.services.search.listing_utils import (
    _word_bounded_substring,
    coerce_int,
    compute_prescore,
    normalized_text_token,
    semantic_skills_score,
)


class SearchNormalizationFilterEngine:
    """Deterministic normalized job-vs-profile matching rules.

    SearchService uses this engine as a collaborator so the search pipeline
    orchestration stays focused on stage execution while the matching rules are
    isolated and unit-testable.
    """

    _QUALIFICATION_RANK: Dict[str, int] = {
        "none": 0,
        "vocational": 1,
        "bachelor": 2,
        "master": 3,
        "phd": 4,
    }

    _RELATED_DOMAIN_GROUPS: tuple[frozenset[str], ...] = (
        frozenset({"it", "engineering"}),
        frozenset({"it", "consulting"}),
        frozenset({"it", "marketing"}),
        frozenset({"finance", "administration"}),
        frozenset({"finance", "consulting"}),
        frozenset({"medical", "pharma"}),
        frozenset({"medical", "education"}),
        frozenset({"sales", "marketing"}),
        frozenset({"sales", "hospitality"}),
        frozenset({"engineering", "construction"}),
        frozenset({"logistics", "construction"}),
        frozenset({"logistics", "general"}),
        frozenset({"hospitality", "general"}),
        frozenset({"administration", "legal"}),
        frozenset({"education", "consulting"}),
    )

    _SENIORITY_ORDER: Dict[str, int] = {
        "intern": 0,
        "trainee": 0,
        "entry": 0,
        "junior": 1,
        "mid": 2,
        "senior": 3,
        "lead": 4,
        "director": 5,
    }

    _ROLE_TYPE_FAMILIES: tuple[frozenset[str], ...] = (
        frozenset({"manual", "service"}),
        frozenset({"technical", "professional"}),
        frozenset({"administrative", "managerial"}),
        frozenset({"creative"}),
    )

    def domains_are_related(self, domain_a: str, domain_b: str) -> bool:
        """Return True when two domains are in the same related group."""
        try:
            from backend.data.domain_affinity import domains_are_related  # type: ignore

            return domains_are_related(domain_a, domain_b, threshold=0.40)
        except Exception:
            for group in self._RELATED_DOMAIN_GROUPS:
                if domain_a in group and domain_b in group:
                    return True
            return False

    def domain_affinity_score(self, domain_a: str, domain_b: str) -> float:
        """Return a continuous 0.0-1.0 affinity score between two domains."""
        try:
            from backend.data.domain_affinity import get_domain_affinity  # type: ignore

            return get_domain_affinity(domain_a, domain_b)
        except Exception:
            if domain_a == domain_b:
                return 1.0
            return 0.5 if self.domains_are_related(domain_a, domain_b) else 0.0

    def domain_distance(self, domain_a: str, domain_b: str) -> int:
        """Return 0 (same), 1 (related), or 2 (unrelated)."""
        if domain_a == domain_b:
            return 0
        if self.domains_are_related(domain_a, domain_b):
            return 1
        return 2

    def role_types_compatible(self, intent_role_type: str, job_role_type: str) -> bool:
        """Return True when two role types belong to the same family."""
        if intent_role_type == job_role_type:
            return True
        for family in self._ROLE_TYPE_FAMILIES:
            if intent_role_type in family and job_role_type in family:
                return True
        return False

    def passes_normalization_filters(
        self,
        job_norm: Dict[str, Any],
        profile_norm: Dict[str, Any],
        preference_signals: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        """Intent-aware deterministic field-vs-field match between normalized job and candidate."""
        raw_confidence = job_norm.get("confidence")
        low_confidence = False
        if raw_confidence is not None:
            try:
                if float(raw_confidence) < 0.7:
                    low_confidence = True
            except (TypeError, ValueError):
                pass

        open_to_unrelated = bool(profile_norm.get("open_to_unrelated", False))
        flexibility = profile_norm.get("flexibility") or {}

        dealbreakers = [
            str(dealbreaker).lower().strip()
            for dealbreaker in (profile_norm.get("dealbreakers") or [])
            if dealbreaker
        ]
        if dealbreakers:
            hard_blockers_raw = list(job_norm.get("hard_blockers") or []) + list(
                job_norm.get("key_requirements") or []
            )
            hard_blockers = [
                normalized_text_token(str(blocker)) for blocker in hard_blockers_raw if blocker
            ]
            for dealbreaker in dealbreakers:
                dealbreaker_token = normalized_text_token(dealbreaker)
                if dealbreaker_token and any(
                    _word_bounded_substring(dealbreaker_token, hard_blocker)
                    or _word_bounded_substring(hard_blocker, dealbreaker_token)
                    for hard_blocker in hard_blockers
                    if hard_blocker
                ):
                    return False, "norm_dealbreaker_hit"

        if preference_signals:
            tier_three = int(getattr(settings, "DEALBREAKER_ESCALATION_TIER3", 10))
            dealbreaker_patterns = preference_signals.get("dealbreaker_patterns") or {}
            job_seniority_signal = str(
                job_norm.get("seniority") or job_norm.get("normalized_seniority") or ""
            ).lower()
            profile_seniority_signal = str(
                profile_norm.get("intent_seniority") or profile_norm.get("seniority") or ""
            ).lower()
            job_domain_signal = str(
                job_norm.get("domain") or job_norm.get("normalized_domain") or "general"
            ).lower()
            avoided_domains = [
                domain.lower() for domain in (preference_signals.get("avoided_domains") or [])
            ]
            for signal, count in dealbreaker_patterns.items():
                if count < tier_three:
                    continue
                if (
                    signal == "too_senior"
                    and job_seniority_signal == "senior"
                    and profile_seniority_signal in ("junior", "mid")
                ):
                    return False, "norm_escalated_dealbreaker:too_senior"
                if (
                    signal == "too_junior"
                    and job_seniority_signal == "junior"
                    and profile_seniority_signal in ("senior", "mid")
                ):
                    return False, "norm_escalated_dealbreaker:too_junior"
                if (
                    signal == "wrong_domain"
                    and job_domain_signal
                    and job_domain_signal in avoided_domains
                ):
                    return False, "norm_escalated_dealbreaker:wrong_domain"

        intent_domain = (
            str(profile_norm.get("intent_domain") or profile_norm.get("domain") or "general")
            .strip()
            .lower()
        )
        job_domain = str(job_norm.get("domain") or "general").strip().lower()

        if not low_confidence and not open_to_unrelated:
            if (
                intent_domain
                and job_domain
                and intent_domain != "general"
                and job_domain != "general"
                and intent_domain != job_domain
                and not self.domains_are_related(intent_domain, job_domain)
            ):
                return False, "norm_domain_mismatch"

        intent_role_type = str(profile_norm.get("intent_role_type") or "").strip().lower() or None
        job_role_type = str(job_norm.get("role_type") or "").strip().lower() or None

        if not low_confidence and intent_role_type and job_role_type:
            flexible_domain = bool(flexibility.get("domain", False))
            if not flexible_domain and not open_to_unrelated:
                if not self.role_types_compatible(intent_role_type, job_role_type):
                    return False, "norm_role_type_mismatch"

        intent_keywords = [
            str(keyword).lower()
            for keyword in (profile_norm.get("intent_keywords") or [])
            if keyword
        ]
        manual_signals = {
            "manual",
            "warehouse",
            "cleaning",
            "physical",
            "handwerk",
            "lager",
            "reinigung",
            "manuell",
        }
        searching_manual = (
            (intent_role_type in {"manual", "service"})
            or open_to_unrelated
            or bool(manual_signals & set(intent_keywords))
        )

        intent_seniority_min = (
            str(profile_norm.get("intent_seniority_min") or "").strip().lower() or None
        )
        intent_seniority_max = (
            str(profile_norm.get("intent_seniority_max") or "").strip().lower() or None
        )
        has_range = intent_seniority_min or intent_seniority_max
        job_seniority = str(job_norm.get("seniority") or "").strip().lower()

        if not low_confidence and job_seniority and has_range:
            job_rank = self._SENIORITY_ORDER.get(job_seniority, -1)
            if job_rank >= 0:
                if intent_seniority_min:
                    min_rank = self._SENIORITY_ORDER.get(intent_seniority_min, -1)
                    if min_rank >= 0 and job_rank < min_rank:
                        return False, "norm_seniority_underqualified"
                if intent_seniority_max:
                    max_rank = self._SENIORITY_ORDER.get(intent_seniority_max, -1)
                    if max_rank >= 0 and job_rank > max_rank:
                        user_exp = coerce_int(profile_norm.get("experience_years"), None)
                        job_exp_min = coerce_int(job_norm.get("experience_min_years"), None)
                        tolerance = int(
                            getattr(settings, "SEARCH_NORMALIZATION_EXPERIENCE_TOLERANCE", 2)
                        )
                        if (
                            job_exp_min is not None
                            and user_exp is not None
                            and job_exp_min > user_exp + tolerance
                        ):
                            return False, "norm_seniority_overqualified"
        elif not low_confidence and job_seniority:
            effective_seniority = (
                str(profile_norm.get("intent_seniority") or profile_norm.get("seniority") or "")
                .strip()
                .lower()
            )
            if effective_seniority:
                if effective_seniority == "junior" and job_seniority == "senior":
                    job_exp_min = coerce_int(job_norm.get("experience_min_years"), None)
                    user_exp = coerce_int(profile_norm.get("experience_years"), None)
                    tolerance = int(
                        getattr(settings, "SEARCH_NORMALIZATION_EXPERIENCE_TOLERANCE", 2)
                    )
                    if (
                        job_exp_min is not None
                        and user_exp is not None
                        and job_exp_min > user_exp + tolerance
                    ):
                        return False, "norm_seniority_overqualified"
                if effective_seniority == "senior" and job_seniority == "junior":
                    job_exp_max = coerce_int(job_norm.get("experience_max_years"), None)
                    user_exp = coerce_int(profile_norm.get("experience_years"), None)
                    if (
                        job_exp_max is not None
                        and user_exp is not None
                        and job_exp_max < user_exp - 3
                    ):
                        return False, "norm_seniority_underqualified"

        effective_qualification = (
            str(
                profile_norm.get("intent_qualification_level")
                or profile_norm.get("qualification_level")
                or ""
            )
            .strip()
            .lower()
        )
        job_qualification = str(job_norm.get("qualification_level") or "").strip().lower()

        if not low_confidence and effective_qualification and job_qualification:
            job_entry_barrier = str(job_norm.get("entry_barrier") or "").strip().lower()
            job_career_changer = bool(job_norm.get("career_changer_friendly", False))
            if not job_career_changer and job_entry_barrier not in {"none", "low"}:
                user_rank = self._QUALIFICATION_RANK.get(effective_qualification, -1)
                job_rank = self._QUALIFICATION_RANK.get(job_qualification, -1)
                if user_rank >= 0 and job_rank >= 0 and job_rank > user_rank + 1:
                    return False, "norm_qualification_mismatch"

        job_entry_barrier_check = str(job_norm.get("entry_barrier") or "").strip().lower()
        if open_to_unrelated and job_entry_barrier_check == "high":
            return False, "norm_entry_barrier_high"

        job_exp_min = coerce_int(job_norm.get("experience_min_years"), None)
        user_exp = coerce_int(profile_norm.get("experience_years"), None)
        if job_exp_min is not None and user_exp is not None:
            tolerance = int(getattr(settings, "SEARCH_NORMALIZATION_EXPERIENCE_TOLERANCE", 2))
            if job_exp_min > user_exp + tolerance:
                return False, "norm_experience_floor"

        career_changer_friendly = bool(job_norm.get("career_changer_friendly", False))
        if not low_confidence and not searching_manual and not career_changer_friendly:
            job_skills = [skill for skill in (job_norm.get("required_skills") or []) if skill]
            profile_skills = list(
                {
                    *[skill for skill in (profile_norm.get("skills") or []) if skill],
                    *[skill for skill in (profile_norm.get("intent_skills") or []) if skill],
                    *[skill for skill in (profile_norm.get("transferable_skills") or []) if skill],
                }
            )
            if len(job_skills) >= 3 and len(profile_skills) >= 3:
                overlap = semantic_skills_score(job_skills, profile_skills)
                if overlap == 0.0:
                    return False, "norm_skills_disjoint"

        if getattr(settings, "STRUCTURED_PRESCORE_ENABLED", False):
            try:
                threshold = float(getattr(settings, "STRUCTURED_PRESCORE_THRESHOLD", 30.0))
                if preference_signals and preference_signals.get("signal_count", 0) >= getattr(
                    settings, "PREFERENCE_MIN_SIGNAL_COUNT", 10
                ):
                    threshold = float(
                        getattr(settings, "STRUCTURED_PRESCORE_THRESHOLD_WITH_PREFS", 35.0)
                    )
                if low_confidence:
                    threshold += 15.0
                prescore = compute_prescore(job_norm, profile_norm, preference_signals)
                if prescore < threshold:
                    return False, f"norm_prescore_low:{prescore:.1f}"
            except Exception:
                pass

        return True, "ok"
