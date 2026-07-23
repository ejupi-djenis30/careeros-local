from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import (
    JSON,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.types import UTCDateTime
from backend.models.base_model import Base, TimestampMixin


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot_value(context, key: str, fallback: str) -> str:
    snapshot = context.get_current_parameters().get("job_snapshot")
    if not isinstance(snapshot, dict):
        return fallback
    return str(snapshot.get(key) or fallback)


class Application(Base, TimestampMixin):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_application_user_job"),
        Index("ix_applications_user_updated_at", "user_id", "updated_at"),
        Index(
            "ix_applications_user_stage_next_action",
            "user_id",
            "current_stage",
            "next_action_at",
        ),
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
    job_title: Mapped[str] = mapped_column(
        String(240),
        nullable=False,
        default=lambda context: _snapshot_value(context, "title", "Untitled role")[:240],
    )
    job_company: Mapped[str] = mapped_column(
        String(240),
        nullable=False,
        default=lambda context: _snapshot_value(context, "company", "Unknown company")[:240],
    )
    job_location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    latest_event_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=_utcnow
    )
    # Queryable projection of the append-only task timeline. The task itself
    # remains fully represented by immutable events; these fields only make the
    # next concrete action inexpensive to show on the board.
    next_action_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    next_action_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    next_action_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    next_action_priority: Mapped[str | None] = mapped_column(String(20), nullable=True)

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
    event_type: Mapped[
        Literal[
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
    ] = mapped_column(String(30), nullable=False)
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
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    application: Mapped[Application] = relationship("Application", back_populates="events")


@event.listens_for(ApplicationEvent, "before_update")
def _application_events_are_immutable(_mapper, _connection, _target) -> None:
    raise ValueError("Application timeline events are append-only")
