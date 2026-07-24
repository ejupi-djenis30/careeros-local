from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ArchiveEntry(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)

    @field_validator("path")
    @classmethod
    def safe_member_path(cls, value: str) -> str:
        if value.startswith(("/", "\\")) or "\\" in value or ".." in value.split("/"):
            raise ValueError("archive member path is unsafe")
        return value


class ArchiveManifest(BaseModel):
    format: Literal["careeros-portable-archive"]
    format_version: Literal[1, 2, 3, 4]
    created_at: datetime
    owner_scope: Literal["career-vault"]
    record_counts: dict[str, int]
    entries: list[ArchiveEntry]


class RestoreResponse(BaseModel):
    format_version: int
    archive_sha256: str
    restored_records: dict[str, int]
    restored_files: int


ArchiveVerificationCode = Literal[
    "manifest_verified",
    "members_verified",
    "records_verified",
    "relationships_verified",
    "file_bindings_verified",
]
ArchiveWarningCode = Literal[
    "archive_not_encrypted",
    "archive_not_authenticated",
    "ai_output_requires_revalidation",
    "restore_requires_empty_vault",
    "restore_target_conflict",
]


class ArchiveInspection(BaseModel):
    status: Literal["valid"] = "valid"
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_bytes: int = Field(ge=1)
    format_version: int = Field(ge=1)
    created_at: datetime
    record_counts: dict[str, int]
    total_records: int = Field(ge=0)
    file_count: int = Field(ge=0)
    file_bytes: int = Field(ge=0)
    compatible: bool
    restorable: bool
    verification_codes: list[ArchiveVerificationCode]
    warning_codes: list[ArchiveWarningCode]
