from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.ai.attestation import is_persisted_match_payload_valid
from backend.jobs.urls import normalize_job_url

# ═══════════════════════════════════════
# Job Schemas
# ═══════════════════════════════════════


class JobBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=240)
    company: str = Field(min_length=1, max_length=240)
    description: Optional[str] = Field(default=None, max_length=100_000)
    location: Optional[str] = Field(default=None, max_length=500)
    external_url: str = Field(min_length=1, max_length=2048)
    application_url: Optional[str] = Field(default=None, max_length=2048)
    application_email: Optional[str] = Field(default=None, max_length=320)
    workload: Optional[str] = Field(default=None, max_length=120)
    publication_date: Optional[datetime] = None
    platform: Optional[str] = Field(default=None, max_length=80)
    platform_job_id: Optional[str] = Field(default=None, max_length=500)

    @field_validator("title", "company", "external_url")
    @classmethod
    def reject_empty_strings(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field must not be empty")
        return v.strip()

    @field_validator("external_url")
    @classmethod
    def validate_external_url(cls, value: str) -> str:
        normalized = normalize_job_url(value, required=True)
        if normalized is None:  # Defensive guard for the shared optional URL normalizer.
            raise ValueError("External URL is required")
        return normalized

    @field_validator("application_url")
    @classmethod
    def validate_application_url(cls, value: Optional[str]) -> Optional[str]:
        return normalize_job_url(value, required=False)

    @property
    def url(self):
        """Backward compatibility for frontend 'url' field."""
        return self.external_url


class JobCreate(JobBase):
    source_query: Optional[str] = Field(default=None, max_length=1000)
    search_profile_id: Optional[int] = Field(default=None, gt=0)
    scraped_job_id: Optional[int] = Field(default=None, gt=0)
    distance_km: Optional[float] = Field(default=None, ge=0)
    raw_metadata: Optional[Dict[str, Any]] = Field(default=None, max_length=100)


FEEDBACK_SIGNAL_VALUES = {
    "too_senior",
    "too_junior",
    "wrong_domain",
    "bad_salary",
    "bad_location",
    "not_interested",
    "already_applied",
    "other",
}


class JobUpdate(BaseModel):
    """Update schema — only allows updating user-specific interaction flags."""

    applied: Optional[bool] = None
    dismissed: Optional[bool] = None
    feedback_signal: Optional[str] = None

    @field_validator("feedback_signal")
    @classmethod
    def validate_feedback_signal(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in FEEDBACK_SIGNAL_VALUES:
            raise ValueError(f"feedback_signal must be one of {sorted(FEEDBACK_SIGNAL_VALUES)}")
        return v


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
    industry_sector: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class JobAnalysisCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "skill",
        "experience",
        "intent",
        "language",
        "location",
        "transferability",
        "qualification",
    ]
    assessment: Literal["strength", "weakness", "gap", "risk", "insufficient_evidence"]
    job_evidence_id: str = Field(pattern=r"^job:\d+$", max_length=32)
    candidate_evidence_id: Literal["candidate:profile"]
    job_quote_id: str = Field(pattern=r"^job:\d+:[a-z_]+:\d+$", max_length=64)
    candidate_quote_id: str = Field(pattern=r"^candidate:profile:[a-z_]+:\d+$", max_length=80)
    job_quote_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_quote_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    job_evidence: str = Field(min_length=1, max_length=240)
    candidate_evidence: str = Field(min_length=4, max_length=240)


class JobAnalysisStructured(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation: Literal["strong_fit", "consider", "weak_fit", "insufficient_evidence"]
    evidence_citations: List[JobAnalysisCitation] = Field(min_length=1, max_length=7)


class JobResponse(JobBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
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
    viewed_at: Optional[datetime] = None
    dismissed: bool = False
    dismissed_at: Optional[datetime] = None
    feedback_signal: Optional[str] = None
    skill_match_score: Optional[float] = None
    experience_match_score: Optional[float] = None
    intent_match_score: Optional[float] = None
    language_match_score: Optional[float] = None
    location_match_score: Optional[float] = None
    transferability_score: Optional[float] = None
    qualification_gap_score: Optional[float] = None
    analysis_structured: Optional[JobAnalysisStructured] = None
    analysis_provenance: Optional[str] = None
    analysis_model_id: Optional[str] = None
    analysis_contract_version: Optional[str] = None
    analysis_validated_at: Optional[datetime] = None
    analysis_execution_id: Optional[str] = None
    analysis_output_fingerprint: Optional[str] = None
    analysis_execution_row_index: Optional[int] = None
    analysis_row_fingerprint: Optional[str] = None
    analysis_input_fingerprint: Optional[str] = None
    red_flags: Optional[List[str]] = None
    analysis_verified: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    raw_metadata: Optional[Dict[str, Any]] = None
    normalized_job: Optional[NormalizedJobData] = None

    @model_validator(mode="after")
    def derive_analysis_verification(self) -> "JobResponse":
        self.analysis_verified = bool(
            self.analysis_verified
            and self.analysis_structured is not None
            and self.analysis_provenance == "local_model_validated"
            and bool((self.analysis_model_id or "").strip())
            and self.analysis_contract_version == "1.1.0"
            and self.analysis_validated_at is not None
            and is_persisted_match_payload_valid(self)
        )
        if not self.analysis_verified:
            self.affinity_score = None
            self.affinity_analysis = None
            self.worth_applying = False
            self.skill_match_score = None
            self.experience_match_score = None
            self.intent_match_score = None
            self.language_match_score = None
            self.location_match_score = None
            self.transferability_score = None
            self.qualification_gap_score = None
            self.analysis_structured = None
            self.analysis_provenance = None
            self.analysis_model_id = None
            self.analysis_contract_version = None
            self.analysis_validated_at = None
            self.analysis_execution_id = None
            self.analysis_output_fingerprint = None
            self.analysis_execution_row_index = None
            self.analysis_row_fingerprint = None
            self.analysis_input_fingerprint = None
            self.red_flags = None
        return self

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
