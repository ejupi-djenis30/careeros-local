"""Data types for parsed campaign workspace representation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any, Mapping

from backend.campaigns.archive_policy import CampaignArchiveInspection
from backend.campaigns.schemas import CampaignArtifactCategory
from backend.campaigns.xlsx_reader import TrackerApplicationRow


def freeze_value(val: Any) -> Any:
    """Recursively convert mappings to MappingProxyType and sequences to tuple."""
    if isinstance(val, (dict, MappingProxyType)):
        return MappingProxyType({k: freeze_value(v) for k, v in val.items()})
    if isinstance(val, (list, tuple)):
        return tuple(freeze_value(v) for v in val)
    return val


@dataclass(frozen=True, slots=True)
class ParsedApplication:
    source_application_id: str
    source_order: int
    title: str
    company: str
    location: str | None
    source_status: str | None
    priority: str | None
    platform: str | None
    category: str | None
    outcome: str | None
    found_at: date | None
    applied_at: date | None
    follow_up_at: date | None
    last_update_at: date | None
    next_action: str | None
    notes: str | None
    platform_url: str | None
    job_posting_url: str | None
    url: str | None
    tracker_record: Mapping[str, Any]
    provenance: Mapping[str, Any]
    packet_dir_name: str | None


@dataclass(frozen=True, slots=True)
class ParsedArtifact:
    relative_path: str
    display_name: str
    category: CampaignArtifactCategory
    source_order: int
    source_application_id: str | None
    raw_bytes: bytes
    sha256: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class ParsedCampaign:
    fingerprint: str
    inspection: CampaignArchiveInspection
    headers: tuple[str, ...]
    tracker_rows: tuple[TrackerApplicationRow, ...]
    tracker_sha256: str | None
    sanitized_tracker_bytes: bytes | None
    sanitized_tracker_sha256: str | None
    applications: tuple[ParsedApplication, ...]
    artifacts: tuple[ParsedArtifact, ...]
    dossier_count: int
    matched_count: int
    tracker_only_count: int
    dossier_only_count: int
    logical_application_count: int
    status_counts: Mapping[str, int]
    credentials_count: int
    warnings: tuple[str, ...]
    suggested_name: str
    suggested_profile_name: str | None
