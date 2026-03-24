from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any, Dict
from datetime import datetime

# ═══════════════════════════════════════
# Job Schemas
# ═══════════════════════════════════════

class JobBase(BaseModel):
    title: str
    company: str
    description: Optional[str] = None
    location: Optional[str] = None
    external_url: str
    application_url: Optional[str] = None
    application_email: Optional[str] = None
    workload: Optional[str] = None
    publication_date: Optional[datetime] = None
    platform: Optional[str] = None
    platform_job_id: Optional[str] = None


class JobCreate(JobBase):
    is_scraped: bool = False
    source_query: Optional[str] = None
    search_profile_id: Optional[int] = None
    affinity_score: Optional[float] = None
    affinity_analysis: Optional[str] = None
    worth_applying: Optional[bool] = False
    distance_km: Optional[float] = None
    raw_metadata: Optional[Dict[str, Any]] = None


class JobUpdate(BaseModel):
    """Partial update schema — all fields optional."""
    applied: Optional[bool] = None


class Job(JobBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_scraped: bool
    source_query: Optional[str] = None
    search_profile_id: Optional[int] = None
    affinity_score: Optional[float] = None
    affinity_analysis: Optional[str] = None
    worth_applying: Optional[bool] = False
    distance_km: Optional[float] = None
    applied: bool
    # Feature 2: True when same ScrapedJob was applied in another profile
    applied_elsewhere: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    raw_metadata: Optional[Dict[str, Any]] = None


class JobPaginationResponse(BaseModel):
    items: List[Job]
    total: int
    page: int
    pages: int
    total_applied: int
    avg_score: float
