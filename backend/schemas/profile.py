from pydantic import BaseModel, ConfigDict, field_validator, Field
from typing import Optional, Any, List
from datetime import datetime

# ═══════════════════════════════════════
# Search Profile Schemas
# ═══════════════════════════════════════

class SearchProfileBase(BaseModel):
    name: str = "Default Profile"
    cv_content: Optional[str] = None
    role_description: Optional[str] = None
    search_strategy: Optional[str] = None
    location_filter: Optional[str] = None
    workload_filter: Optional[str] = None
    contract_type: Optional[str] = "any"
    posted_within_days: Optional[int] = 30
    max_distance: Optional[int] = 50
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    scrape_mode: Optional[str] = "sequential"
    max_queries: Optional[int] = None
    is_history: Optional[bool] = False
    is_stopped: Optional[bool] = False

    # Query generation control (Feature 4)
    max_occupation_queries: Optional[int] = None
    max_keyword_queries: Optional[int] = None

    # Schedule
    schedule_enabled: Optional[bool] = False
    schedule_interval_hours: Optional[int] = Field(default=24, ge=1)

    @field_validator("max_queries", "max_occupation_queries", "max_keyword_queries", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Optional[int]:
        if v == "" or v == -1 or v == "-1":
            return None
        return v


class SearchProfileCreate(SearchProfileBase):
    pass


class SearchProfileUpdate(BaseModel):
    name: Optional[str] = None
    cv_content: Optional[str] = None
    role_description: Optional[str] = None
    search_strategy: Optional[str] = None
    location_filter: Optional[str] = None
    workload_filter: Optional[str] = None
    contract_type: Optional[str] = None
    posted_within_days: Optional[int] = None
    max_distance: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    scrape_mode: Optional[str] = None
    max_queries: Optional[int] = None
    max_occupation_queries: Optional[int] = None
    max_keyword_queries: Optional[int] = None
    is_history: Optional[bool] = None
    is_stopped: Optional[bool] = None
    schedule_enabled: Optional[bool] = None
    schedule_interval_hours: Optional[int] = None


class StartSearchRequest(SearchProfileBase):
    id: Optional[int] = None
    # Feature 3: separate force-regeneration flags
    force_regenerate_cv_summary: bool = False
    force_regenerate_queries: bool = False


class SearchProfile(SearchProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_scheduled_run: Optional[datetime] = None
    created_at: datetime
    # Caching (Feature 3): expose cached state for frontend awareness
    cached_cv_summary: Optional[str] = None
    cached_queries: Optional[Any] = None


class ScheduleToggle(BaseModel):
    """Toggle schedule on/off for a profile."""
    enabled: bool
    interval_hours: Optional[int] = None
