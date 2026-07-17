from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

UuidString = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValidationCode(StrEnum):
    SCHEMA_INVALID = "schema_invalid"
    EVIDENCE_MISSING = "evidence_missing"
    EVIDENCE_UNKNOWN = "evidence_unknown"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    SEMANTIC_INVALID = "semantic_invalid"
    ROW_COUNT_MISMATCH = "row_count_mismatch"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"


class GroundedClaim(StrictContract):
    text: str = Field(min_length=1, max_length=800)
    fact_ids: list[UuidString] = Field(default_factory=list, max_length=12)
    job_ids: list[int] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def require_evidence(self) -> "GroundedClaim":
        if not self.fact_ids and not self.job_ids:
            raise ValueError("each career claim requires at least one evidence identifier")
        if len(set(self.fact_ids)) != len(self.fact_ids) or len(set(self.job_ids)) != len(
            self.job_ids
        ):
            raise ValueError("claim evidence identifiers must be unique")
        if any(job_id < 1 for job_id in self.job_ids):
            raise ValueError("job evidence identifiers must be positive")
        return self


class CoachResult(StrictContract):
    answer: str = Field(min_length=1, max_length=6000)
    claims: list[GroundedClaim] = Field(default_factory=list, max_length=12)
    fact_citations: list[UuidString] = Field(default_factory=list, max_length=32)
    job_citations: list[int] = Field(default_factory=list, max_length=32)
    confidence: float = Field(ge=0, le=1)
    missing_evidence: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def citations_cover_claims(self) -> "CoachResult":
        claim_facts = {item for claim in self.claims for item in claim.fact_ids}
        claim_jobs = {item for claim in self.claims for item in claim.job_ids}
        if not claim_facts <= set(self.fact_citations):
            raise ValueError("aggregate fact citations do not cover every claim")
        if not claim_jobs <= set(self.job_citations):
            raise ValueError("aggregate job citations do not cover every claim")
        if len(set(self.fact_citations)) != len(self.fact_citations):
            raise ValueError("fact citations must be unique")
        if len(set(self.job_citations)) != len(self.job_citations):
            raise ValueError("job citations must be unique")
        return self


class LanguageLevel(StrictContract):
    code: str = Field(pattern=r"^[a-z]{2}$")
    level: str | None = Field(
        default=None,
        pattern=r"^(A1|A2|B1|B2|C1|C2|native)$",
    )


Domain = Literal[
    "general",
    "it",
    "finance",
    "medical",
    "engineering",
    "hospitality",
    "sales",
    "logistics",
    "administration",
    "legal",
    "education",
    "marketing",
    "consulting",
    "pharma",
    "construction",
]
Seniority = Literal["junior", "mid", "senior"]
RoleType = Literal[
    "technical", "manual", "administrative", "creative", "managerial", "service", "professional"
]
Qualification = Literal["none", "vocational", "bachelor", "master", "phd"]


class CandidateProfileBlock(StrictContract):
    seniority: Seniority
    domain: Domain
    role_family: str = Field(min_length=1, max_length=160)
    role_type: RoleType
    qualification_level: Qualification
    experience_years: int = Field(ge=0, le=80)
    languages: list[LanguageLevel] = Field(default_factory=list, max_length=12)
    skills: list[str] = Field(default_factory=list, max_length=20)
    industry_sectors: list[str] = Field(default_factory=list, max_length=5)
    transferable_skills: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0, le=1)


class SearchIntentBlock(StrictContract):
    target_domain: Domain
    target_role_type: RoleType | None = None
    target_seniority: Seniority | None = None
    target_seniority_min: Seniority | None = None
    target_seniority_max: Seniority | None = None
    target_role_family: str = Field(default="", max_length=160)
    target_qualification_level: Qualification | None = None
    target_skills: list[str] = Field(default_factory=list, max_length=15)
    open_to_unrelated: bool
    intent_keywords: list[str] = Field(default_factory=list, max_length=15)
    dealbreakers: list[str] = Field(default_factory=list, max_length=12)
    flexibility: dict[Literal["domain", "seniority", "qualification", "location"], bool]
    confidence: float = Field(ge=0, le=1)


class ProfileNormalizationResult(StrictContract):
    candidate_profile: CandidateProfileBlock
    search_intent: SearchIntentBlock


class SearchQuery(StrictContract):
    query: str = Field(min_length=2, max_length=240)
    domain: Domain
    type: Literal["occupation", "keyword"]
    language: Literal["en", "de", "fr", "it"]


class SearchPlanResult(StrictContract):
    searches: list[SearchQuery] = Field(min_length=1, max_length=30)


class JobNormalization(StrictContract):
    title: str = Field(min_length=1, max_length=240)
    role_family: str = Field(min_length=1, max_length=160)
    domain: Domain
    industry_sector: str | None = Field(default=None, max_length=160)
    role_type: RoleType
    seniority: Seniority | None = None
    employment_mode: Literal["remote", "hybrid", "on-site"] | None = None
    contract_type: Literal["permanent", "temporary", "internship", "freelance"] | None = None
    qualification_level: Qualification | None = None
    experience_min_years: int | None = Field(default=None, ge=0, le=80)
    experience_max_years: int | None = Field(default=None, ge=0, le=80)
    workload_min: int = Field(ge=0, le=100)
    workload_max: int = Field(ge=0, le=100)
    salary_min_chf: int | None = Field(default=None, ge=0)
    salary_max_chf: int | None = Field(default=None, ge=0)
    required_languages: list[LanguageLevel] = Field(default_factory=list, max_length=12)
    required_skills: list[str] = Field(default_factory=list, max_length=15)
    preferred_skills: list[str] = Field(default_factory=list, max_length=10)
    soft_skills: list[str] = Field(default_factory=list, max_length=8)
    physical_requirements: list[str] = Field(default_factory=list, max_length=8)
    entry_barrier: Literal["none", "low", "medium", "high"]
    career_changer_friendly: bool
    education_levels: list[str] = Field(default_factory=list, max_length=8)
    key_requirements: list[str] = Field(default_factory=list, max_length=15)
    hard_blockers: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0, le=1)


class JobNormalizationResult(StrictContract):
    results: list[JobNormalization] = Field(min_length=1, max_length=12)


class JobMatch(StrictContract):
    affinity_score: int = Field(ge=0, le=100)
    affinity_analysis: str = Field(min_length=1, max_length=2000)
    worth_applying: bool
    skill_match_score: int = Field(ge=0, le=100)
    experience_match_score: int = Field(ge=0, le=100)
    intent_match_score: int = Field(ge=0, le=100)
    language_match_score: int = Field(ge=0, le=100)
    location_match_score: int = Field(ge=0, le=100)
    transferability_score: int = Field(ge=0, le=100)
    qualification_gap_score: int = Field(ge=0, le=100)
    red_flags: list[str] = Field(default_factory=list, max_length=10)


class JobMatchResult(StrictContract):
    results: list[JobMatch] = Field(min_length=1, max_length=12)
