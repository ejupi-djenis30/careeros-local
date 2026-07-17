from __future__ import annotations

from datetime import date
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.career.goal_schemas import CompensationTarget


def _normalized_unique_strings(value: list[str], label: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = item.strip()
        if not normalized:
            raise ValueError(f"{label} values cannot be empty")
        key = normalized.casefold()
        if key in seen:
            raise ValueError(f"{label} values must be unique")
        seen.add(key)
        result.append(normalized)
    return result


def safe_url(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    parsed = urlsplit(str(value).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("url must not include credentials")
    return parsed.geturl()


class DateRangePayload(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot precede start_date")
        return self


class ExperiencePayload(DateRangePayload):
    role: str = Field(min_length=1, max_length=200)
    organization: str = Field(min_length=1, max_length=200)
    employment_type: Literal[
        "permanent", "temporary", "contract", "freelance", "internship", "apprenticeship"
    ] | None = None
    industry: str | None = Field(default=None, max_length=160)
    location: str | None = Field(default=None, max_length=200)
    work_mode: Literal["onsite", "hybrid", "remote"] | None = None
    description: str = Field(default="", max_length=10_000)
    responsibilities: list[str] = Field(default_factory=list, max_length=50)
    achievements: list[str] = Field(default_factory=list, max_length=50)
    metrics: list[str] = Field(default_factory=list, max_length=50)
    technologies: list[str] = Field(default_factory=list, max_length=100)
    skills: list[str] = Field(default_factory=list, max_length=100)
    team_size: int | None = Field(default=None, ge=1, le=100_000)
    current: bool = False

    @field_validator("responsibilities", "achievements", "metrics", "technologies", "skills")
    @classmethod
    def normalize_lists(cls, value: list[str], info) -> list[str]:
        return _normalized_unique_strings(value, info.field_name)

    @model_validator(mode="after")
    def validate_current_role(self):
        if self.current and self.end_date:
            raise ValueError("current experience cannot have an end_date")
        return self


class EducationPayload(DateRangePayload):
    institution: str = Field(min_length=1, max_length=240)
    qualification: str = Field(min_length=1, max_length=240)
    field: str | None = Field(default=None, max_length=240)
    grade: str | None = Field(default=None, max_length=80)
    description: str = Field(default="", max_length=5000)
    thesis: str | None = Field(default=None, max_length=500)
    activities: list[str] = Field(default_factory=list, max_length=50)
    coursework: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("activities", "coursework")
    @classmethod
    def normalize_lists(cls, value: list[str], info) -> list[str]:
        return _normalized_unique_strings(value, info.field_name)


class ProjectPayload(DateRangePayload):
    name: str = Field(min_length=1, max_length=240)
    role: str | None = Field(default=None, max_length=200)
    organization: str | None = Field(default=None, max_length=240)
    client: str | None = Field(default=None, max_length=240)
    description: str = Field(default="", max_length=10_000)
    achievements: list[str] = Field(default_factory=list, max_length=50)
    technologies: list[str] = Field(default_factory=list, max_length=100)
    skills: list[str] = Field(default_factory=list, max_length=100)
    url: str | None = None

    _validate_url = field_validator("url")(safe_url)

    @field_validator("achievements", "technologies", "skills")
    @classmethod
    def normalize_lists(cls, value: list[str], info) -> list[str]:
        return _normalized_unique_strings(value, info.field_name)


class SkillPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=120)
    level: Literal["learning", "working", "advanced", "expert"] | None = None
    years: float | None = Field(default=None, ge=0, le=80)
    last_used_date: date | None = None
    evidence_fact_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("evidence_fact_ids")
    @classmethod
    def validate_evidence_ids(cls, value: list[str]) -> list[str]:
        try:
            canonical = [str(UUID(item)) for item in value]
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("skill evidence ids must be UUIDs") from exc
        if len(canonical) != len(set(canonical)):
            raise ValueError("skill evidence ids must be unique")
        return canonical


class LanguagePayload(BaseModel):
    language: str = Field(min_length=1, max_length=100)
    level: Literal["A1", "A2", "B1", "B2", "C1", "C2", "native"]


class CertificationPayload(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    issuer: str | None = Field(default=None, max_length=240)
    issued_on: date | None = None
    expires_on: date | None = None
    credential_id: str | None = Field(default=None, max_length=240)
    url: str | None = None

    _validate_url = field_validator("url")(safe_url)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.issued_on and self.expires_on and self.expires_on < self.issued_on:
            raise ValueError("expires_on cannot precede issued_on")
        return self


class AchievementPayload(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=5000)
    details: list[str] = Field(default_factory=list, max_length=50)
    metric_value: float | None = None
    metric_unit: str | None = Field(default=None, max_length=80)
    context: str | None = Field(default=None, max_length=500)
    achieved_on: date | None = None

    @field_validator("details")
    @classmethod
    def validate_details(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("achievement details cannot be empty")
        if any(len(item) > 1000 for item in normalized):
            raise ValueError("achievement details cannot exceed 1000 characters")
        return normalized


class VolunteeringPayload(DateRangePayload):
    title: str = Field(min_length=1, max_length=240)
    organization: str | None = Field(default=None, max_length=240)
    description: str = Field(default="", max_length=5000)
    achievements: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("achievements")
    @classmethod
    def normalize_achievements(cls, value: list[str]) -> list[str]:
        return _normalized_unique_strings(value, "achievements")


class PublicationPayload(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    publisher: str | None = Field(default=None, max_length=240)
    published_on: date | None = None
    description: str = Field(default="", max_length=5000)
    url: str | None = None

    _validate_url = field_validator("url")(safe_url)


class LinkPayload(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    url: str

    _validate_url = field_validator("url")(safe_url)


class AwardPayload(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    issuer: str | None = Field(default=None, max_length=240)
    awarded_on: date | None = None
    description: str = Field(default="", max_length=5000)
    url: str | None = None

    _validate_url = field_validator("url")(safe_url)


class MembershipPayload(DateRangePayload):
    organization: str = Field(min_length=1, max_length=240)
    role: str = Field(default="Member", min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    current: bool = False
    url: str | None = None

    _validate_url = field_validator("url")(safe_url)

    @model_validator(mode="after")
    def validate_current_membership(self):
        if self.current and self.end_date:
            raise ValueError("current membership cannot have an end_date")
        return self


class ReferencePayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    relationship: str = Field(min_length=1, max_length=240)
    organization: str | None = Field(default=None, max_length=240)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    notes: str = Field(default="", max_length=2000)
    permission_to_contact: bool = False

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value and ("@" not in value or value.startswith("@") or value.endswith("@")):
            raise ValueError("email is invalid")
        return value

    @model_validator(mode="after")
    def validate_contact_permission(self):
        if self.permission_to_contact and not (self.email or self.phone):
            raise ValueError("permission to contact requires an email or phone")
        return self


class PortfolioPayload(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    url: str
    description: str = Field(default="", max_length=5000)
    skills: list[str] = Field(default_factory=list, max_length=100)

    _validate_url = field_validator("url")(safe_url)

    @field_validator("skills")
    @classmethod
    def normalize_skills(cls, value: list[str]) -> list[str]:
        return _normalized_unique_strings(value, "skills")


class CareerPreferences(BaseModel):
    model_config = ConfigDict(extra="allow")

    target_roles: list[str] = Field(default_factory=list, max_length=50)
    target_industries: list[str] = Field(default_factory=list, max_length=50)
    preferred_locations: list[str] = Field(default_factory=list, max_length=50)
    preferred_work_modes: list[Literal["onsite", "hybrid", "remote"]] = Field(
        default_factory=list, max_length=3
    )
    contract_types: list[
        Literal[
            "permanent",
            "temporary",
            "contract",
            "freelance",
            "internship",
            "apprenticeship",
        ]
    ] = Field(default_factory=list, max_length=10)
    workload_min: int | None = Field(default=None, ge=0, le=100)
    workload_max: int | None = Field(default=None, ge=0, le=100)
    salary_min_chf: float | None = Field(default=None, ge=0)
    salary: CompensationTarget | None = None
    preferred_languages: list[str] = Field(default_factory=list, max_length=50)
    hard_max_distance_km: float | None = Field(default=None, ge=0)
    remote_only: bool = False
    relocation: Literal["no", "within_country", "international", "open"] = "no"
    travel_max_percent: int | None = Field(default=None, ge=0, le=100)
    notice_period_days: int | None = Field(default=None, ge=0, le=730)
    available_from: date | None = None
    company_sizes: list[Literal["startup", "small", "medium", "large", "enterprise"]] = Field(
        default_factory=list, max_length=5
    )
    company_values: list[str] = Field(default_factory=list, max_length=50)
    desired_benefits: list[str] = Field(default_factory=list, max_length=50)
    excluded_companies: list[str] = Field(default_factory=list, max_length=100)
    excluded_industries: list[str] = Field(default_factory=list, max_length=100)
    job_source_consents: dict[
        Literal["job_room", "swissdevjobs", "adecco"], bool
    ] = Field(default_factory=dict, max_length=3)

    @field_validator(
        "target_roles",
        "target_industries",
        "preferred_locations",
        "preferred_languages",
        "company_values",
        "desired_benefits",
        "excluded_companies",
        "excluded_industries",
    )
    @classmethod
    def normalize_lists(cls, value: list[str], info) -> list[str]:
        return _normalized_unique_strings(value, info.field_name)

    @model_validator(mode="after")
    def validate_workload(self):
        if (
            self.workload_min is not None
            and self.workload_max is not None
            and self.workload_min > self.workload_max
        ):
            raise ValueError("workload_min cannot exceed workload_max")
        if self.remote_only and self.preferred_work_modes and "remote" not in self.preferred_work_modes:
            raise ValueError("remote_only conflicts with preferred_work_modes")
        return self


PAYLOAD_SCHEMAS: dict[str, type[BaseModel]] = {
    "experience": ExperiencePayload,
    "education": EducationPayload,
    "project": ProjectPayload,
    "skill": SkillPayload,
    "language": LanguagePayload,
    "certification": CertificationPayload,
    "achievement": AchievementPayload,
    "link": LinkPayload,
    "volunteering": VolunteeringPayload,
    "publication": PublicationPayload,
    "award": AwardPayload,
    "membership": MembershipPayload,
    "reference": ReferencePayload,
    "portfolio": PortfolioPayload,
}
