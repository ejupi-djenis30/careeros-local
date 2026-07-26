from typing import Literal, Optional

from pydantic import BaseModel, Field


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
