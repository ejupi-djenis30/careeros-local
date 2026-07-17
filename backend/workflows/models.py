from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base_model import Base, TimestampMixin


def _uuid() -> str:
    return str(uuid.uuid4())


class WorkflowRun(Base, TimestampMixin):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "workflow_type", "idempotency_key", name="uq_workflow_idempotency"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[Literal["queued", "running", "succeeded", "failed", "cancelled"]] = (
        mapped_column(String(20), nullable=False, default="queued", index=True)
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result_reference: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
