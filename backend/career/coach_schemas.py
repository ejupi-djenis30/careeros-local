from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CoachMessageCreate(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=20_000)
    fact_ids: list[str] = Field(default_factory=list, max_length=30)
    job_ids: list[int] = Field(default_factory=list, max_length=20)

    @field_validator("message")
    @classmethod
    def strip_message(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("message cannot be blank")
        return value

    @field_validator("fact_ids", "job_ids")
    @classmethod
    def unique_ids(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("citation ids must be unique")
        return value


class CoachMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: Literal["user", "assistant"]
    content: str
    cited_fact_ids: list[str]
    cited_job_ids: list[int]
    model_id: str | None
    generation_metadata: dict[str, Any]
    created_at: datetime


class CoachConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str
    title: str
    messages: list[CoachMessageResponse]
    created_at: datetime
    updated_at: datetime


class CoachConversationSummary(BaseModel):
    id: str
    title: str
    message_count: int
    updated_at: datetime


class CoachReply(BaseModel):
    conversation_id: str
    message: CoachMessageResponse
