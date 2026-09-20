"""SQLAlchemy persistence models for Campaign Workspace (Feature 003)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.types import UTCDateTime
from backend.models.base_model import Base, TimestampMixin


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


ALLOWED_ARTIFACT_CATEGORIES = (
    "tracker",
    "profile",
    "goal",
    "story",
    "template",
    "vacancy",
    "cv",
    "letter",
    "email",
    "evidence",
    "image",
    "script",
    "other",
)

_CATEGORIES_SQL = ", ".join(f"'{c}'" for c in ALLOWED_ARTIFACT_CATEGORIES)
XLSX_MAX_CELL_CHARS = 32_767



class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint("user_id", "source_fingerprint", name="uq_campaigns_user_fingerprint"),
        Index("ix_campaigns_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # Digest of the user-visible name, retained separately from the aggregate
    # summary so idempotent retries can detect name-row corruption.
    name_integrity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tracker_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    applications: Mapped[list[CampaignApplication]] = relationship(
        "CampaignApplication",
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="CampaignApplication.source_order",
    )
    artifacts: Mapped[list[CampaignArtifact]] = relationship(
        "CampaignArtifact",
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="CampaignArtifact.source_order",
    )


class CampaignApplication(Base):
    __tablename__ = "campaign_applications"
    __table_args__ = (
        UniqueConstraint("campaign_id", "source_application_id", name="uq_campaign_app_campaign_source_id"),
        UniqueConstraint("campaign_id", "application_id", name="uq_campaign_app_campaign_app_id"),
        Index("ix_campaign_applications_campaign_source_order", "campaign_id", "source_order"),
        Index("ix_campaign_applications_campaign_priority", "campaign_id", "priority"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_application_id: Mapped[str] = mapped_column(String(120), nullable=False)
    source_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(60), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    found_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    applied_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    follow_up_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_update_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    tracker_record: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    campaign: Mapped[Campaign] = relationship("Campaign", back_populates="applications")
    application: Mapped[Any] = relationship("Application")


class CampaignArtifact(Base):
    __tablename__ = "campaign_artifacts"
    __table_args__ = (
        UniqueConstraint("campaign_id", "relative_path", name="uq_campaign_artifacts_campaign_path"),
        Index("ix_campaign_artifacts_campaign_source_order", "campaign_id", "source_order"),
        CheckConstraint(
            f"category IN ({_CATEGORIES_SQL})",
            name="ck_campaign_artifacts_category",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("career_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    source_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        server_default=func.now(),
        default=_utcnow,
        nullable=False,
    )

    campaign: Mapped[Campaign] = relationship("Campaign", back_populates="artifacts")
    application: Mapped[Any] = relationship("Application")
    asset: Mapped[Any] = relationship("CareerAsset")
