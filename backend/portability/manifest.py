from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Literal

from backend.portability.schemas import ArchiveManifest

ARCHIVE_FORMAT: Final[Literal["careeros-portable-archive"]] = (
    "careeros-portable-archive"
)
CURRENT_ARCHIVE_VERSION: Final = 2
SUPPORTED_ARCHIVE_VERSIONS: Final = frozenset({1, 2})
MANIFEST_MEMBER: Final = "manifest.json"
PAYLOAD_MEMBER: Final = "payload.json"

V1_TABLES: Final = (
    "candidate_profiles",
    "career_assets",
    "source_documents",
    "career_facts",
    "career_goals",
    "resume_drafts",
    "resume_versions",
    "resume_artifacts",
    "applications",
    "application_events",
    "coach_conversations",
    "coach_messages",
    "workflow_runs",
)
V2_TABLES: Final = (*V1_TABLES, "ai_executions")
TABLES_BY_VERSION: Final = {1: frozenset(V1_TABLES), 2: frozenset(V2_TABLES)}


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expected_tables(format_version: int) -> frozenset[str]:
    try:
        return TABLES_BY_VERSION[format_version]
    except KeyError as exc:
        raise ValueError(
            f"Archive version {format_version} is not supported; "
            f"supported versions are {min(SUPPORTED_ARCHIVE_VERSIONS)}–"
            f"{max(SUPPORTED_ARCHIVE_VERSIONS)}"
        ) from exc


def validate_manifest_compatibility(manifest: ArchiveManifest) -> frozenset[str]:
    expected = expected_tables(manifest.format_version)
    if set(manifest.record_counts) != expected:
        raise ValueError("The manifest contains an unsupported record count set")
    return expected
