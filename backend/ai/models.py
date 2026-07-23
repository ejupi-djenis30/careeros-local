from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base_model import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AIExecution(Base):
    __tablename__ = "ai_executions"
    __table_args__ = (
        Index("ix_ai_executions_task_created_at", "task", "created_at"),
        Index("ix_ai_executions_model_created_at", "model_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    task: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    contract_version: Mapped[str] = mapped_column(String(20), nullable=False)
    model_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    output_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_fingerprints: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    row_input_fingerprints: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    repair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class AIEvaluationRun(Base):
    __tablename__ = "ai_evaluation_runs"
    __table_args__ = (Index("ix_ai_evaluation_dataset_model", "dataset_version", "model_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dataset_version: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    application_version: Mapped[str] = mapped_column(String(30), nullable=False)
    model_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    runtime_version: Mapped[str] = mapped_column(String(80), nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    peak_memory_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
