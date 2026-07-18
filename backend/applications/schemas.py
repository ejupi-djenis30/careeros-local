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
ApplicationEventType = Literal["stage", "note", "task", "contact", "interview"]
InitialApplicationStage = Literal["saved", "preparing", "applied"]


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
    event_type: ApplicationEventType
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
