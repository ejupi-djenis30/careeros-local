import copy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.models import SearchProfile
from backend.repositories.base import BaseRepository

SEARCH_LOCK_RESERVED = "reserved"
SEARCH_LOCK_ACTIVE = "active"


def _coerce_status_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        timestamp = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            timestamp = datetime.fromisoformat(text)
        except (TypeError, ValueError):
            return None

    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp


class ProfileRepository(BaseRepository[SearchProfile]):
    def __init__(self, db: Session):
        super().__init__(SearchProfile, db)

    def get_for_user(self, profile_id: int, user_id: int) -> Optional[SearchProfile]:
        return (
            self.db.query(self.model)
            .filter(self.model.id == profile_id, self.model.user_id == user_id)
            .first()
        )

    def get_by_user(self, user_id: int, skip: int = 0, limit: int = 100) -> List[SearchProfile]:
        return (
            self.db.query(self.model)
            .filter(self.model.user_id == user_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_scheduled_profiles(self, user_id: Optional[int] = None) -> List[SearchProfile]:
        query = self.db.query(self.model).filter(self.model.schedule_enabled.is_(True))
        if user_id is not None:
            query = query.filter(self.model.user_id == user_id)
        return query.all()

    def acquire_search_lock(
        self,
        profile_id: int,
        token: str,
        *,
        reservation_ttl_seconds: int,
        active_ttl_seconds: int,
    ) -> bool:
        now = datetime.now(timezone.utc)
        reserved_stale_before = now - timedelta(seconds=reservation_ttl_seconds)
        active_stale_before = now - timedelta(seconds=active_ttl_seconds)

        try:
            updated = (
                self.db.query(self.model)
                .filter(self.model.id == profile_id)
                .filter(
                    or_(
                        self.model.search_lock_token.is_(None),
                        and_(
                            self.model.search_lock_state == SEARCH_LOCK_RESERVED,
                            or_(
                                self.model.search_lock_acquired_at.is_(None),
                                self.model.search_lock_acquired_at < reserved_stale_before,
                            ),
                        ),
                        and_(
                            self.model.search_lock_state == SEARCH_LOCK_ACTIVE,
                            or_(
                                self.model.search_lock_acquired_at.is_(None),
                                self.model.search_lock_acquired_at < active_stale_before,
                            ),
                        ),
                    )
                )
                .update(
                    {
                        self.model.search_lock_token: token,
                        self.model.search_lock_state: SEARCH_LOCK_RESERVED,
                        self.model.search_lock_acquired_at: now,
                    },
                    synchronize_session=False,
                )
            )
            if not updated:
                self.db.rollback()
                return False
            self.db.commit()
            self.db.expire_all()
            return True
        except Exception:
            self.db.rollback()
            raise

    def activate_search_lock(self, profile_id: int, token: str) -> bool:
        now = datetime.now(timezone.utc)
        try:
            updated = (
                self.db.query(self.model)
                .filter(
                    self.model.id == profile_id,
                    self.model.search_lock_token == token,
                )
                .update(
                    {
                        self.model.search_lock_state: SEARCH_LOCK_ACTIVE,
                        self.model.search_lock_acquired_at: now,
                    },
                    synchronize_session=False,
                )
            )
            if not updated:
                self.db.rollback()
                return False
            self.db.commit()
            self.db.expire_all()
            return True
        except Exception:
            self.db.rollback()
            raise

    def release_search_lock(self, profile_id: int, token: Optional[str] = None) -> bool:
        filters = [self.model.id == profile_id]
        if token is not None:
            filters.append(self.model.search_lock_token == token)

        try:
            updated = (
                self.db.query(self.model)
                .filter(*filters)
                .update(
                    {
                        self.model.search_lock_token: None,
                        self.model.search_lock_state: None,
                        self.model.search_lock_acquired_at: None,
                    },
                    synchronize_session=False,
                )
            )
            if not updated:
                self.db.rollback()
                return False
            self.db.commit()
            self.db.expire_all()
            return True
        except Exception:
            self.db.rollback()
            raise

    def update_search_status(self, profile_id: int, status_payload: Dict[str, Any]) -> bool:
        payload = copy.deepcopy(status_payload)
        state = payload.get("state")
        updated_at = _coerce_status_timestamp(payload.get("updated_at")) or datetime.now(
            timezone.utc
        )
        started_at = _coerce_status_timestamp(payload.get("started_at"))
        finished_at = _coerce_status_timestamp(payload.get("finished_at"))

        try:
            updated = (
                self.db.query(self.model)
                .filter(self.model.id == profile_id)
                .update(
                    {
                        self.model.search_status_state: state,
                        self.model.search_status_payload: payload,
                        self.model.search_status_started_at: started_at,
                        self.model.search_status_updated_at: updated_at,
                        self.model.search_status_finished_at: finished_at,
                    },
                    synchronize_session=False,
                )
            )
            if not updated:
                self.db.rollback()
                return False
            self.db.commit()
            self.db.expire_all()
            return True
        except Exception:
            self.db.rollback()
            raise

    def clear_search_status(self, profile_id: int) -> bool:
        try:
            updated = (
                self.db.query(self.model)
                .filter(self.model.id == profile_id)
                .update(
                    {
                        self.model.search_status_state: None,
                        self.model.search_status_payload: None,
                        self.model.search_status_started_at: None,
                        self.model.search_status_updated_at: None,
                        self.model.search_status_finished_at: None,
                    },
                    synchronize_session=False,
                )
            )
            if not updated:
                self.db.rollback()
                return False
            self.db.commit()
            self.db.expire_all()
            return True
        except Exception:
            self.db.rollback()
            raise

    def get_search_status(self, profile_id: int) -> Optional[Dict[str, Any]]:
        profile = (
            self.db.query(self.model.search_status_payload)
            .filter(self.model.id == profile_id)
            .first()
        )
        if not profile:
            return None

        payload = profile[0]
        return copy.deepcopy(payload) if isinstance(payload, dict) else None

    def get_search_statuses(self, user_id: Optional[int] = None) -> Dict[int, Dict[str, Any]]:
        query = self.db.query(self.model.id, self.model.search_status_payload).filter(
            self.model.search_status_state.isnot(None)
        )
        if user_id is not None:
            query = query.filter(self.model.user_id == user_id)

        statuses: Dict[int, Dict[str, Any]] = {}
        for profile_id, payload in query.all():
            if isinstance(payload, dict):
                statuses[int(profile_id)] = copy.deepcopy(payload)
        return statuses

    def clear_stale_search_statuses(
        self,
        *,
        max_age_seconds: float,
        terminal_states: List[str],
    ) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)

        try:
            updated = (
                self.db.query(self.model)
                .filter(
                    self.model.search_status_state.in_(terminal_states),
                    self.model.search_status_finished_at.is_not(None),
                    self.model.search_status_finished_at < cutoff,
                )
                .update(
                    {
                        self.model.search_status_state: None,
                        self.model.search_status_payload: None,
                        self.model.search_status_started_at: None,
                        self.model.search_status_updated_at: None,
                        self.model.search_status_finished_at: None,
                    },
                    synchronize_session=False,
                )
            )
            if not updated:
                self.db.rollback()
                return 0
            self.db.commit()
            self.db.expire_all()
            return int(updated)
        except Exception:
            self.db.rollback()
            raise

    def update_cache(
        self, profile_id: int, cv_summary: Optional[str] = None, queries_json: Optional[str] = None
    ):
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
        profile.profile_search_intent_qualification_level = normalized_data.get(
            "intent_qualification_level"
        )
        profile.profile_search_intent_skills = normalized_data.get("intent_skills") or []
        profile.profile_search_intent_open_to_unrelated = bool(
            normalized_data.get("open_to_unrelated", False)
        )
        profile.profile_search_intent_keywords = normalized_data.get("intent_keywords") or []

        # V2 enhanced candidate profile fields
        profile.profile_normalized_role_type = normalized_data.get("role_type")
        profile.profile_normalized_industry_sectors = normalized_data.get("industry_sectors") or []
        profile.profile_normalized_transferable_skills = (
            normalized_data.get("transferable_skills") or []
        )

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
