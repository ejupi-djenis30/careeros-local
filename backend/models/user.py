from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base_model import BaseModel, TimestampMixin

if TYPE_CHECKING:
    from backend.models.job import Job
    from backend.models.search_profile import SearchProfile

VAULT_STATE_READY = "ready"
VAULT_STATE_RESET_PENDING = "reset_pending"
VAULT_STATE_RESTORE_PENDING = "restore_pending"
VAULT_STATE_ERASURE_PENDING = "erasure_pending"
VAULT_LIFECYCLE_STATES = (
    VAULT_STATE_READY,
    VAULT_STATE_RESET_PENDING,
    VAULT_STATE_RESTORE_PENDING,
    VAULT_STATE_ERASURE_PENDING,
)


class User(BaseModel, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "vault_lifecycle_state IN "
            "('ready', 'reset_pending', 'restore_pending', 'erasure_pending')",
            name="ck_user_vault_lifecycle_state",
        ),
        CheckConstraint(
            "(vault_lifecycle_state = 'restore_pending' "
            "AND vault_maintenance_fingerprint IS NOT NULL) OR "
            "(vault_lifecycle_state != 'restore_pending' "
            "AND vault_maintenance_fingerprint IS NULL)",
            name="ck_user_vault_maintenance_fingerprint",
        ),
        CheckConstraint(
            "vault_maintenance_fingerprint IS NULL OR "
            "(length(vault_maintenance_fingerprint) = 64 "
            "AND vault_maintenance_fingerprint = lower(vault_maintenance_fingerprint) "
            "AND vault_maintenance_fingerprint NOT GLOB '*[^0-9a-f]*')",
            name="ck_user_vault_maintenance_fingerprint_shape",
        ),
    )

    username: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True, unique=True, index=True)
    vault_lifecycle_state: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=VAULT_STATE_READY,
        server_default=VAULT_STATE_READY,
        index=True,
    )
    vault_maintenance_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # ─── Phase 2: Behavioural preference signals ──────────────────────────────
    # Aggregated from applied/dismissed patterns. Recomputed by preference_service.
    # Schema: {
    #   "preferred_domains": {"it": 0.9, "engineering": 0.7, ...},
    #   "avoided_domains": {"hospitality": 0.8, ...},
    #   "preferred_role_types": {"technical": 0.85, ...},
    #   "preferred_skills": ["python", "react", ...],
    #   "preferred_seniority": "senior",
    #   "typical_salary_range": {"min": 100000, "max": 140000},
    #   "typical_distance_km": 30.0,
    #   "dealbreaker_patterns": ["night shifts", ...],
    #   "signal_count": 42,          # total jobs with signals
    #   "last_computed_at": "ISO8601"
    # }
    preference_signals: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    preference_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    jobs: Mapped[list[Job]] = relationship("Job", back_populates="user")
    profiles: Mapped[list[SearchProfile]] = relationship("SearchProfile", back_populates="user")
