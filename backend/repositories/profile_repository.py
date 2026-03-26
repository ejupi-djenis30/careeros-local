from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.models import SearchProfile
from backend.repositories.base import BaseRepository


class ProfileRepository(BaseRepository[SearchProfile]):
    def __init__(self, db: Session):
        super().__init__(SearchProfile, db)

    def get_by_user(self, user_id: int, skip: int = 0, limit: int = 100) -> List[SearchProfile]:
        return self.db.query(self.model).filter(self.model.user_id == user_id).offset(skip).limit(limit).all()

    def update_cache(self, profile_id: int, cv_summary: Optional[str] = None, queries_json: Optional[str] = None):
        """Update caching layer fields for a profile."""
        profile = self.get(profile_id)
        if not profile:
            return None

        if cv_summary is not None:
            profile.cached_cv_summary = cv_summary
        if queries_json is not None:
            profile.cached_queries = queries_json

        self.db.add(profile)
        try:
            self.db.commit()
            self.db.refresh(profile)
        except Exception:
            self.db.rollback()
            raise
        return profile

    def update_normalized_profile(
        self,
        profile_id: int,
        normalized_data: dict,
        fingerprint: Optional[str] = None,
    ) -> Optional[SearchProfile]:
        """Persist the dual-signal LLM-extracted candidate normalisation fields onto the profile.

        ``normalized_data`` is the dict returned by ``LLMService.normalize_user_profile()``.
        It contains both ``candidate_profile`` fields (seniority, domain, skills etc.) and
        ``search_intent`` fields (intent_domain, intent_seniority, open_to_unrelated etc.).
        ``fingerprint`` is the cache-invalidation key so we can skip re-extraction
        on the next run when inputs have not changed.
        """
        profile = self.get(profile_id)
        if not profile:
            return None

        profile.profile_normalization_status = "normalized"
        profile.profile_normalized_at = datetime.now(timezone.utc)
        if fingerprint is not None:
            profile.profile_normalization_fingerprint = fingerprint

        # Candidate profile (CV facts)
        profile.profile_normalized_seniority = normalized_data.get("seniority")
        profile.profile_normalized_domain = normalized_data.get("domain")
        profile.profile_normalized_role_family = normalized_data.get("role_family")
        profile.profile_normalized_qualification_level = normalized_data.get("qualification_level")
        profile.profile_normalized_experience_years = normalized_data.get("experience_years")
        profile.profile_normalized_languages = normalized_data.get("languages") or []
        profile.profile_normalized_skills = normalized_data.get("skills") or []

        # Search intent (what the user WANTS)
        profile.profile_search_intent_domain = normalized_data.get("intent_domain")
        profile.profile_search_intent_seniority = normalized_data.get("intent_seniority")
        profile.profile_search_intent_role_family = normalized_data.get("intent_role_family")
        profile.profile_search_intent_qualification_level = normalized_data.get("intent_qualification_level")
        profile.profile_search_intent_skills = normalized_data.get("intent_skills") or []
        profile.profile_search_intent_open_to_unrelated = bool(normalized_data.get("open_to_unrelated", False))
        profile.profile_search_intent_keywords = normalized_data.get("intent_keywords") or []

        # V2 enhanced candidate profile fields
        profile.profile_normalized_role_type = normalized_data.get("role_type")
        profile.profile_normalized_industry_sectors = normalized_data.get("industry_sectors") or []
        profile.profile_normalized_transferable_skills = normalized_data.get("transferable_skills") or []

        # V2 enhanced search intent fields
        profile.profile_search_intent_role_type = normalized_data.get("intent_role_type")
        profile.profile_search_intent_seniority_min = normalized_data.get("intent_seniority_min")
        profile.profile_search_intent_seniority_max = normalized_data.get("intent_seniority_max")
        profile.profile_search_intent_dealbreakers = normalized_data.get("dealbreakers") or []
        profile.profile_search_intent_flexibility = normalized_data.get("flexibility") or {}

        self.db.add(profile)
        try:
            self.db.commit()
            self.db.refresh(profile)
        except Exception:
            self.db.rollback()
            raise
        return profile

