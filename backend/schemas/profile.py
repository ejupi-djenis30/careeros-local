from pydantic import BaseModel, ConfigDict
from typing import Optional
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
    schedule_interval_hours: Optional[int] = 24


class SearchProfileCreate(SearchProfileBase):
    pass


class StartSearchRequest(SearchProfileBase):
    id: Optional[int] = None


class SearchProfile(SearchProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_scheduled_run: Optional[datetime] = None
    
    # Caching layer (Feature 3)
    cached_cv_summary: Optional[str] = None
    cached_queries: Optional[str] = None  # JSON string
    
    created_at: datetime


class ScheduleToggle(BaseModel):
    """Toggle schedule on/off for a profile."""
    enabled: bool
    interval_hours: Optional[int] = None
