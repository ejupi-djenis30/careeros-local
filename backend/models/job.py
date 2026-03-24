from sqlalchemy import Column, Integer, String, Boolean, Float, Text, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.base import Base


class ScrapedJob(Base):
    __tablename__ = "scraped_jobs"
    __table_args__ = (
        UniqueConstraint('platform', 'platform_job_id', name='uq_scraped_job_platform_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
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
    
    # Keep track of where it originally came from (optional but useful)
    source_query = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user_jobs = relationship("Job", back_populates="scraped_job", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
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
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="jobs")
    search_profile = relationship("SearchProfile", backref="jobs")
    scraped_job = relationship("ScrapedJob", back_populates="user_jobs", lazy="joined")

    def __init__(self, **kwargs):
        scraped_fields = {
            "title", "company", "description", "location", "external_url", 
            "application_url", "application_email", "workload", 
            "publication_date", "platform", "platform_job_id", 
            "raw_metadata", "source_query", "summary"
        }
        user_kwargs = {}
        scraped_kwargs = {}
        for k, v in kwargs.items():
            if k in scraped_fields or k == "url":
                target_key = "external_url" if k == "url" else k
                scraped_kwargs[target_key] = v
            else:
                user_kwargs[k] = v
        
        # Special case: 'url' in scraped_kwargs might have been set by the loop above
        if "url" in scraped_kwargs:
            scraped_kwargs["external_url"] = scraped_kwargs.pop("url")

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
