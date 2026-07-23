from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

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
ApplicationEventInputType = Literal["stage", "note", "task", "contact", "interview"]
InitialApplicationStage = Literal["saved", "preparing", "applied"]
ReadinessCheckStatus = Literal["pass", "warning", "blocker"]
ReadinessReportStatus = Literal["ready", "action_needed", "blocked"]
ApplicationTaskPriority = Literal["low", "normal", "high", "urgent"]
ApplicationTaskStatus = Literal["pending", "completed", "cancelled"]
ApplicationAgendaState = Literal[
    "overdue",
    "today",
    "upcoming",
    "unscheduled",
    "needs_action",
]

MAX_EVENT_PAYLOAD_BYTES = 64 * 1024
MAX_EVENT_PAYLOAD_DEPTH = 8
MAX_EVENT_PAYLOAD_NODES = 1_000
MAX_EVENT_PAYLOAD_STRING_BYTES = 16 * 1024
MAX_DOSSIER_INPUT_BYTES = 256 * 1024
MAX_DOSSIER_EVIDENCE_LINKS = 100
MAX_DOSSIER_UNIQUE_FACTS = 50

ApplicationEventType = Literal[
    "stage",
    "note",
    "task",
    "contact",
    "interview",
    "preparation",
    "task_created",
    "task_updated",
    "task_completed",
    "task_reopened",
    "task_cancelled",
    "dossier_published",
]

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


def _validate_bounded_json(value: Any) -> None:
    """Reject JSON shapes that are expensive to persist or replay."""

    nodes = 0
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_EVENT_PAYLOAD_NODES:
            raise ValueError("payload contains too many JSON nodes")
        if depth > MAX_EVENT_PAYLOAD_DEPTH:
            raise ValueError("payload nesting is too deep")
        if item is None or isinstance(item, (bool, int)):
            continue
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("payload numbers must be finite")
            continue
        if isinstance(item, str):
            if len(item.encode("utf-8")) > MAX_EVENT_PAYLOAD_STRING_BYTES:
                raise ValueError("payload contains an oversized string")
            continue
        if isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
            continue
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError("payload object keys must be strings")
                if len(key.encode("utf-8")) > 200:
                    raise ValueError("payload contains an oversized object key")
                stack.append((child, depth + 1))
            continue
        raise ValueError("payload must contain JSON values only")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must be valid JSON") from exc
    if len(encoded) > MAX_EVENT_PAYLOAD_BYTES:
        raise ValueError(f"payload exceeds {MAX_EVENT_PAYLOAD_BYTES} bytes")


class ManualJobSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

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

    _safe_application_email = field_validator("application_email")(normalize_application_email)


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: int | None = Field(default=None, gt=0)
    manual_job: ManualJobSnapshot | None = None
    resume_version_id: UUID | None = None
    initial_stage: InitialApplicationStage = "saved"
    note: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def exactly_one_job_source(self):
        if (self.job_id is None) == (self.manual_job is None):
            raise ValueError("Provide exactly one of job_id or manual_job")
        return self


class ApplicationEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
        return value.astimezone(timezone.utc) if value is not None else None

    @model_validator(mode="after")
    def validate_event(self):
        if self.event_type == "stage" and self.stage is None:
            raise ValueError("stage is required for stage events")
        if self.event_type != "stage" and self.stage is not None:
            raise ValueError("stage is only valid for stage events")
        if self.event_type in {"note", "contact", "interview"} and not self.note:
            raise ValueError(f"note is required for {self.event_type} events")
        _validate_bounded_json(self.payload)
        return self


def _require_timezone(value: datetime | None, field_name: str) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value.astimezone(timezone.utc) if value is not None else None


class ApplicationTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=500)
    due_at: datetime | None = None
    priority: ApplicationTaskPriority = "normal"
    reminder_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized

    @field_validator("due_at", "reminder_at")
    @classmethod
    def timezone_required(cls, value: datetime | None, info):
        return _require_timezone(value, info.field_name)

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.reminder_at is not None and self.due_at is None:
            raise ValueError("due_at is required when reminder_at is set")
        if self.reminder_at is not None and self.due_at is not None:
            if self.reminder_at > self.due_at:
                raise ValueError("reminder_at cannot be after due_at")
        return self


class ApplicationTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    due_at: datetime | None = None
    priority: ApplicationTaskPriority | None = None
    reminder_at: datetime | None = None
    status: ApplicationTaskStatus | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized

    @field_validator("due_at", "reminder_at")
    @classmethod
    def timezone_required(cls, value: datetime | None, info):
        return _require_timezone(value, info.field_name)

    @model_validator(mode="after")
    def require_update(self):
        if self.model_fields_set == {"expected_revision"}:
            raise ValueError("Provide at least one task field")
        for field in ("title", "priority", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ApplicationTaskResponse(BaseModel):
    id: str
    title: str
    status: ApplicationTaskStatus
    priority: ApplicationTaskPriority
    due_at: datetime | None
    reminder_at: datetime | None
    completed_at: datetime | None
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("due_at", "reminder_at", "completed_at", "created_at", "updated_at")
    @classmethod
    def normalize_datetimes(cls, value: datetime | None, info):
        return _require_timezone(value, info.field_name)


class DossierAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=20_000)

    @field_validator("question", "answer")
    @classmethod
    def normalize_text(cls, value: str, info) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be blank")
        return normalized


class DossierChecklistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=500)
    completed: bool = False

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("label must not be blank")
        return normalized


class DossierRequirementEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(min_length=1, max_length=2000)
    evidence_fact_ids: list[UUID] = Field(min_length=1, max_length=10)

    @field_validator("requirement")
    @classmethod
    def normalize_requirement(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("requirement must not be blank")
        return normalized

    @field_validator("evidence_fact_ids")
    @classmethod
    def unique_evidence(cls, values: list[UUID]) -> list[UUID]:
        if len(set(values)) != len(values):
            raise ValueError("Evidence fact ids must be unique per requirement")
        return values


class ApplicationDossierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    cover_letter: str | None = Field(default=None, max_length=30_000)
    answers: list[DossierAnswer] = Field(default_factory=list, max_length=25)
    checklist: list[DossierChecklistItem] = Field(default_factory=list, max_length=50)
    requirement_matrix: list[DossierRequirementEvidence] = Field(min_length=1, max_length=25)

    @field_validator("cover_letter")
    @classmethod
    def normalize_cover_letter(cls, value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None

    @model_validator(mode="after")
    def bound_aggregate_size(self):
        evidence_ids = [
            fact_id for row in self.requirement_matrix for fact_id in row.evidence_fact_ids
        ]
        if len(evidence_ids) > MAX_DOSSIER_EVIDENCE_LINKS:
            raise ValueError(
                f"dossier cannot contain more than {MAX_DOSSIER_EVIDENCE_LINKS} evidence links"
            )
        if len(set(evidence_ids)) > MAX_DOSSIER_UNIQUE_FACTS:
            raise ValueError(
                f"dossier cannot reference more than {MAX_DOSSIER_UNIQUE_FACTS} unique facts"
            )
        encoded = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOSSIER_INPUT_BYTES:
            raise ValueError(f"dossier input exceeds {MAX_DOSSIER_INPUT_BYTES} bytes")
        return self


class ApplicationDossierSummary(BaseModel):
    id: str
    version_number: int = Field(ge=1)
    application_revision: int = Field(ge=1)
    resume_version_id: str
    created_at: datetime
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    readiness_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    requirement_count: int = Field(ge=1)
    completed_checklist: int = Field(ge=0)
    checklist_total: int = Field(ge=0)


class ApplicationPreparationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=240)
    company: str | None = Field(default=None, max_length=240)
    description: str | None = Field(default=None, max_length=100_000)
    application_url: str | None = Field(default=None, max_length=2048)
    application_email: str | None = Field(default=None, max_length=320)
    resume_version_id: UUID | None = None

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
    tasks: list[ApplicationTaskResponse] = Field(default_factory=list)
    dossiers: list[ApplicationDossierSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ApplicationNextAction(BaseModel):
    """Read-model projection used by the application board.

    The detailed task timeline remains available on ``ApplicationResponse``.  Keeping this
    shape narrow makes it impossible for the board to pretend it replayed event history.
    """

    id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=500)
    due_at: datetime | None = None
    priority: ApplicationTaskPriority


class ApplicationAgendaItem(BaseModel):
    """One owned application that needs attention inside the requested agenda window."""

    application_id: str = Field(min_length=1, max_length=36)
    application_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=240)
    company: str = Field(min_length=1, max_length=240)
    current_stage: ApplicationStage
    latest_event_at: datetime
    state: ApplicationAgendaState
    next_action: ApplicationNextAction | None = None

    @model_validator(mode="after")
    def action_matches_state(self):
        if self.state == "needs_action" and self.next_action is not None:
            raise ValueError("needs_action items cannot include a next action")
        if self.state != "needs_action" and self.next_action is None:
            raise ValueError(f"{self.state} items require a next action")
        if self.next_action is not None:
            if self.state in {"overdue", "today", "upcoming"}:
                if self.next_action.due_at is None:
                    raise ValueError(f"{self.state} items require a due date")
            elif self.state == "unscheduled" and self.next_action.due_at is not None:
                raise ValueError("unscheduled items cannot include a due date")
        return self


class ApplicationAgendaResponse(BaseModel):
    """Bounded daily-work read model with explicit omission accounting."""

    generated_at: datetime
    local_day_end: datetime
    horizon_end: datetime
    active_count: int = Field(ge=0)
    visible_count: int = Field(ge=0)
    later_count: int = Field(ge=0)
    truncated_count: int = Field(ge=0)
    items: list[ApplicationAgendaItem] = Field(max_length=200)

    @model_validator(mode="after")
    def counts_are_coherent(self):
        if self.local_day_end <= self.generated_at:
            raise ValueError("local day boundary cannot end before agenda generation")
        if self.horizon_end < self.generated_at:
            raise ValueError("agenda horizon cannot end before it starts")
        if self.active_count != self.visible_count + self.later_count:
            raise ValueError("agenda active count is inconsistent")
        if self.truncated_count != self.visible_count - len(self.items):
            raise ValueError("agenda truncation count is inconsistent")
        return self


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
    next_action: ApplicationNextAction | None = None


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
