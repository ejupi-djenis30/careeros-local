"""Persistence for declarative user-owned job providers."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base_model import Base, TimestampMixin


def _uuid() -> str:
    return str(uuid.uuid4())


class JobProviderConfiguration(Base, TimestampMixin):
    """A revisioned declaration; it never contains executable provider code."""

    __tablename__ = "job_provider_configurations"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_job_provider_configuration_user_key"),
        Index("ix_job_provider_configurations_user_enabled", "user_id", "enabled"),
        CheckConstraint("revision >= 1", name="ck_job_provider_configuration_revision"),
        CheckConstraint(
            "((adapter_kind IN ('json', 'html') AND native_adapter_id IS NULL "
            "AND request_config IS NOT NULL AND extraction_config IS NOT NULL) OR "
            "(adapter_kind = 'native' AND native_adapter_id IS NOT NULL "
            "AND request_config IS NULL AND extraction_config IS NULL))",
            name="ck_job_provider_configuration_adapter_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    adapter_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    native_adapter_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_pack_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_pack_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    request_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    extraction_config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    capabilities_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
