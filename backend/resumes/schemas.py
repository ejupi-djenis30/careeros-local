from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.career.schemas import FactType
from backend.resumes.canvas_schemas import (
    GenerationContext,
    ResumeCanvasDocument,
    canonical_uuid,
)

TemplateKind = Literal["ats", "photo"]
SyncMode = Literal["preview", "apply", "reset"]


def _default_section_order() -> list[FactType]:
    return [
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


class ResumeSectionConfig(BaseModel):
    order: list[FactType] = Field(default_factory=_default_section_order, min_length=1)
    include_summary: bool = True
    include_email: bool = True
    include_phone: bool = True
    include_location: bool = True
    include_links: bool = True

    @field_validator("order")
    @classmethod
    def unique_sections(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("section order cannot contain duplicates")
        return value


class FactContentOverride(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    subtitle: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=10_000)
    bullets: list[str] | None = Field(default=None, max_length=50)


class ResumeDraftBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    template_kind: TemplateKind
    section_config: ResumeSectionConfig = Field(default_factory=ResumeSectionConfig)
    selected_fact_ids: list[str] = Field(min_length=1, max_length=300)
    content_overrides: dict[str, FactContentOverride] = Field(default_factory=dict)
    photo_asset_id: str | None = None
    canvas_document: ResumeCanvasDocument | None = None

    @field_validator("selected_fact_ids")
    @classmethod
    def validate_fact_ids(cls, value):
        canonical = [canonical_uuid(item) for item in value]
        if len(canonical) != len(set(canonical)):
            raise ValueError("selected fact ids must be unique")
        return canonical

    @field_validator("photo_asset_id")
    @classmethod
    def validate_photo_id(cls, value):
        return canonical_uuid(value) if value else None

    @field_validator("content_overrides")
    @classmethod
    def validate_override_ids(cls, value):
        return {canonical_uuid(key): item for key, item in value.items()}

    @model_validator(mode="after")
    def validate_references(self):
        selected = set(self.selected_fact_ids)
        if set(self.content_overrides) - selected:
            raise ValueError("content overrides must reference selected career facts")
        if self.template_kind == "ats" and self.photo_asset_id:
            raise ValueError("ATS resumes cannot reference a photo")
        if self.canvas_document:
            if self.template_kind == "ats" and self.canvas_document.style.columns != 1:
                raise ValueError("ATS resumes must use a single-column canvas")
        return self


class ResumeDraftCreate(ResumeDraftBase):
    pass


class ResumeDraftUpdate(ResumeDraftBase):
    expected_revision: int = Field(ge=1)


class ResumeGenerate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    template_kind: TemplateKind = "ats"
    career_goal_id: str | None = None
    target_job_id: int | None = Field(default=None, ge=1)
    photo_asset_id: str | None = None

    @field_validator("career_goal_id", "photo_asset_id")
    @classmethod
    def validate_uuid_fields(cls, value):
        return canonical_uuid(value) if value else None

    @model_validator(mode="after")
    def validate_template(self):
        if self.template_kind == "ats" and self.photo_asset_id:
            raise ValueError("ATS resumes cannot reference a photo")
        return self


class ResumeDuplicate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)


class ResumeClaimPromote(BaseModel):
    expected_revision: int = Field(ge=1)
    expected_profile_revision: int = Field(ge=1)
    block_id: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    )


class ResumeSync(BaseModel):
    expected_revision: int = Field(ge=1)
    mode: SyncMode
    sections: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("sections")
    @classmethod
    def validate_sections(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("sync sections must be unique")
        return value


class ResumeArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    format: Literal["pdf", "docx"]
    media_type: str
    sha256: str
    byte_size: int
    created_at: datetime


class ResumeVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version_number: int
    semantic_version: str
    profile_revision: int
    selected_fact_ids: list[str]
    template_kind: TemplateKind
    renderer_version: str
    published_at: datetime
    quality_report: dict[str, Any]
    artifacts: list[ResumeArtifactResponse]


class ResumeDraftResponse(ResumeDraftBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str
    revision: int
    profile_revision: int
    generation_context: GenerationContext | None = None
    created_at: datetime
    updated_at: datetime
    versions: list[ResumeVersionResponse] = Field(default_factory=list)


class ResumeSummary(BaseModel):
    id: str
    revision: int
    title: str
    template_kind: TemplateKind
    selected_fact_count: int
    latest_version: str | None
    updated_at: datetime


class PhotoAssetResponse(BaseModel):
    id: str
    sha256: str
    byte_size: int
    media_type: Literal["image/jpeg"]
    width: int
    height: int
    profile_revision: int


class ResumeSyncSection(BaseModel):
    kind: str
    added_fact_ids: list[str] = Field(default_factory=list)
    removed_fact_ids: list[str] = Field(default_factory=list)
    changed_fact_ids: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class ResumeSyncResponse(BaseModel):
    source_profile_revision: int
    current_profile_revision: int
    sections: list[ResumeSyncSection]
    preserved_manual_fields: list[str] = Field(default_factory=list)
    applied: bool = False
    draft: ResumeDraftResponse | None = None
