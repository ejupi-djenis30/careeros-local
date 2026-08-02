from typing import Literal, Optional

from pydantic import BaseModel, Field

from backend.schemas.job import JobResponse


class CVUploadResponse(BaseModel):
    text: str
    filename: Optional[str] = None


class SearchStartResponse(BaseModel):
    message: str
    profile_id: int
    profile_source: Literal["career_vault", "uploaded_cv"]
    source_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SearchStopResponse(BaseModel):
    message: str


class AgentSearchRunRequest(BaseModel):
    name: str = Field(default="Agent search", min_length=1, max_length=160)
    query: str = Field(min_length=1, max_length=1_000)
    location: str = Field(default="", max_length=500)
    search_strategy: str = Field(default="", max_length=2_000)
    preferred_languages: list[str] = Field(default_factory=list, max_length=20)
    preferred_domains: list[str] = Field(default_factory=list, max_length=20)
    posted_within_days: int = Field(default=30, ge=1, le=365)
    max_queries: int = Field(default=4, ge=1, le=10)
    page_size: int = Field(default=20, ge=1, le=50)


class AgentSearchRunView(BaseModel):
    profile_id: int
    state: str = Field(max_length=32)
    terminal_reason: str | None = Field(default=None, max_length=80)
    returned_jobs: int = Field(ge=0, le=50)
    jobs: list[JobResponse] = Field(max_length=50)
