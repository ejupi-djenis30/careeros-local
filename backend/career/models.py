from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base_model import Base, TimestampMixin


def _uuid() -> str:
    return str(uuid.uuid4())


class CandidateProfile(Base, TimestampMixin):
    __tablename__ = "candidate_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    headline: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    location: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(120), nullable=True)
    work_authorization: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    website: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    linkedin: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    github: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    photo_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    facts: Mapped[list[CareerFact]] = relationship(
        "CareerFact",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="CareerFact.position, CareerFact.created_at",
        lazy="selectin",
    )
    goals: Mapped[list[CareerGoal]] = relationship(
        "CareerGoal",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="CareerGoal.created_at",
        lazy="selectin",
    )
    assets: Mapped[list[CareerAsset]] = relationship(
        "CareerAsset", back_populates="profile", cascade="all, delete-orphan", lazy="selectin"
    )
    source_documents: Mapped[list[SourceDocument]] = relationship(
        "SourceDocument",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CareerAsset(Base, TimestampMixin):
    __tablename__ = "career_assets"
    __table_args__ = (
        UniqueConstraint("profile_id", "sha256", "kind", name="uq_asset_profile_sha_kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    normalized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    profile: Mapped[CandidateProfile] = relationship("CandidateProfile", back_populates="assets")
    source_document: Mapped[SourceDocument | None] = relationship(
        "SourceDocument", back_populates="asset", uselist=False
    )


class SourceDocument(Base, TimestampMixin):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("career_assets.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    extracted_text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    profile: Mapped[CandidateProfile] = relationship(
        "CandidateProfile", back_populates="source_documents"
    )
    asset: Mapped[CareerAsset] = relationship("CareerAsset", back_populates="source_document")
    facts: Mapped[list[CareerFact]] = relationship("CareerFact", back_populates="source_document")


class CareerFact(Base, TimestampMixin):
    __tablename__ = "career_facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fact_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("source_documents.id", ondelete="SET NULL"), nullable=True
    )
    source_locator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped[CandidateProfile] = relationship("CandidateProfile", back_populates="facts")
    source_document: Mapped[SourceDocument | None] = relationship(
        "SourceDocument", back_populates="facts"
    )


class CareerGoal(Base, TimestampMixin):
    __tablename__ = "career_goals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    profile: Mapped[CandidateProfile] = relationship("CandidateProfile", back_populates="goals")
