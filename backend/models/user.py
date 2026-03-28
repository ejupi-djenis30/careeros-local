from sqlalchemy import JSON, Column, DateTime, String
from sqlalchemy.orm import relationship

from backend.models.base_model import BaseModel, TimestampMixin


class User(BaseModel, TimestampMixin):
    __tablename__ = "users"

    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    email = Column(String, nullable=True, unique=True, index=True)
    supabase_id = Column(String, nullable=True, unique=True, index=True)

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
    preference_signals = Column(JSON, nullable=True)
    preference_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    jobs = relationship("Job", back_populates="user")
    profiles = relationship("SearchProfile", back_populates="user")
