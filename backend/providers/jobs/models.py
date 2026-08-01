from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class SortOrder(str, Enum):
    DATE_DESC = "date_desc"
    DATE_ASC = "date_asc"
    RELEVANCE = "relevance"


class ContractType(str, Enum):
    PERMANENT = "permanent"
    TEMPORARY = "temporary"
    ANY = "any"


class WorkForm(str, Enum):
    DIVERSE = "diverse"
    HOME_OFFICE = "home_office"
    # Add others as needed


class LanguageLevel(str, Enum):
    PROFICIENT = "proficient"
    INTERMEDIATE = "intermediate"
    BASIC = "basic"
    NONE = "none"


class LanguageSkillRequest(BaseModel):
    language_code: str = Field(min_length=2, max_length=16)
    spoken_level: Optional[LanguageLevel] = None
    written_level: Optional[LanguageLevel] = None


class Coordinates(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class RadiusSearchRequest(BaseModel):
    geo_point: Coordinates
    distance: int = Field(ge=0)


class JobSearchRequest(BaseModel):
    query: str = Field(default="", max_length=1_000)
    location: str = Field(default="", max_length=500)
    canton_codes: List[str] = Field(default_factory=list, max_length=26)
    communal_codes: List[str] = Field(default_factory=list, max_length=500)
    keywords: List[str] = Field(default_factory=list, max_length=100)
    profession_codes: List[str] = Field(default_factory=list, max_length=100)
    workload_min: int = Field(default=0, ge=0, le=100)
    workload_max: int = Field(default=100, ge=0, le=100)
    contract_type: ContractType = ContractType.ANY
    company_name: Optional[str] = Field(default=None, max_length=500)
    posted_within_days: Optional[int] = Field(default=30, ge=1)
    display_restricted: bool = False
    radius: Optional[int] = Field(default=None, ge=0)
    radius_search: Optional[RadiusSearchRequest] = None
    work_forms: List[WorkForm] = Field(default_factory=list, max_length=10)
    language_skills: List[LanguageSkillRequest] = Field(default_factory=list, max_length=20)
    language: str = Field(default="en", min_length=2, max_length=16)
    page: int = Field(default=0, ge=0)
    page_size: int = Field(default=20, ge=1, le=100)
    sort: SortOrder = SortOrder.DATE_DESC

    @model_validator(mode="after")
    def validate_workload_range(self) -> "JobSearchRequest":
        if self.workload_min > self.workload_max:
            raise ValueError("workload_min cannot be greater than workload_max")
        return self


# Response Models


class CompanyInfo(BaseModel):
    name: Optional[str] = None
    street: Optional[str] = None
    house_number: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    is_agency: bool = False


class JobLocation(BaseModel):
    city: str
    postal_code: Optional[str] = None
    canton_code: Optional[str] = None
    region_code: Optional[str] = None
    communal_code: Optional[str] = None
    country_code: str = "CH"
    coordinates: Optional[Coordinates] = None
    remarks: Optional[str] = None


class EmploymentDetails(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_permanent: bool = True
    is_immediate: bool = False
    is_short_employment: bool = False
    workload_min: int = 100
    workload_max: int = 100
    work_forms: List[str] = []


class Occupation(BaseModel):
    avam_code: str
    work_experience: Optional[str] = None
    education_code: Optional[str] = None
    qualification_code: Optional[str] = None


class LanguageSkill(BaseModel):
    language_code: str
    spoken_level: Optional[str] = None
    written_level: Optional[str] = None


class ContactInfo(BaseModel):
    salutation: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class ApplicationChannel(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    form_url: Optional[str] = None
    post_address: Optional[str] = None
    additional_info: Optional[str] = None


class PublicationInfo(BaseModel):
    start_date: str
    end_date: str
    public_display: bool = True
    eures_display: bool = False
    company_anonymous: bool = False
    restricted_display: bool = False


class JobDescription(BaseModel):
    language_code: str
    title: str
    description: str


class JobListing(BaseModel):
    id: str
    source: str
    external_reference: Optional[str] = None
    stellennummer_egov: Optional[str] = None
    stellennummer_avam: Optional[str] = None
    title: str
    descriptions: List[JobDescription] = []
    external_url: Optional[str] = None
    company: Optional[CompanyInfo] = None
    location: Optional[JobLocation] = None
    number_of_positions: int = 1
    employment: Optional[EmploymentDetails] = None
    occupations: List[Occupation] = []
    language_skills: List[LanguageSkill] = []
    contact: Optional[ContactInfo] = None
    application: Optional[ApplicationChannel] = None
    publication: Optional[PublicationInfo] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    status: Optional[str] = None
    reporting_obligation: bool = False
    reporting_obligation_end_date: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None


class JobSearchResponse(BaseModel):
    items: List[JobListing]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    source: str
    search_time_ms: int
    request: JobSearchRequest


class ProviderInfo(BaseModel):
    name: str = Field(description="The unique identifier/name of the provider")
    description: str = Field(
        description="Detailed description of what kind of jobs this provider has (e.g. IT only, generalist, remote only, etc.)"
    )
    domain: str = Field(description="The domain of the job board")
    accepted_domains: List[str] = Field(
        default=["*"],
        description="Job domains this provider accepts. ['*'] = generalist (all domains). ['it'] = IT-only.",
    )


class ProviderCapabilities(BaseModel):
    supports_radius_search: bool = False
    supports_canton_filter: bool = False
    supports_profession_codes: bool = False
    supports_language_skills: bool = False
    supports_company_filter: bool = False
    supports_work_forms: bool = False
    max_page_size: int = 100
    supported_languages: List[str] = ["en"]
    supported_sort_orders: List[str] = ["date_desc"]


class ProviderStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class ProviderHealth(BaseModel):
    provider: str
    status: ProviderStatus
    latency_ms: int
    message: Optional[str] = None
