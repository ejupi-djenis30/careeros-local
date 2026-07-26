"""Persistence models for revocable external-agent access."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.types import UTCDateTime
from backend.models.base_model import Base, TimestampMixin


def _uuid() -> str:
    return str(uuid.uuid4())


class AutomationGrant(Base, TimestampMixin):
    """A revocable, scoped grant whose bearer secret is never persisted."""

    __tablename__ = "automation_grants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)

    def scope_set(self) -> frozenset[str]:
        raw: Any = self.scopes
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            return frozenset()
        return frozenset(raw)
