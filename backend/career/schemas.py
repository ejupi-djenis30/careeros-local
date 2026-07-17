from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from backend.career.goal_schemas import CareerGoalPayload
from backend.career.payloads import PAYLOAD_SCHEMAS, CareerPreferences, safe_url

FactType = Literal[
    "experience",
    "education",
    "project",
    "skill",
    "language",
    "certification",
    "achievement",
    "volunteering",
    "publication",
    "link",
]
VerificationStatus = Literal["draft", "confirmed", "imported"]


class CareerFactInput(BaseModel):
    id: str | None = None
    fact_type: FactType
    position: int = Field(default=0, ge=0, le=10_000)
    payload: dict[str, Any]
    source_document_id: str | None = None
    source_locator: str | None = Field(default=None, max_length=255)
    confidence: float | None = Field(default=None, ge=0, le=1)
    verification_status: VerificationStatus = "draft"

    @model_validator(mode="after")
    def validate_payload(self):
        schema = PAYLOAD_SCHEMAS[self.fact_type]
        self.payload = schema.model_validate(self.payload).model_dump(
            mode="json", exclude_none=True
        )
        return self


class CareerGoalInput(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=160)
    is_primary: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload(self):
        self.payload = CareerGoalPayload.model_validate(self.payload).model_dump(
            mode="json", exclude_none=True
        )
        return self


class CareerProfileWrite(BaseModel):
    expected_revision: int = Field(default=0, ge=0)
    display_name: str = Field(min_length=1, max_length=160)
    headline: str = Field(default="", max_length=240)
    summary: str = Field(default="", max_length=20_000)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    location: dict[str, Any] = Field(default_factory=dict)
    birth_date: date | None = None
    nationality: str | None = Field(default=None, max_length=120)
    work_authorization: list[str] = Field(default_factory=list, max_length=100)
    website: str | None = None
    linkedin: str | None = None
    github: str | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)
    facts: list[CareerFactInput] = Field(default_factory=list, max_length=1000)
    goals: list[CareerGoalInput] = Field(default_factory=list, max_length=100)

    @field_validator("website", "linkedin", "github")
    @classmethod
    def validate_urls(cls, value):
        return safe_url(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        if value and ("@" not in value or value.startswith("@") or value.endswith("@")):
            raise ValueError("email is invalid")
        return value

    @model_validator(mode="after")
    def validate_collections(self):
        fact_ids = [item.id for item in self.facts if item.id]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("fact ids must be unique")
        known_fact_ids = set(fact_ids)
        evidence_ids = {
            evidence_id
            for item in self.facts
            if item.fact_type == "skill"
            for evidence_id in item.payload.get("evidence_fact_ids", [])
        }
        if evidence_ids - known_fact_ids:
            raise ValueError("skill evidence facts must belong to the same profile")
        goal_ids = [item.id for item in self.goals if item.id]
        if len(goal_ids) != len(set(goal_ids)):
            raise ValueError("goal ids must be unique")
        if sum(1 for item in self.goals if item.is_primary) > 1:
            raise ValueError("only one career goal can be primary")
        self.preferences = CareerPreferences.model_validate(self.preferences).model_dump(
            mode="json", exclude_none=True
        )
        return self


class CareerFactResponse(CareerFactInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime


class CareerGoalResponse(CareerGoalInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime


class CareerProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: int
    revision: int
    display_name: str
    headline: str
    summary: str
    email: str | None
    phone: str | None
    location: dict[str, Any]
    birth_date: date | None
    nationality: str | None
    work_authorization: list[str]
    website: str | None
    linkedin: str | None
    github: str | None
    photo_asset_id: str | None
    preferences: dict[str, Any]
    facts: list[CareerFactResponse]
    goals: list[CareerGoalResponse]
    created_at: datetime
    updated_at: datetime


class CareerProfileSummary(BaseModel):
    id: str
    revision: int
    display_name: str
    headline: str
    fact_counts: dict[str, int]
    goal_count: int
    updated_at: datetime


class SourceDocumentResponse(BaseModel):
    id: str
    asset_id: str
    original_name: str
    media_type: str
    sha256: str
    byte_size: int
    document_type: str
    extracted_characters: int
    created_at: datetime
