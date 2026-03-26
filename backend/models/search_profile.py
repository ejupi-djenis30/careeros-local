from sqlalchemy import Column, String, Boolean, Float, Text, Integer, ForeignKey, JSON, DateTime, Index
from sqlalchemy.orm import relationship
from backend.models.base_model import BaseModel, TimestampMixin


class SearchProfile(BaseModel, TimestampMixin):
    __tablename__ = "search_profiles"
    __table_args__ = (
        Index('ix_search_profile_user_schedule', 'user_id', 'schedule_enabled'),
    )

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, default="")
    cv_content = Column(Text)
    
    # Preferences
    role_description = Column(Text)
    search_strategy = Column(Text)
    
    # Filters
    location_filter = Column(String)
    workload_filter = Column(String)
    contract_type = Column(String, default="any")
    posted_within_days = Column(Integer, default=30)
    max_distance = Column(Integer, default=50)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    scrape_mode = Column(String, default="sequential")
    max_queries = Column(Integer, nullable=True)
    is_history = Column(Boolean, default=False)
    is_stopped = Column(Boolean, default=False)
    
    # Schedule
    schedule_enabled = Column(Boolean, default=False)
    schedule_interval_hours = Column(Integer, default=24)
    last_scheduled_run = Column(DateTime(timezone=True), nullable=True)
    
    # Advanced / Extensible preferences
    advanced_preferences = Column(JSON, nullable=True)

    # Query generation control (Feature 4)
    max_occupation_queries = Column(Integer, nullable=True)
    max_keyword_queries = Column(Integer, nullable=True)

    # Caching layer (Feature 3): saves CV summary and generated queries between runs
    cached_cv_summary = Column(Text, nullable=True)
    cached_queries = Column(JSON, nullable=True)

    # ── Normalized user / candidate profile (mirrors ScrapedJob normalization) ──
    # Extracted once per profile (CV + role_description) via LLM, cached until inputs change.
    # Used for deterministic field-vs-field matching against normalized ScrapedJob data.
    profile_normalization_status = Column(String, nullable=True, default="pending")  # pending | normalized
    profile_normalized_at = Column(DateTime(timezone=True), nullable=True)
    profile_normalization_fingerprint = Column(String, nullable=True)  # cache invalidation key
    profile_normalized_seniority = Column(String, nullable=True)        # junior | mid | senior
    profile_normalized_domain = Column(String, nullable=True)           # general | it | finance | ...
    profile_normalized_role_family = Column(String, nullable=True)      # normalised role name
    profile_normalized_qualification_level = Column(String, nullable=True)  # none | vocational | bachelor | master | phd
    profile_normalized_experience_years = Column(Integer, nullable=True)    # candidate's total years
    profile_normalized_languages = Column(JSON, nullable=True)          # [{code, level}, ...]
    profile_normalized_skills = Column(JSON, nullable=True)             # ["Python", "React", ...]

    # ── Search intent — what the user WANTS to find (may differ from CV domain) ──
    # Derived from role_description + search_strategy at the same LLM call as candidate profile.
    # The structured filtering layer uses these as the PRIMARY comparison axis against jobs.
    profile_search_intent_domain = Column(String, nullable=True)             # target domain
    profile_search_intent_seniority = Column(String, nullable=True)          # target seniority
    profile_search_intent_role_family = Column(String, nullable=True)        # target role
    profile_search_intent_qualification_level = Column(String, nullable=True) # acceptable qualification
    profile_search_intent_skills = Column(JSON, nullable=True)               # target skills
    profile_search_intent_open_to_unrelated = Column(Boolean, nullable=True, default=False)  # cross-domain search
    profile_search_intent_keywords = Column(JSON, nullable=True)             # free-form intent keywords

    user = relationship("User", back_populates="profiles")
    jobs = relationship("Job", back_populates="search_profile", cascade="all, delete-orphan")

    def _advanced_pref(self, key: str, default=None):
        if isinstance(self.advanced_preferences, dict):
            return self.advanced_preferences.get(key, default)
        return default

    @property
    def preferred_languages(self):
        return self._advanced_pref("preferred_languages")

    @property
    def preferred_domains(self):
        return self._advanced_pref("preferred_domains")

    @property
    def remote_only(self):
        return self._advanced_pref("remote_only", False)

    @property
    def salary_min_chf(self):
        return self._advanced_pref("salary_min_chf")

    @property
    def workload_min(self):
        return self._advanced_pref("workload_min")

    @property
    def workload_max(self):
        return self._advanced_pref("workload_max")

    @property
    def hard_max_distance_km(self):
        return self._advanced_pref("hard_max_distance_km")
