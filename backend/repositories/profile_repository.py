from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.repositories.base import BaseRepository
from backend.models import SearchProfile

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
        """Persist the LLM-extracted candidate normalisation fields onto the profile.

        ``normalized_data`` is the dict returned by
        ``LLMService.normalize_user_profile()`` (keys: seniority, domain,
        role_family, qualification_level, experience_years, languages, skills,
        confidence).
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
        profile.profile_normalized_seniority = normalized_data.get("seniority")
        profile.profile_normalized_domain = normalized_data.get("domain")
        profile.profile_normalized_role_family = normalized_data.get("role_family")
        profile.profile_normalized_qualification_level = normalized_data.get("qualification_level")
        profile.profile_normalized_experience_years = normalized_data.get("experience_years")
        profile.profile_normalized_languages = normalized_data.get("languages") or []
        profile.profile_normalized_skills = normalized_data.get("skills") or []

        self.db.add(profile)
        try:
            self.db.commit()
            self.db.refresh(profile)
        except Exception:
            self.db.rollback()
            raise
        return profile

