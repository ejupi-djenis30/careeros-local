from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
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


class Application(Base, TimestampMixin):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_application_user_job"),
        Index("ix_applications_user_updated_at", "user_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resume_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("resume_versions.id", ondelete="SET NULL"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_stage: Mapped[
        Literal[
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
    ] = mapped_column(String(30), nullable=False, default="saved", index=True)
    job_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    events: Mapped[list[ApplicationEvent]] = relationship(
        "ApplicationEvent",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationEvent.occurred_at, ApplicationEvent.created_at",
        lazy="selectin",
    )


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[Literal["stage", "note", "task", "contact", "interview"]] = (
        mapped_column(String(30), nullable=False)
    )
    stage: Mapped[
        Literal[
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
        | None
    ] = mapped_column(String(30), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    application: Mapped[Application] = relationship("Application", back_populates="events")


@event.listens_for(ApplicationEvent, "before_update")
def _application_events_are_immutable(_mapper, _connection, _target) -> None:
    raise ValueError("Application timeline events are append-only")
