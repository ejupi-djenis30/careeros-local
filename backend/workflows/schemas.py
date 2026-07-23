from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

WorkflowStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class WorkflowEnqueue(BaseModel):
    workflow_type: str = Field(min_length=1, max_length=60, pattern=r"^[a-z][a-z0-9_.-]*$")
    idempotency_key: str = Field(min_length=1, max_length=160)
    payload: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = Field(default=3, ge=1, le=20)


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: int
    workflow_type: str
    idempotency_key: str
    status: WorkflowStatus
    checkpoint: dict[str, Any]
    result_reference: dict[str, Any]
    progress: float
    attempt_count: int
    max_attempts: int
    error_code: str | None
    lease_expires_at: datetime | None
    cancel_requested_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_validator("progress")
    @classmethod
    def valid_progress(cls, value):
        if not 0 <= value <= 1:
            raise ValueError("progress must be between 0 and 1")
        return value
