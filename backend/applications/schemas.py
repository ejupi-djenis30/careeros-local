import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.jobs.urls import normalize_job_url

ApplicationStage = Literal[
    "saved",
    "preparing",
    "applied",
    "screening",
    "interview",
    "offer",
    "accepted",
    "rejected",
    "withdrawn",
    "archived",
]
ApplicationEventType = Literal["stage", "note", "task", "contact", "interview", "preparation"]
ApplicationEventInputType = Literal["stage", "note", "task", "contact", "interview"]
InitialApplicationStage = Literal["saved", "preparing", "applied"]
ReadinessCheckStatus = Literal["pass", "warning", "blocker"]
ReadinessReportStatus = Literal["ready", "action_needed", "blocked"]

_APPLICATION_EMAIL = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}$"
)


def normalize_application_email(value: str | None) -> str | None:
    normalized = (value or "").strip() or None
    if normalized is None:
        return None
    local, separator, domain = normalized.rpartition("@")
    candidate = f"{local}{separator}{domain.lower()}"
    if not _APPLICATION_EMAIL.fullmatch(candidate):
        raise ValueError("application_email is invalid")
    return candidate


class ManualJobSnapshot(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    company: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=100_000)
    location: str | None = Field(default=None, max_length=500)
    external_url: str | None = Field(default=None, max_length=2048)
    application_url: str | None = Field(default=None, max_length=2048)
    application_email: str | None = Field(default=None, max_length=320)
    workload: str | None = Field(default=None, max_length=120)

    @field_validator("title", "company")
    @classmethod
    def non_empty_identity(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("external_url", "application_url")
    @classmethod
    def safe_url(cls, value: str | None) -> str | None:
        return normalize_job_url(value, required=False)

    _safe_application_email = field_validator("application_email")(
        normalize_application_email
    )


class ApplicationCreate(BaseModel):
    job_id: int | None = Field(default=None, gt=0)
    manual_job: ManualJobSnapshot | None = None
    resume_version_id: str | None = None
    initial_stage: InitialApplicationStage = "saved"
    note: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def exactly_one_job_source(self):
        if (self.job_id is None) == (self.manual_job is None):
            raise ValueError("Provide exactly one of job_id or manual_job")
        return self


class ApplicationEventCreate(BaseModel):
    expected_revision: int = Field(ge=1)
    event_type: ApplicationEventInputType
    stage: ApplicationStage | None = None
    occurred_at: datetime | None = None
    note: str | None = Field(default=None, max_length=10_000)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_event(self):
        if self.event_type == "stage" and self.stage is None:
            raise ValueError("stage is required for stage events")
        if self.event_type != "stage" and self.stage is not None:
            raise ValueError("stage is only valid for stage events")
        if self.event_type in {"note", "contact", "interview"} and not self.note:
            raise ValueError(f"note is required for {self.event_type} events")
        return self


class ApplicationPreparationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=240)
    company: str | None = Field(default=None, max_length=240)
    description: str | None = Field(default=None, max_length=100_000)
    application_url: str | None = Field(default=None, max_length=2048)
    application_email: str | None = Field(default=None, max_length=320)
    resume_version_id: str | None = Field(default=None, max_length=36)

    @field_validator("title", "company", "description")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("application_url")
    @classmethod
    def safe_application_url(cls, value: str | None) -> str | None:
        return normalize_job_url(value, required=False)

    @field_validator("application_email")
    @classmethod
    def validate_application_email(cls, value: str | None) -> str | None:
        return normalize_application_email(value)

    @model_validator(mode="after")
    def require_update(self):
        if self.model_fields_set == {"expected_revision"}:
            raise ValueError("Provide at least one preparation field")
        return self


class ApplicationEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: ApplicationEventType
    stage: ApplicationStage | None
    occurred_at: datetime
    note: str | None
    payload: dict[str, Any]
    created_at: datetime


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: int
    job_id: int | None
    resume_version_id: str | None
    revision: int
    current_stage: ApplicationStage
    job_snapshot: dict[str, Any]
    events: list[ApplicationEventResponse]
    created_at: datetime
    updated_at: datetime


class ApplicationSummary(BaseModel):
    id: str
    job_id: int | None
    resume_version_id: str | None
    revision: int
    current_stage: ApplicationStage
    title: str
    company: str
    location: str | None
    latest_event_at: datetime
    updated_at: datetime


class ReadinessEvidence(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    value: str = Field(max_length=500)


class ApplicationReadinessCheck(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    status: ReadinessCheckStatus
    points_awarded: int = Field(ge=0, le=100)
    points_available: int = Field(ge=1, le=100)
    evidence: list[ReadinessEvidence]
    action: str | None = Field(default=None, max_length=80)


class ApplicationReadinessReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    application_id: str
    application_revision: int = Field(ge=1)
    role_title: str
    company: str
    status: ReadinessReportStatus
    score_kind: Literal["preflight_completeness"] = "preflight_completeness"
    completeness_score: int = Field(ge=0, le=100)
    blocker_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    checks: list[ApplicationReadinessCheck]
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
