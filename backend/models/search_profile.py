from sqlalchemy import Column, String, Boolean, Float, Text, Integer, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from backend.models.base_model import BaseModel, TimestampMixin


class SearchProfile(BaseModel, TimestampMixin):
    __tablename__ = "search_profiles"

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
