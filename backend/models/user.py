from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base_model import BaseModel, TimestampMixin

if TYPE_CHECKING:
    from backend.models.job import Job
    from backend.models.search_profile import SearchProfile


class User(BaseModel, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True, unique=True, index=True)

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
