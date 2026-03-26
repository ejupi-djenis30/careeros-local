import re
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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

    # Explicit user query preferences
    preferred_languages: Optional[List[str]] = None
    preferred_domains: Optional[List[str]] = None

    # Hard filtering controls
    remote_only: Optional[bool] = False
    salary_min_chf: Optional[int] = None
    workload_min: Optional[int] = None
    workload_max: Optional[int] = None
    hard_max_distance_km: Optional[int] = None

    # Schedule
    schedule_enabled: Optional[bool] = False
    schedule_interval_hours: Optional[int] = Field(default=24, ge=1)

    @field_validator(
        "max_queries",
        "max_occupation_queries",
        "max_keyword_queries",
        "salary_min_chf",
        "workload_min",
        "workload_max",
        "hard_max_distance_km",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Optional[int]:
        if v == "" or v == -1 or v == "-1":
            return None
        return v

    @field_validator("preferred_languages", mode="before")
    @classmethod
    def normalize_preferred_languages(cls, value: Any) -> Optional[List[str]]:
        if value is None:
            return None
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",")]
        if not isinstance(value, list):
            return None

        aliases = {
            "english": "en",
            "en": "en",
            "de": "de",
            "deutsch": "de",
            "german": "de",
            "fr": "fr",
            "french": "fr",
            "francais": "fr",
            "français": "fr",
            "it": "it",
            "italian": "it",
            "italiano": "it",
            "es": "es",
            "spanish": "es",
            "espanol": "es",
            "español": "es",
            "pt": "pt",
            "portuguese": "pt",
            "pl": "pl",
            "polish": "pl",
            "ro": "ro",
            "romanian": "ro",
        }
        normalized: List[str] = []
        seen = set()
        for item in value:
            text = str(item or "").strip().lower()
            if not text:
                continue
            code = aliases.get(text, text[:2])
            if not re.fullmatch(r"[a-z]{2}", code):
                continue
            if code not in seen:
                seen.add(code)
                normalized.append(code)
        return normalized or None

    @field_validator("preferred_domains", mode="before")
    @classmethod
    def normalize_preferred_domains(cls, value: Any) -> Optional[List[str]]:
        if value is None:
            return None
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",")]
        if not isinstance(value, list):
            return None

        normalized: List[str] = []
        seen = set()
        for item in value:
            text = str(item or "").strip().lower()
            text = text.replace("/", "-").replace("_", "-")
            text = re.sub(r"[^a-z0-9- ]", "", text)
            text = text.replace(" ", "-")
            text = re.sub(r"-+", "-", text).strip("-")
            if not text:
                continue
            if text not in seen:
                seen.add(text)
                normalized.append(text)
        return normalized or None

    @model_validator(mode="after")
    def validate_hard_filter_ranges(self):
        if self.workload_min is not None and not 0 <= self.workload_min <= 100:
            raise ValueError("workload_min must be between 0 and 100")
        if self.workload_max is not None and not 0 <= self.workload_max <= 100:
            raise ValueError("workload_max must be between 0 and 100")
        if self.workload_min is not None and self.workload_max is not None and self.workload_min > self.workload_max:
            raise ValueError("workload_min cannot be greater than workload_max")
        if self.salary_min_chf is not None and self.salary_min_chf < 0:
            raise ValueError("salary_min_chf must be non-negative")
        if self.hard_max_distance_km is not None and self.hard_max_distance_km < 0:
            raise ValueError("hard_max_distance_km must be non-negative")
        if self.max_distance is not None and not 0 <= self.max_distance <= 500:
            raise ValueError("max_distance must be between 0 and 500 km")
        if self.posted_within_days is not None and not 1 <= self.posted_within_days <= 365:
            raise ValueError("posted_within_days must be between 1 and 365 days")
        return self


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
    preferred_languages: Optional[List[str]] = None
    preferred_domains: Optional[List[str]] = None
    remote_only: Optional[bool] = None
    salary_min_chf: Optional[int] = None
    workload_min: Optional[int] = None
    workload_max: Optional[int] = None
    hard_max_distance_km: Optional[int] = None
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

    # Caching layer (Feature 3)
    cached_cv_summary: Optional[str] = None
    cached_queries: Optional[Any] = None  # JSON object

    created_at: datetime


class ScheduleToggle(BaseModel):
    """Toggle schedule on/off for a profile."""
    enabled: bool
    interval_hours: Optional[int] = None
