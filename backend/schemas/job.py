from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any
from datetime import datetime

# ═══════════════════════════════════════
# Job Schemas
# ═══════════════════════════════════════

class JobBase(BaseModel):
    title: str
    company: str
    description: Optional[str] = None
    location: Optional[str] = None
    url: str
    external_url: Optional[str] = None
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
    scraped_job_id: Optional[int] = None
    affinity_score: Optional[float] = None
    affinity_analysis: Optional[str] = None
    worth_applying: Optional[bool] = False
    distance_km: Optional[float] = None


class JobUpdate(BaseModel):
    """Update schema — only allows updating user-specific interaction flags."""
    applied: Optional[bool] = None
    title: Optional[str] = None
    company: Optional[str] = None


class Job(JobBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_scraped: bool
    source_query: Optional[str] = None
    search_profile_id: Optional[int] = None
    scraped_job_id: int
    affinity_score: Optional[float] = None
    affinity_analysis: Optional[str] = None
    worth_applying: Optional[bool] = False
    distance_km: Optional[float] = None
    applied: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class JobPaginationResponse(BaseModel):
    items: List[Job]
    total: int
    page: int
    pages: int
    total_applied: int
    avg_score: float
