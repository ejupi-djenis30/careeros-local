from typing import Any, Dict

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.repositories.profile_repository import ProfileRepository
from backend.schemas import ScheduleToggle, SearchProfileCreate, SearchProfileUpdate

_PREFERENCE_FIELDS = {
    "preferred_languages",
    "preferred_domains",
    "remote_only",
    "salary_min_chf",
    "workload_min",
    "workload_max",
    "hard_max_distance_km",
}

_QUERY_CACHE_INVALIDATION_FIELDS = {
    "role_description",
    "search_strategy",
    "location_filter",
    "workload_filter",
    "contract_type",
    "posted_within_days",
    "max_distance",
    "latitude",
    "longitude",
    "max_queries",
    "max_occupation_queries",
    "max_keyword_queries",
}


_PREFERENCE_FIELD_TYPES: Dict[str, type] = {
    "preferred_languages": list,
    "preferred_domains": list,
    "remote_only": bool,
    "salary_min_chf": (int, float),
    "workload_min": int,
    "workload_max": int,
    "hard_max_distance_km": (int, float),
}


def _coerce_preference_value(field: str, value: Any) -> Any:
    """Coerce a preference value to its expected type, returning None if invalid."""
    expected = _PREFERENCE_FIELD_TYPES.get(field)
    if expected is None or value is None:
        return value
    if isinstance(value, expected):
        return value
    # Attempt coercion
    try:
        if expected is bool or (isinstance(expected, tuple) and bool in expected):
            if isinstance(value, str):
                if value.lower() in ("true", "yes", "1"):
                    return True
                if value.lower() in ("false", "no", "0"):
                    return False
            return bool(value)
        if expected is int or (isinstance(expected, tuple) and int in expected):
            return int(float(str(value)))
        if expected is list:
            if isinstance(value, str):
                return [v.strip() for v in value.split(",") if v.strip()]
            return list(value)
    except (TypeError, ValueError):
        return None
    return None


def _extract_advanced_preferences(
    data: Dict[str, Any], existing: Dict[str, Any] | None = None
) -> tuple[Dict[str, Any], Dict[str, Any] | None]:
    base = dict(existing or {})
    extracted: Dict[str, Any] = {}
    for field in _PREFERENCE_FIELDS:
        if field in data:
            raw = data.pop(field)
            coerced = _coerce_preference_value(field, raw)
            extracted[field] = coerced

    base.update({k: v for k, v in extracted.items() if v is not None})
    cleaned = {k: v for k, v in base.items() if v is not None}
    return data, (cleaned or None)


class ProfileService:
    def __init__(self, db: Session):
        self.repo = ProfileRepository(db)

    def get_profiles_by_user(self, user_id: int, skip: int = 0, limit: int = 100):
        return self.repo.get_by_user(user_id, skip=skip, limit=limit)

    def create_profile(self, user_id: int, profile_in: SearchProfileCreate):
        data = profile_in.model_dump()
        data, advanced_preferences = _extract_advanced_preferences(data)
        data["advanced_preferences"] = advanced_preferences
        data["user_id"] = user_id

        # Enforce per-user name uniqueness (non-empty names only)
        name = data.get("name", "").strip()
        if name:
            existing = self.repo.get_by_user(user_id)
            if any(p.name and p.name.strip().lower() == name.lower() for p in existing):
                raise HTTPException(
                    status_code=409, detail=f"A search with the name '{name}' already exists."
                )

        return self.repo.create(data)

    def update_profile(self, user_id: int, profile_id: int, profile_in: SearchProfileUpdate):
        profile = self.repo.get(profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        if profile.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        update_data = profile_in.model_dump(exclude_unset=True)
        update_data, advanced_preferences = _extract_advanced_preferences(
            update_data,
            existing=getattr(profile, "advanced_preferences", None),
        )
        if "advanced_preferences" in update_data or advanced_preferences is not None:
            update_data["advanced_preferences"] = advanced_preferences

        if "cv_content" in update_data:
            update_data["cached_cv_summary"] = None
            update_data["profile_normalization_fingerprint"] = None

        if any(field in update_data for field in ("role_description", "search_strategy")):
            update_data["profile_normalization_fingerprint"] = None
            update_data["profile_normalization_status"] = "pending"

        if any(field in update_data for field in _QUERY_CACHE_INVALIDATION_FIELDS) or (
            advanced_preferences is not None
        ):
            update_data["cached_queries"] = None

        return self.repo.update(profile, update_data)

    def toggle_schedule(self, user_id: int, profile_id: int, schedule: ScheduleToggle):
        profile = self.repo.get(profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        if profile.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        update_data = {"schedule_enabled": schedule.enabled}
        if schedule.interval_hours:
            update_data["schedule_interval_hours"] = schedule.interval_hours

        updated_profile = self.repo.update(profile, update_data)

        # Actually add/remove the APScheduler job
        from backend.services.scheduler import add_schedule, remove_schedule

        if schedule.enabled:
            interval = schedule.interval_hours or updated_profile.schedule_interval_hours or 24
            add_schedule(profile_id, interval)
        else:
            remove_schedule(profile_id)

        return updated_profile

    def delete_profile(self, user_id: int, profile_id: int):
        profile = self.repo.get(profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        if profile.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        from backend.services.scheduler import remove_schedule
        from backend.services.search_status import clear_status, release_task

        remove_schedule(profile_id)
        # Release any in-flight reservation so the profile_id slot doesn't block forever
        release_task(profile_id)
        clear_status(profile_id)

        self.repo.delete(profile_id)


def get_profile_service(db: Session) -> ProfileService:
    return ProfileService(db)
