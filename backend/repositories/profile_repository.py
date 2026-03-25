from typing import List, Optional
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
