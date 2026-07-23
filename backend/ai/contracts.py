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
    claims: list[GroundedClaim] = Field(min_length=1, max_length=12)
    fact_citations: list[UuidString] = Field(default_factory=list, max_length=32)
    job_citations: list[int] = Field(default_factory=list, max_length=32)
    confidence: float = Field(ge=0, le=1)
    missing_evidence: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="before")
    @classmethod
    def materialize_omitted_aggregate_citations(cls, value):
        """Derive redundant citation indexes when a compact model omits them.

        The grounded claims are authoritative.  Small local models commonly omit
        fields that have schema defaults even when the prompt repeats them.  An
        explicitly supplied aggregate remains subject to the exact-match validator
        below, so a model cannot use this normalization to hide a mismatch.
        """
        if not isinstance(value, dict) or not isinstance(value.get("claims"), list):
            return value

        normalized = dict(value)
        if "fact_citations" not in normalized:
            normalized["fact_citations"] = list(
                dict.fromkeys(
                    fact_id
                    for claim in normalized["claims"]
                    if isinstance(claim, dict)
                    for fact_id in claim.get("fact_ids", [])
                )
            )
        if "job_citations" not in normalized:
            normalized["job_citations"] = list(
                dict.fromkeys(
                    job_id
                    for claim in normalized["claims"]
                    if isinstance(claim, dict)
                    for job_id in claim.get("job_ids", [])
                )
            )
        return normalized

    @model_validator(mode="after")
    def citations_cover_claims(self) -> "CoachResult":
        claim_facts = {item for claim in self.claims for item in claim.fact_ids}
        claim_jobs = {item for claim in self.claims for item in claim.job_ids}
        if claim_facts != set(self.fact_citations):
            raise ValueError("aggregate fact citations must exactly match grounded claims")
        if claim_jobs != set(self.job_citations):
            raise ValueError("aggregate job citations must exactly match grounded claims")
        if len(set(self.fact_citations)) != len(self.fact_citations):
            raise ValueError("fact citations must be unique")
        if len(set(self.job_citations)) != len(self.job_citations):
            raise ValueError("job citations must be unique")
        return self


class ResumeTailoringClaim(GroundedClaim):
    section: Literal["headline", "summary", "experience", "skills", "projects", "education"]
    operation: Literal["keep", "rewrite", "add", "remove"]
    source_text: str | None = Field(default=None, max_length=800)
    matched_keywords: list[str] = Field(default_factory=list, max_length=12)


class ResumeRequirementGap(StrictContract):
    requirement: str = Field(min_length=1, max_length=240)
    job_ids: list[int] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def unique_positive_job_ids(self) -> "ResumeRequirementGap":
        if len(set(self.job_ids)) != len(self.job_ids) or any(item < 1 for item in self.job_ids):
            raise ValueError("resume gaps require unique positive job identifiers")
        return self


class ResumeTailoringResult(StrictContract):
    claims: list[ResumeTailoringClaim] = Field(min_length=1, max_length=20)
    gaps: list[ResumeRequirementGap] = Field(default_factory=list, max_length=12)
    fact_citations: list[UuidString] = Field(default_factory=list, max_length=32)
    job_citations: list[int] = Field(default_factory=list, max_length=32)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def citations_cover_tailoring(self) -> "ResumeTailoringResult":
        claim_facts = {item for claim in self.claims for item in claim.fact_ids}
        claim_jobs = {item for claim in self.claims for item in claim.job_ids}
        gap_jobs = {item for gap in self.gaps for item in gap.job_ids}
        if not claim_facts <= set(self.fact_citations):
            raise ValueError("aggregate fact citations do not cover every resume claim")
        if not (claim_jobs | gap_jobs) <= set(self.job_citations):
            raise ValueError("aggregate job citations do not cover resume claims and gaps")
        if len(set(self.fact_citations)) != len(self.fact_citations):
            raise ValueError("resume fact citations must be unique")
        if len(set(self.job_citations)) != len(self.job_citations):
            raise ValueError("resume job citations must be unique")
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


class MatchEvidence(StrictContract):
    type: Literal[
        "skill",
        "experience",
        "intent",
        "language",
        "location",
        "transferability",
        "qualification",
    ]
    job_evidence_id: str = Field(pattern=r"^job:\d+$", max_length=32)
    candidate_evidence_id: Literal["candidate:profile"]
    job_quote_id: str = Field(pattern=r"^job:\d+:[a-z_]+:\d+$", max_length=64)
    candidate_quote_id: str = Field(pattern=r"^candidate:profile:[a-z_]+:\d+$", max_length=80)

    @model_validator(mode="after")
    def quote_ids_match_dimension_and_document(self) -> "MatchEvidence":
        if not self.job_quote_id.startswith(
            f"{self.job_evidence_id}:{self.type}:"
        ) or not self.candidate_quote_id.startswith(f"{self.candidate_evidence_id}:{self.type}:"):
            raise ValueError("match quote IDs must belong to the declared evidence dimension")
        return self


class MatchAnalysis(StrictContract):
    evidence_citations: list[MatchEvidence] = Field(min_length=1, max_length=7)


class JobMatch(StrictContract):
    skill_match_score: int = Field(ge=0, le=100)
    experience_match_score: int = Field(ge=0, le=100)
    intent_match_score: int = Field(ge=0, le=100)
    language_match_score: int = Field(ge=0, le=100)
    location_match_score: int = Field(ge=0, le=100)
    transferability_score: int = Field(ge=0, le=100)
    qualification_gap_score: int = Field(ge=0, le=100)


class JobMatchResult(StrictContract):
    results: list[JobMatch] = Field(min_length=1, max_length=12)

    @model_validator(mode="before")
    @classmethod
    def wrap_single_score_row(cls, value):
        """Accept one compact score row from small local models.

        The public contract remains a batch object. Some small constrained models
        omit that single redundant wrapper when only one job is supplied, so the
        server restores it before strict validation. No score field or extra model
        claim is synthesized here.
        """
        score_fields = {
            "skill_match_score",
            "experience_match_score",
            "intent_match_score",
            "language_match_score",
            "location_match_score",
            "transferability_score",
            "qualification_gap_score",
        }
        if isinstance(value, dict) and "results" not in value and score_fields <= value.keys():
            return {"results": [dict(value)]}
        return value


class JobCritique(StrictContract):
    affinity_score: int = Field(ge=0, le=100)
    worth_applying: bool
    critique_notes: str = Field(min_length=1, max_length=800)
    score_changed: bool


class JobCritiqueResult(StrictContract):
    results: list[JobCritique] = Field(min_length=1, max_length=12)


class JobRerank(StrictContract):
    final_score: int = Field(ge=0, le=100)
    rank: int = Field(ge=1, le=100)
    rank_notes: str = Field(min_length=1, max_length=500)


class JobRerankResult(StrictContract):
    results: list[JobRerank] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_ranks(self) -> "JobRerankResult":
        ranks = [item.rank for item in self.results]
        if len(ranks) != len(set(ranks)):
            raise ValueError("comparative job ranks must be unique")
        return self
