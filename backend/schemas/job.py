from pydantic import BaseModel, ConfigDict, Field
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

    @property
    def url(self):
        """Backward compatibility for frontend 'url' field."""
        return self.external_url


class JobCreate(JobBase):
    is_scraped: bool = False
    source_query: Optional[str] = None
    search_profile_id: Optional[int] = None
    scraped_job_id: Optional[int] = None
    affinity_score: Optional[float] = None
    affinity_analysis: Optional[str] = None
    worth_applying: Optional[bool] = False
    distance_km: Optional[float] = None
    raw_metadata: Optional[Dict[str, Any]] = None


class JobUpdate(BaseModel):
    """Update schema — only allows updating user-specific interaction flags."""
    applied: Optional[bool] = None


class NormalizedJobData(BaseModel):
    status: Optional[str] = None
    normalized_at: Optional[datetime] = None
    version: Optional[int] = None
    source: Optional[str] = None
    confidence: Optional[float] = None
    title: Optional[str] = None
    role_family: Optional[str] = None
    domain: Optional[str] = None
    seniority: Optional[str] = None
    employment_mode: Optional[str] = None
    contract_type: Optional[str] = None
    qualification_level: Optional[str] = None
    experience_min_years: Optional[int] = None
    experience_max_years: Optional[int] = None
    workload_min: Optional[int] = None
    workload_max: Optional[int] = None
    salary_min_chf: Optional[int] = None
    salary_max_chf: Optional[int] = None
    required_languages: List[Dict[str, Any]] = Field(default_factory=list)
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    physical_requirements: List[str] = Field(default_factory=list)
    entry_barrier: Optional[str] = None
    career_changer_friendly: Optional[bool] = None
    hard_blockers: List[str] = Field(default_factory=list)
    education_levels: List[str] = Field(default_factory=list)
    key_requirements: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class JobResponse(JobBase):
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
    applied_elsewhere: bool = Field(
        default=False,
        description="Derived response field. True when the same scraped job is marked applied in another profile for the same user.",
    )
    skill_match_score: Optional[float] = None
    experience_match_score: Optional[float] = None
    intent_match_score: Optional[float] = None
    language_match_score: Optional[float] = None
    location_match_score: Optional[float] = None
    transferability_score: Optional[float] = None
    qualification_gap_score: Optional[float] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    raw_metadata: Optional[Dict[str, Any]] = None
    normalized_job: Optional[NormalizedJobData] = None

    @property
    def url(self):
        """Backward compatibility for frontend 'url' field."""
        return self.external_url


class JobPaginationResponse(BaseModel):
    items: List[JobResponse]
    total: int
    page: int
    pages: int
    total_applied: int
    avg_score: float
