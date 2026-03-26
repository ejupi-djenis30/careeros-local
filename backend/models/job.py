from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, Float, Text, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.models.base_model import BaseModel, TimestampMixin


class ScrapedJob(BaseModel, TimestampMixin):
    __tablename__ = "scraped_jobs"
    __table_args__ = (
        UniqueConstraint('platform', 'platform_job_id', name='uq_scraped_job_platform_id'),
    )

    platform = Column(String, index=True, nullable=False)
    platform_job_id = Column(String, index=True, nullable=False)
    
    title = Column(String, index=True, nullable=False)
    company = Column(String, index=True, nullable=False)
    description = Column(Text)
    location = Column(String, index=True)
    
    # Generic URLs
    external_url = Column(String, index=True, nullable=False)
    application_url = Column(String, nullable=True)
    application_email = Column(String, nullable=True)
    
    workload = Column(String)
    publication_date = Column(DateTime(timezone=True))
    
    # For provider-specific details (JobRoom, SwissDevJobs, etc)
    raw_metadata = Column(JSON, nullable=True)
    
    # LLM-generated summary used by the relevance filter step (opt-in)
    summary = Column(Text, nullable=True)

    # Normalized shared job facts used for structured filtering and later analysis reuse.
    normalization_status = Column(String, nullable=True, default="pending", index=True)
    normalized_at = Column(DateTime(timezone=True), nullable=True, index=True)
    normalization_version = Column(Integer, nullable=True, default=1)
    normalization_source = Column(String, nullable=True)
    normalization_confidence = Column(Float, nullable=True)
    normalized_title = Column(String, nullable=True)
    normalized_role_family = Column(String, nullable=True, index=True)
    normalized_domain = Column(String, nullable=True, index=True)
    normalized_seniority = Column(String, nullable=True, index=True)
    normalized_employment_mode = Column(String, nullable=True, index=True)
    normalized_contract_type = Column(String, nullable=True, index=True)
    normalized_qualification_level = Column(String, nullable=True, index=True)
    normalized_experience_min_years = Column(Integer, nullable=True)
    normalized_experience_max_years = Column(Integer, nullable=True)
    normalized_workload_min = Column(Integer, nullable=True)
    normalized_workload_max = Column(Integer, nullable=True)
    normalized_salary_min_chf = Column(Integer, nullable=True)
    normalized_salary_max_chf = Column(Integer, nullable=True)
    normalized_required_languages = Column(JSON, nullable=True)
    normalized_required_skills = Column(JSON, nullable=True)
    normalized_education_levels = Column(JSON, nullable=True)
    normalized_key_requirements = Column(JSON, nullable=True)
    normalized_metadata = Column(JSON, nullable=True)
    
    # Keep track of where it originally came from (optional but useful)
    source_query = Column(String, nullable=True)

    # Relationships
    user_jobs = relationship("Job", back_populates="scraped_job", cascade="all, delete-orphan")

    @property
    def normalized_job_data(self):
        return {
            "status": self.normalization_status,
            "normalized_at": self.normalized_at,
            "version": self.normalization_version,
            "source": self.normalization_source,
            "confidence": self.normalization_confidence,
            "title": self.normalized_title,
            "role_family": self.normalized_role_family,
            "domain": self.normalized_domain,
            "seniority": self.normalized_seniority,
            "employment_mode": self.normalized_employment_mode,
            "contract_type": self.normalized_contract_type,
            "qualification_level": self.normalized_qualification_level,
            "experience_min_years": self.normalized_experience_min_years,
            "experience_max_years": self.normalized_experience_max_years,
            "workload_min": self.normalized_workload_min,
            "workload_max": self.normalized_workload_max,
            "salary_min_chf": self.normalized_salary_min_chf,
            "salary_max_chf": self.normalized_salary_max_chf,
            "required_languages": self.normalized_required_languages or [],
            "required_skills": self.normalized_required_skills or [],
            "education_levels": self.normalized_education_levels or [],
            "key_requirements": self.normalized_key_requirements or [],
            "metadata": self.normalized_metadata or {},
        }


class Job(BaseModel, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint('user_id', 'scraped_job_id', 'search_profile_id', name='uq_job_user_scraped_profile'),
    )

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    search_profile_id = Column(Integer, ForeignKey("search_profiles.id"), nullable=True, index=True)
    scraped_job_id = Column(Integer, ForeignKey("scraped_jobs.id"), nullable=False, index=True)
    
    # Metadata
    is_scraped = Column(Boolean, default=False)
    
    # AI Analysis (User-specific match)
    affinity_score = Column(Float)
    affinity_analysis = Column(Text)
    worth_applying = Column(Boolean, default=False)
    
    # Distance from search origin (km)
    distance_km = Column(Float, nullable=True)
    
    # User Action
    applied = Column(Boolean, default=False)
    
    # Relationships
    user = relationship("User", back_populates="jobs")
    search_profile = relationship("SearchProfile", back_populates="jobs")
    scraped_job = relationship("ScrapedJob", back_populates="user_jobs", lazy="joined")

    # Feature 2: Track if same ScrapedJob was applied elsewhere
    @property
    def applied_elsewhere(self) -> bool:
        """Returns True if the underlying scraped job has been marked as 'applied' in ANY other Job entry for the same user."""
        if hasattr(self, "_applied_elsewhere_transient"):
            return self._applied_elsewhere_transient
        if not self.scraped_job:
            return False
        return any(uj.applied for uj in self.scraped_job.user_jobs if uj.id != self.id and uj.user_id == self.user_id)

    @applied_elsewhere.setter
    def applied_elsewhere(self, value: bool):
        self._applied_elsewhere_transient = value

    def __init__(self, **kwargs):
        scraped_fields = {
            "title", "company", "description", "location", "external_url", 
            "application_url", "application_email", "workload", 
            "publication_date", "platform", "platform_job_id", 
            "raw_metadata", "source_query", "summary",
            "normalization_status", "normalized_at", "normalization_version",
            "normalization_source", "normalization_confidence", "normalized_title",
            "normalized_role_family", "normalized_domain", "normalized_seniority",
            "normalized_employment_mode", "normalized_contract_type",
            "normalized_qualification_level", "normalized_experience_min_years",
            "normalized_experience_max_years", "normalized_workload_min",
            "normalized_workload_max", "normalized_salary_min_chf",
            "normalized_salary_max_chf", "normalized_required_languages",
            "normalized_required_skills", "normalized_education_levels",
            "normalized_key_requirements", "normalized_metadata"
        }
        user_kwargs = {}
        scraped_kwargs = {}
        for k, v in kwargs.items():
            if k in scraped_fields or k == "url":
                target_key = "external_url" if k == "url" else k
                scraped_kwargs[target_key] = v
            else:
                user_kwargs[k] = v
        
        # If we have scraped info but no linked object, create it (compatibility mode)
        if scraped_kwargs and "scraped_job_id" not in user_kwargs and "scraped_job" not in user_kwargs:
            import uuid
            if "platform" not in scraped_kwargs: scraped_kwargs["platform"] = "manual"
            if "platform_job_id" not in scraped_kwargs: scraped_kwargs["platform_job_id"] = str(uuid.uuid4())
            if "title" not in scraped_kwargs: scraped_kwargs["title"] = "Untitled"
            if "company" not in scraped_kwargs: scraped_kwargs["company"] = "Unknown"
            if "external_url" not in scraped_kwargs: scraped_kwargs["external_url"] = "http://unknown"
            user_kwargs["scraped_job"] = ScrapedJob(**scraped_kwargs)
            
        super().__init__(**user_kwargs)

    def _ensure_scraped_job(self):
        if self.scraped_job is None:
            import uuid
            self.scraped_job = ScrapedJob(
                platform="manual",
                platform_job_id=str(uuid.uuid4()),
                title="Untitled",
                company="Unknown",
                external_url="http://unknown"
            )

    # Pass-through properties for backward compatibility
    @property
    def title(self):
        return self.scraped_job.title if self.scraped_job else None
    @title.setter
    def title(self, value):
        self._ensure_scraped_job()
        self.scraped_job.title = value

    @property
    def company(self):
        return self.scraped_job.company if self.scraped_job else None
    @company.setter
    def company(self, value):
        self._ensure_scraped_job()
        self.scraped_job.company = value

    @property
    def description(self):
        return self.scraped_job.description if self.scraped_job else None
    @description.setter
    def description(self, value):
        self._ensure_scraped_job()
        self.scraped_job.description = value

    @property
    def location(self):
        return self.scraped_job.location if self.scraped_job else None
    @location.setter
    def location(self, value):
        self._ensure_scraped_job()
        self.scraped_job.location = value

    @property
    def url(self):
        return self.scraped_job.external_url if self.scraped_job else None
    @url.setter
    def url(self, value):
        self._ensure_scraped_job()
        self.scraped_job.external_url = value

    @property
    def external_url(self):
        return self.scraped_job.external_url if self.scraped_job else None
    @external_url.setter
    def external_url(self, value):
        self._ensure_scraped_job()
        self.scraped_job.external_url = value

    @property
    def application_url(self):
        return self.scraped_job.application_url if self.scraped_job else None
    @application_url.setter
    def application_url(self, value):
        self._ensure_scraped_job()
        self.scraped_job.application_url = value

    @property
    def application_email(self):
        return self.scraped_job.application_email if self.scraped_job else None
    @application_email.setter
    def application_email(self, value):
        self._ensure_scraped_job()
        self.scraped_job.application_email = value

    @property
    def workload(self):
        return self.scraped_job.workload if self.scraped_job else None
    @workload.setter
    def workload(self, value):
        self._ensure_scraped_job()
        self.scraped_job.workload = value

    @property
    def publication_date(self):
        return self.scraped_job.publication_date if self.scraped_job else None
    @publication_date.setter
    def publication_date(self, value):
        self._ensure_scraped_job()
        self.scraped_job.publication_date = value

    @property
    def platform(self):
        return self.scraped_job.platform if self.scraped_job else None
    @platform.setter
    def platform(self, value):
        self._ensure_scraped_job()
        self.scraped_job.platform = value

    @property
    def platform_job_id(self):
        return self.scraped_job.platform_job_id if self.scraped_job else None
    @platform_job_id.setter
    def platform_job_id(self, value):
        self._ensure_scraped_job()
        self.scraped_job.platform_job_id = value

    @property
    def raw_metadata(self):
        return self.scraped_job.raw_metadata if self.scraped_job else None
    @raw_metadata.setter
    def raw_metadata(self, value):
        self._ensure_scraped_job()
        self.scraped_job.raw_metadata = value

    @property
    def source_query(self):
        return self.scraped_job.source_query if self.scraped_job else None
    @source_query.setter
    def source_query(self, value):
        self._ensure_scraped_job()
        self.scraped_job.source_query = value

    @property
    def normalized_job(self):
        return self.scraped_job.normalized_job_data if self.scraped_job else None
