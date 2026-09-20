"""Persistence models for agent work requests and proposals."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.db.types import UTCDateTime
from backend.models.base_model import Base, TimestampMixin


def _uuid() -> str:
    return str(uuid.uuid4())


class AgentWorkRequest(Base, TimestampMixin):
    """An owner-requested external-agent work task and its frozen context."""

    __tablename__ = "agent_work_requests"
    __table_args__ = (
        CheckConstraint(
            "work_kind IN ('discover', 'analyze', 'materials')",
            name="ck_agent_work_kind",
        ),
        CheckConstraint(
            "state IN ('queued', 'returned', 'accepted', 'rejected', 'canceled', 'expired')",
            name="ck_agent_work_state",
        ),
        CheckConstraint("revision >= 1", name="ck_agent_work_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bound_grant_id: Mapped[str | None] = mapped_column(
        ForeignKey("automation_grants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    work_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", server_default="queued", index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    target_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_application_id: Mapped[str | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_resume_id: Mapped[str | None] = mapped_column(
        ForeignKey("resume_drafts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    preset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preset_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    locale: Mapped[str | None] = mapped_column(String(8), nullable=True)
    selected_fact_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    input_revisions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    accepted_receipt: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    proposal: Mapped[AgentProposal | None] = relationship(
        "AgentProposal",
        back_populates="request",
        uselist=False,
        cascade="all, delete-orphan",
    )


class AgentProposal(Base):
    """An unconfirmed external-agent result proposal submitted for owner review."""

    __tablename__ = "agent_proposals"
    __table_args__ = (
        CheckConstraint("contract_version >= 1", name="ck_agent_proposal_contract_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("agent_work_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submitting_grant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    client_label: Mapped[str] = mapped_column(String(120), nullable=False)
    model_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )

    request: Mapped[AgentWorkRequest] = relationship(
        "AgentWorkRequest",
        back_populates="proposal",
    )
