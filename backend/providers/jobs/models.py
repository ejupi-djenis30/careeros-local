from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime

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
    language_code: str
    spoken_level: Optional[LanguageLevel] = None
    written_level: Optional[LanguageLevel] = None

class Coordinates(BaseModel):
    lat: float
    lon: float

class RadiusSearchRequest(BaseModel):
    geo_point: Coordinates
    distance: int

class JobSearchRequest(BaseModel):
    query: str = ""
    location: str = ""
    canton_codes: List[str] = []
    communal_codes: List[str] = []
    keywords: List[str] = []
    profession_codes: List[str] = []
    workload_min: int = 0
    workload_max: int = 100
    contract_type: ContractType = ContractType.ANY
    company_name: Optional[str] = None
    posted_within_days: Optional[int] = 30
    display_restricted: bool = False
    radius: Optional[int] = None
    radius_search: Optional[RadiusSearchRequest] = None
    work_forms: List[WorkForm] = []
    language_skills: List[LanguageSkillRequest] = []
    language: str = "en"
    page: int = 0
    page_size: int = 20
    sort: SortOrder = SortOrder.DATE_DESC

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

class DateModel(BaseModel): # Placeholder for Occupation
    pass

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
    description: str = Field(description="Detailed description of what kind of jobs this provider has (e.g. IT only, generalist, remote only, etc.)")
    domain: str = Field(description="The domain of the job board")
    accepted_domains: List[str] = Field(
        default=["*"],
        description="Job domains this provider accepts. ['*'] = generalist (all domains). ['it'] = IT-only."
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
