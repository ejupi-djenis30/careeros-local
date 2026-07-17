from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

CanvasSectionKind = Literal[
    "identity",
    "summary",
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
CanvasBlockKind = Literal["identity", "summary", "fact"]
ManualField = Literal["title", "subtitle", "date_range", "description", "bullets"]


def canonical_uuid(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("must be a UUID") from exc


def _plain_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if any(ord(char) < 32 and char not in {"\n", "\t"} for char in normalized):
        raise ValueError("text contains unsupported control characters")
    return normalized.strip()


class CanvasContent(BaseModel):
    title: str = Field(default="", max_length=240)
    subtitle: str = Field(default="", max_length=240)
    date_range: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=10_000)
    bullets: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("title", "subtitle", "date_range", "description")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _plain_text(value)

    @field_validator("bullets")
    @classmethod
    def validate_bullets(cls, value: list[str]) -> list[str]:
        normalized = [_plain_text(item) for item in value]
        if any(not item for item in normalized):
            raise ValueError("bullets cannot be empty")
        if any(len(item) > 1000 for item in normalized):
            raise ValueError("bullets cannot exceed 1000 characters")
        return normalized


class CanvasBlock(BaseModel):
    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    kind: CanvasBlockKind
    fact_ids: list[str] = Field(default_factory=list, max_length=100)
    visible: bool = True
    content: CanvasContent = Field(default_factory=CanvasContent)
    manual_fields: list[ManualField] = Field(default_factory=list, max_length=5)

    @field_validator("fact_ids")
    @classmethod
    def validate_fact_ids(cls, value: list[str]) -> list[str]:
        canonical = [canonical_uuid(item) for item in value]
        if len(canonical) != len(set(canonical)):
            raise ValueError("block fact ids must be unique")
        return canonical

    @field_validator("manual_fields")
    @classmethod
    def validate_manual_fields(cls, value: list[ManualField]) -> list[ManualField]:
        if len(value) != len(set(value)):
            raise ValueError("manual fields must be unique")
        return value

    @model_validator(mode="after")
    def validate_provenance_shape(self):
        if self.kind == "identity" and self.fact_ids:
            raise ValueError("identity blocks cannot reference career facts")
        return self


class CanvasSection(BaseModel):
    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    kind: CanvasSectionKind
    title: str = Field(min_length=1, max_length=120)
    visible: bool = True
    page_break_before: bool = False
    blocks: list[CanvasBlock] = Field(default_factory=list, max_length=300)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _plain_text(value)


class CanvasStyle(BaseModel):
    font_family: Literal["Helvetica", "Arial", "Georgia"] = "Helvetica"
    base_font_size: float = Field(default=10, ge=9, le=12)
    line_height: float = Field(default=1.3, ge=1, le=1.6)
    section_spacing: float = Field(default=10, ge=4, le=24)
    margin_mm: float = Field(default=18, ge=10, le=30)
    accent_color: str = Field(default="#243B53", pattern=r"^#[0-9A-Fa-f]{6}$")
    columns: Literal[1, 2] = 1


class ResumeCanvasDocument(BaseModel):
    schema_version: Literal[1] = 1
    sections: list[CanvasSection] = Field(min_length=1, max_length=20)
    style: CanvasStyle = Field(default_factory=CanvasStyle)

    @model_validator(mode="after")
    def validate_document(self):
        section_ids = [section.id for section in self.sections]
        section_kinds = [section.kind for section in self.sections]
        block_ids = [block.id for section in self.sections for block in section.blocks]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("canvas section ids must be unique")
        if len(section_kinds) != len(set(section_kinds)):
            raise ValueError("canvas section kinds must be unique")
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("canvas block ids must be unique")
        if len(block_ids) > 300:
            raise ValueError("canvas cannot contain more than 300 blocks")
        for section in self.sections:
            if section.kind == "identity" and any(
                block.kind != "identity" for block in section.blocks
            ):
                raise ValueError("identity sections can only contain identity blocks")
            if section.kind == "summary" and any(
                block.kind != "summary" for block in section.blocks
            ):
                raise ValueError("summary sections can only contain summary blocks")
            if section.kind not in {"identity", "summary"} and any(
                block.kind != "fact" for block in section.blocks
            ):
                raise ValueError("career sections can only contain fact blocks")
        return self


class GenerationContext(BaseModel):
    mode: Literal["deterministic", "local-model-assisted"] = "deterministic"
    generated_at: str | None = None
    source_profile_revision: int = Field(ge=1)
    career_goal_id: str | None = None
    target_job_id: int | None = Field(default=None, ge=1)
    target_snapshot: dict = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("career_goal_id")
    @classmethod
    def validate_goal_id(cls, value: str | None) -> str | None:
        return canonical_uuid(value) if value else None
