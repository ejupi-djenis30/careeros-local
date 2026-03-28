from typing import Optional

from pydantic import BaseModel


class CVUploadResponse(BaseModel):
    text: str
    filename: Optional[str] = None


class SearchStartResponse(BaseModel):
    message: str
    profile_id: int


class SearchStopResponse(BaseModel):
    message: str
