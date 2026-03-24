from sqlalchemy import Column, String, Boolean, Float, Text, DateTime, ForeignKey, JSON, Integer, UniqueConstraint
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
    
    # Keep track of where it originally came from (optional but useful)
    source_query = Column(String)
    
    # Relationships
    user_jobs = relationship("Job", back_populates="scraped_job", cascade="all, delete-orphan")


class Job(BaseModel, TimestampMixin):
    __tablename__ = "jobs"

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
    
    user = relationship("User", back_populates="jobs")
    search_profile = relationship("SearchProfile", backref="jobs")
    scraped_job = relationship("ScrapedJob", back_populates="user_jobs", lazy="joined")

    # Pass-through properties to maintain backward compatibility with API schemas
    @property
    def title(self):
        return self.scraped_job.title if self.scraped_job else None

    @property
    def company(self):
        return self.scraped_job.company if self.scraped_job else None

    @property
    def description(self):
        return self.scraped_job.description if self.scraped_job else None

    @property
    def location(self):
        return self.scraped_job.location if self.scraped_job else None

    @property
    def external_url(self):
        return self.scraped_job.external_url if self.scraped_job else None

    @property
    def application_url(self):
        return self.scraped_job.application_url if self.scraped_job else None

    @property
    def application_email(self):
        return self.scraped_job.application_email if self.scraped_job else None

    @property
    def workload(self):
        return self.scraped_job.workload if self.scraped_job else None

    @property
    def publication_date(self):
        return self.scraped_job.publication_date if self.scraped_job else None

    @property
    def platform(self):
        return self.scraped_job.platform if self.scraped_job else None

    @property
    def platform_job_id(self):
        return self.scraped_job.platform_job_id if self.scraped_job else None

    @property
    def raw_metadata(self):
        return self.scraped_job.raw_metadata if self.scraped_job else None
