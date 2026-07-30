"""Bounded DTOs exposed by the CareerOS automation boundary."""

from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

AutomationScope = Literal[
    "system:read",
    "career:read",
    "resume:read",
    "applications:read",
]
AutomationErrorCode = Literal[
    "authentication_failed",
    "reauthentication_locked",
    "active_grant_limit",
    "grant_not_found",
    "invalid_label",
    "invalid_scopes",
    "invalid_lifetime",
]
ALL_AUTOMATION_SCOPES: tuple[AutomationScope, ...] = (
    "system:read",
    "career:read",
    "resume:read",
    "applications:read",
)


def normalize_grant_label(value: str) -> str:
    """Normalize a human label and reject invisible or control characters."""
    normalized = unicodedata.normalize("NFC", value).strip()
    if not 1 <= len(normalized) <= 120 or any(
        (
            unicodedata.category(character).startswith("C")
            or unicodedata.category(character) in {"Zl", "Zp"}
        )
        for character in normalized
    ):
        raise ValueError(
            "Grant labels must contain 1 to 120 printable characters"
        )
    return normalized


class AutomationDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrivateErrorResponse(AutomationDTO):
    detail: str


class AutomationErrorDetail(AutomationDTO):
    code: AutomationErrorCode
    message: str


class AutomationErrorResponse(AutomationDTO):
    detail: AutomationErrorDetail


class GrantView(AutomationDTO):
    id: str
    label: str
    scopes: list[AutomationScope]
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime


class GrantIssueRequest(AutomationDTO):
    label: str = Field(min_length=1, max_length=120)
    scopes: list[AutomationScope] = Field(min_length=1, max_length=4)
    lifetime_days: int = Field(default=30, ge=1, le=365)
    password: SecretStr

    @field_validator("label")
    @classmethod
    def label_must_be_printable(cls, value: str) -> str:
        return normalize_grant_label(value)

    @field_validator("scopes")
    @classmethod
    def scopes_must_be_unique(
        cls, value: list[AutomationScope]
    ) -> list[AutomationScope]:
        if len(value) != len(set(value)):
            raise ValueError("Automation scopes must be unique")
        return value


class GrantRevokeRequest(AutomationDTO):
    password: SecretStr


class GrantIssuedView(AutomationDTO):
    grant: GrantView
    token: str = Field(min_length=50, max_length=96)
    token_environment_variable: Literal["CAREEROS_MCP_TOKEN"] = "CAREEROS_MCP_TOKEN"
    warning: Literal[
        "This token is shown once. Store it in your OS credential manager and never commit it."
    ] = "This token is shown once. Store it in your OS credential manager and never commit it."


class SystemStatusView(AutomationDTO):
    schema_version: Literal["1.0"] = "1.0"
    product: Literal["CareerOS Local"] = "CareerOS Local"
    product_version: str
    access_mode: Literal["read_only"] = "read_only"
    database_revision: str
    granted_scopes: list[AutomationScope]
    available_tools: list[str]
    privacy_boundary: Literal["local vault; selected results are shared with the MCP client"] = (
        "local vault; selected results are shared with the MCP client"
    )


class LocalModelStatusView(AutomationDTO):
    required: bool
    analysis_required: bool
    available: bool
    ready: bool
    configured_model: str
    installed_model_count: int = Field(ge=0)
    error_code: str | None
    runtime: str
    privacy_boundary: Literal["local-only"] = "local-only"


class CareerSummaryView(AutomationDTO):
    profile_exists: bool
    revision: int | None = Field(default=None, ge=1)
    fact_counts: dict[str, int] = Field(default_factory=dict)
    goal_count: int = Field(default=0, ge=0)
    completeness_score: int = Field(default=0, ge=0, le=100)
    issue_count: int = Field(default=0, ge=0)
    updated_at: datetime | None = None


class NextActionView(AutomationDTO):
    id: str
    title: str = Field(max_length=500)
    due_at: datetime | None
    priority: str = Field(max_length=24)


class ApplicationSummaryView(AutomationDTO):
    id: str
    revision: int = Field(ge=1)
    current_stage: str = Field(max_length=40)
    title: str = Field(max_length=240)
    company: str = Field(max_length=240)
    location: str | None = Field(default=None, max_length=500)
    latest_event_at: datetime
    updated_at: datetime
    next_action: NextActionView | None = None


class ApplicationListView(AutomationDTO):
    items: list[ApplicationSummaryView] = Field(max_length=50)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=50)
    returned_count: int = Field(ge=0, le=50)


class ReadinessEvidenceView(AutomationDTO):
    key: str = Field(max_length=80)
    value: str = Field(max_length=500)


class ReadinessCheckView(AutomationDTO):
    id: str = Field(max_length=80)
    status: str = Field(max_length=24)
    points_awarded: int = Field(ge=0, le=100)
    points_available: int = Field(ge=1, le=100)
    evidence: list[ReadinessEvidenceView] = Field(max_length=20)
    action: str | None = Field(default=None, max_length=80)


class ApplicationReadinessView(AutomationDTO):
    application_id: str
    application_revision: int = Field(ge=1)
    role_title: str = Field(max_length=240)
    company: str = Field(max_length=240)
    status: str = Field(max_length=24)
    completeness_score: int = Field(ge=0, le=100)
    blocker_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    checks: list[ReadinessCheckView] = Field(max_length=30)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class AgendaItemView(AutomationDTO):
    application_id: str
    application_revision: int = Field(ge=1)
    title: str = Field(max_length=240)
    company: str = Field(max_length=240)
    current_stage: str = Field(max_length=40)
    latest_event_at: datetime
    state: str = Field(max_length=32)
    next_action: NextActionView | None = None


class AgendaView(AutomationDTO):
    generated_at: datetime
    local_day_end: datetime
    horizon_end: datetime
    active_count: int = Field(ge=0)
    visible_count: int = Field(ge=0)
    later_count: int = Field(ge=0)
    truncated_count: int = Field(ge=0)
    items: list[AgendaItemView] = Field(max_length=50)


class ResumeSummaryView(AutomationDTO):
    id: str
    revision: int = Field(ge=1)
    title: str = Field(max_length=200)
    template_kind: str = Field(max_length=40)
    selected_fact_count: int = Field(ge=0)
    latest_version: str | None = Field(default=None, max_length=80)
    updated_at: datetime


class ResumeVersionView(AutomationDTO):
    id: str
    draft_id: str
    draft_title: str = Field(max_length=200)
    semantic_version: str = Field(max_length=80)
    name: str = Field(max_length=240)
    published_at: datetime


class ResumeCatalogView(AutomationDTO):
    resumes: list[ResumeSummaryView] = Field(max_length=50)
    published_versions: list[ResumeVersionView] = Field(max_length=100)
