from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base_model import Base, TimestampMixin


def _uuid() -> str:
    return str(uuid.uuid4())


class ResumeDraft(Base, TimestampMixin):
    __tablename__ = "resume_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    profile_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    template_kind: Mapped[Literal["ats", "photo"]] = mapped_column(String(20), nullable=False)
    section_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    selected_fact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    content_overrides: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    canvas_document: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    generation_context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    photo_asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("career_assets.id", ondelete="SET NULL"), nullable=True
    )

    versions: Mapped[list[ResumeVersion]] = relationship(
        "ResumeVersion",
        back_populates="draft",
        cascade="all, delete-orphan",
        order_by="ResumeVersion.published_at.desc()",
        lazy="selectin",
    )


class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    __table_args__ = (
        UniqueConstraint("draft_id", "version_number", name="uq_resume_version_draft_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    draft_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resume_drafts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    semantic_version: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, default="Published version"
    )
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_fact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    template_kind: Mapped[Literal["ats", "photo"]] = mapped_column(String(20), nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(30), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quality_report: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    draft: Mapped[ResumeDraft] = relationship("ResumeDraft", back_populates="versions")
    artifacts: Mapped[list[ResumeArtifact]] = relationship(
        "ResumeArtifact",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="ResumeArtifact.format",
        lazy="selectin",
    )


class ResumeArtifact(Base):
    __tablename__ = "resume_artifacts"
    __table_args__ = (
        UniqueConstraint("version_id", "format", name="uq_resume_artifact_version_format"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    format: Mapped[Literal["pdf", "docx"]] = mapped_column(String(10), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    version: Mapped[ResumeVersion] = relationship("ResumeVersion", back_populates="artifacts")


@event.listens_for(ResumeVersion, "before_update")
@event.listens_for(ResumeArtifact, "before_update")
def _published_resume_is_immutable(_mapper, _connection, _target) -> None:
    raise ValueError("Published resume versions and artifacts are immutable")
