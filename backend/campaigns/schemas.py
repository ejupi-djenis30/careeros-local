"""Pydantic schemas and DTOs for the campaign workspace feature."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CampaignArtifactCategory = Literal[
    "tracker",
    "profile",
    "goal",
    "story",
    "template",
    "vacancy",
    "cv",
    "letter",
    "email",
    "evidence",
    "image",
    "script",
    "other",
]


def map_source_status_to_stage(source_status: str | None) -> str:
    """Map source tracker status conservatively per Constitution 2.0.1 and FR-014.

    Exact audited mapping:
    - 'Saved' -> 'saved'
    - 'Preparing' -> 'preparing'
    - 'Applied' -> 'applied'
    - 'Closed' -> 'archived'
    Whitespace and case normalized. Every other or unknown value maps to 'saved'.
    """
    if not source_status:
        return "saved"
    normalized = source_status.strip().lower()
    if normalized == "closed":
        return "archived"
    if normalized == "applied":
        return "applied"
    if normalized == "preparing":
        return "preparing"
    if normalized == "saved":
        return "saved"
    return "saved"


class CampaignSampleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_application_id: str
    title: str
    company: str
    source_status: str | None = None
    provenance: list[str] = Field(default_factory=list)


class CampaignPreviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fingerprint: str
    suggested_name: str = "Legacy application campaign"
    suggested_profile_name: str | None = None
    tracker_rows: int
    dossier_count: int
    matched_count: int
    tracker_only_count: int
    dossier_only_count: int
    logical_application_count: int
    artifact_count: int
    expanded_bytes: int
    status_counts: dict[str, int] = Field(default_factory=dict)
    credential_rows_omitted: int
    warnings: list[str] = Field(default_factory=list)
    sample: list[CampaignSampleItem] = Field(default_factory=list)
    requires_profile_name: bool = False


class CampaignImportRequest(BaseModel):
    expected_fingerprint: str
    name: str | None = None
    profile_display_name: str | None = None


class CampaignSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    source_fingerprint: str
    tracker_sha256: str | None = None
    summary: dict[str, object]
    created_at: str
    updated_at: str


class CampaignImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    campaign_id: str
    fingerprint: str
    created: bool
    application_count: int
    artifact_count: int
    source_document_count: int
    task_count: int
    warning_count: int
