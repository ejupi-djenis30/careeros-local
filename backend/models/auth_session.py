"""Bounded server-side authority shared by browser access and refresh tokens."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.types import UTCDateTime
from backend.models.base_model import Base, TimestampMixin


class AuthSession(Base, TimestampMixin):
    """One browser family with live access authority and one valid refresh JTI."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("slot >= 0 AND slot < 8", name="ck_auth_session_slot"),
        UniqueConstraint("user_id", "slot", name="uq_auth_session_user_slot"),
    )

    # The opaque family id is embedded in signed access and refresh tokens. It is
    # not a bearer secret; neither raw token nor either token's JTI is persisted.
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    refresh_jti_digest: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
