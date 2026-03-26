from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, Float, Text, DateTime, ForeignKey, JSON, UniqueConstraint, Index
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

    # Normalized shared job facts used for structured filtering and later analysis reuse.
    normalization_status = Column(String, nullable=True, default="pending", index=True)
    normalized_at = Column(DateTime(timezone=True), nullable=True, index=True)
    normalization_version = Column(Integer, nullable=True, default=1)
    normalization_source = Column(String, nullable=True)
    normalization_confidence = Column(Float, nullable=True)
    normalized_title = Column(String, nullable=True)
    normalized_role_family = Column(String, nullable=True, index=True)
    normalized_domain = Column(String, nullable=True, index=True)
    normalized_industry_sector = Column(String, nullable=True)          # granular sector within domain
    normalized_role_type = Column(String, nullable=True, index=True)    # technical | manual | administrative | creative | managerial | service | professional
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
    normalized_preferred_skills = Column(JSON, nullable=True)        # nice-to-have skills ("von Vorteil", "ideally")
    normalized_soft_skills = Column(JSON, nullable=True)             # interpersonal/organizational skills
    normalized_physical_requirements = Column(JSON, nullable=True)   # physical demands for manual jobs
    normalized_entry_barrier = Column(String, nullable=True)         # none|low|medium|high — overall accessibility
    normalized_career_changer_friendly = Column(Boolean, nullable=True)  # true if Quereinsteiger willkommen / training provided
    normalized_hard_blockers = Column(JSON, nullable=True)           # absolute non-negotiable requirements
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
            "industry_sector": self.normalized_industry_sector,
            "role_type": self.normalized_role_type,
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
            "preferred_skills": self.normalized_preferred_skills or [],
            "soft_skills": self.normalized_soft_skills or [],
            "physical_requirements": self.normalized_physical_requirements or [],
            "entry_barrier": self.normalized_entry_barrier,
            "career_changer_friendly": self.normalized_career_changer_friendly,
            "hard_blockers": self.normalized_hard_blockers or [],
            "education_levels": self.normalized_education_levels or [],
            "key_requirements": self.normalized_key_requirements or [],
            "metadata": self.normalized_metadata or {},
        }


class Job(BaseModel, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint('user_id', 'scraped_job_id', 'search_profile_id', name='uq_job_user_scraped_profile'),
        Index('ix_job_user_profile', 'user_id', 'search_profile_id'),
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

    # Dimensional sub-scores (from advanced MATCH step)
    skill_match_score = Column(Float, nullable=True)        # 0-100: technical/domain skill alignment
    experience_match_score = Column(Float, nullable=True)   # 0-100: experience level fit
    intent_match_score = Column(Float, nullable=True)       # 0-100: job fits what the user WANTS
    language_match_score = Column(Float, nullable=True)     # 0-100: language requirements fit
    location_match_score = Column(Float, nullable=True)     # 0-100: location/remote preference fit
    transferability_score = Column(Float, nullable=True)    # 0-100: how well existing skills transfer to this job
    qualification_gap_score = Column(Float, nullable=True)  # 0-100: qualification relevance for this specific job

    # Distance from search origin (km)
    distance_km = Column(Float, nullable=True)
    
    # User Action
    applied = Column(Boolean, default=False, index=True)
    
    # Relationships
    user = relationship("User", back_populates="jobs")
    search_profile = relationship("SearchProfile", back_populates="jobs")
    scraped_job = relationship("ScrapedJob", back_populates="user_jobs", lazy="joined")

    # Feature 2: Track if same ScrapedJob was applied elsewhere
    @property
    def applied_elsewhere(self) -> bool:
        """Returns True if the underlying scraped job has been marked as 'applied' in ANY other Job entry for the same user.
        
        This value is always populated via the transient attribute set by JobService.get_jobs_by_user().
        Outside that flow, returns False to avoid triggering a lazy-load N+1 query.
        """
        return getattr(self, "_applied_elsewhere_transient", False)

    @applied_elsewhere.setter
    def applied_elsewhere(self, value: bool):
        self._applied_elsewhere_transient = value

    # Pass-through properties for Pydantic JobResponse serialization (from_attributes=True)
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
    def url(self):
        return self.scraped_job.external_url if self.scraped_job else None

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

    @property
    def source_query(self):
        return self.scraped_job.source_query if self.scraped_job else None

    @property
    def normalized_job(self):
        return self.scraped_job.normalized_job_data if self.scraped_job else None
