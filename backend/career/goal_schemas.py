from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CompensationTarget(BaseModel):
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    minimum: float | None = Field(default=None, ge=0)
    maximum: float | None = Field(default=None, ge=0)
    period: Literal["hour", "day", "month", "year"] = "year"

    @model_validator(mode="after")
    def validate_range(self):
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("compensation minimum cannot exceed maximum")
        return self


class SkillGap(BaseModel):
    skill: str = Field(min_length=1, max_length=160)
    current_level: Literal["none", "learning", "working", "advanced", "expert"]
    target_level: Literal["learning", "working", "advanced", "expert"]
    action: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_progression(self):
        levels = {"none": 0, "learning": 1, "working": 2, "advanced": 3, "expert": 4}
        if levels[self.target_level] <= levels[self.current_level]:
            raise ValueError("target skill level must exceed current level")
        return self


class CareerMilestone(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    title: str = Field(min_length=1, max_length=240)
    status: Literal["planned", "in_progress", "achieved", "cancelled"] = "planned"
    target_date: date | None = None
    completed_date: date | None = None
    progress_percent: int = Field(default=0, ge=0, le=100)
    evidence_fact_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_completion(self):
        if self.status == "achieved" and self.completed_date is None:
            raise ValueError("achieved milestones require completed_date")
        if self.status == "achieved":
            self.progress_percent = 100
        elif self.completed_date is not None:
            raise ValueError("only achieved milestones can have completed_date")
        return self


class CareerAction(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    title: str = Field(min_length=1, max_length=240)
    kind: Literal[
        "research", "networking", "learning", "portfolio", "application", "interview", "other"
    ] = "other"
    status: Literal["planned", "in_progress", "completed", "cancelled"] = "planned"
    due_date: date | None = None
    completed_date: date | None = None
    notes: str = Field(default="", max_length=3000)
    linked_fact_ids: list[str] = Field(default_factory=list, max_length=100)
    linked_job_ids: list[str] = Field(default_factory=list, max_length=100)
    linked_application_ids: list[str] = Field(default_factory=list, max_length=100)
    linked_learning_activity_ids: list[str] = Field(default_factory=list, max_length=100)
    linked_resume_version_ids: list[str] = Field(default_factory=list, max_length=100)
    learning_resource_url: str | None = Field(default=None, max_length=2048)

    @field_validator(
        "linked_fact_ids",
        "linked_job_ids",
        "linked_application_ids",
        "linked_learning_activity_ids",
        "linked_resume_version_ids",
    )
    @classmethod
    def validate_unique_links(cls, value: list[str], info) -> list[str]:
        normalized = [str(item).strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError(f"{info.field_name} cannot contain empty values")
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{info.field_name} must be unique")
        return normalized

    @field_validator("learning_resource_url")
    @classmethod
    def validate_learning_url(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        from urllib.parse import urlsplit

        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("learning_resource_url must use http or https")
        if parsed.username or parsed.password:
            raise ValueError("learning_resource_url must not include credentials")
        return parsed.geturl()

    @model_validator(mode="after")
    def validate_completion(self):
        if self.status == "completed" and self.completed_date is None:
            raise ValueError("completed actions require completed_date")
        if self.status != "completed" and self.completed_date is not None:
            raise ValueError("only completed actions can have completed_date")
        return self


class ProgressNote(BaseModel):
    recorded_at: datetime
    text: str = Field(min_length=1, max_length=2000)
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    evidence_fact_ids: list[str] = Field(default_factory=list, max_length=100)


class CareerGoalPayload(BaseModel):
    status: Literal["draft", "active", "paused", "achieved", "abandoned"] = "active"
    priority: int = Field(default=3, ge=1, le=5)
    target_roles: list[str] = Field(default_factory=list, max_length=50)
    target_industries: list[str] = Field(default_factory=list, max_length=50)
    target_locations: list[str] = Field(default_factory=list, max_length=50)
    target_seniority: list[
        Literal["intern", "junior", "mid", "senior", "staff", "lead", "manager", "director", "executive"]
    ] = Field(default_factory=list, max_length=20)
    work_modes: list[Literal["onsite", "hybrid", "remote"]] = Field(
        default_factory=list, max_length=3
    )
    contract_types: list[
        Literal["permanent", "temporary", "contract", "freelance", "internship", "apprenticeship"]
    ] = Field(default_factory=list, max_length=10)
    compensation: CompensationTarget | None = None
    rationale: str = Field(default="", max_length=5000)
    start_date: date | None = None
    target_date: date | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    success_criteria: list[str] = Field(default_factory=list, max_length=50)
    must_haves: list[str] = Field(default_factory=list, max_length=50)
    deal_breakers: list[str] = Field(default_factory=list, max_length=50)
    skill_gaps: list[SkillGap] = Field(default_factory=list, max_length=100)
    milestones: list[CareerMilestone] = Field(default_factory=list, max_length=100)
    actions: list[CareerAction] = Field(default_factory=list, max_length=300)
    progress_notes: list[ProgressNote] = Field(default_factory=list, max_length=200)

    @field_validator(
        "target_roles",
        "target_industries",
        "target_locations",
        "success_criteria",
        "must_haves",
        "deal_breakers",
    )
    @classmethod
    def normalize_unique_strings(cls, value: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = item.strip()
            if not normalized:
                raise ValueError("list values cannot be empty")
            key = normalized.casefold()
            if key in seen:
                raise ValueError("list values must be unique")
            seen.add(key)
            result.append(normalized)
        return result

    @model_validator(mode="after")
    def validate_plan(self):
        if self.start_date and self.target_date and self.target_date < self.start_date:
            raise ValueError("target_date cannot precede start_date")
        milestone_ids = [item.id for item in self.milestones]
        if len(milestone_ids) != len(set(milestone_ids)):
            raise ValueError("milestone ids must be unique")
        action_ids = [item.id for item in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("action ids must be unique")
        learning_activity_ids = {
            item.id for item in self.actions if item.kind == "learning"
        }
        for action in self.actions:
            linked_learning = set(action.linked_learning_activity_ids)
            if linked_learning - learning_activity_ids:
                raise ValueError(
                    "linked learning activities must be learning actions in the same goal"
                )
            if action.id in linked_learning:
                raise ValueError("an action cannot link to itself as a learning activity")
        if self.target_date:
            if any(item.target_date and item.target_date > self.target_date for item in self.milestones):
                raise ValueError("milestone target_date cannot exceed goal target_date")
            if any(item.due_date and item.due_date > self.target_date for item in self.actions):
                raise ValueError("action due_date cannot exceed goal target_date")
        if self.status == "achieved":
            if self.progress_percent not in (None, 100):
                raise ValueError("achieved goals require 100 percent progress")
            self.progress_percent = 100
        elif self.progress_percent is None:
            progress_values = [item.progress_percent for item in self.milestones]
            progress_values.extend(
                100 if item.status == "completed" else 50 if item.status == "in_progress" else 0
                for item in self.actions
                if item.status != "cancelled"
            )
            self.progress_percent = (
                round(sum(progress_values) / len(progress_values)) if progress_values else 0
            )
        return self
