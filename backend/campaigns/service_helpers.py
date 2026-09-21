"""Helper functions and types for campaign import service."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.campaigns.import_planner_types import PlannedCampaign
from backend.campaigns.parser_types import ParsedCampaign
from backend.career.asset_publication import (
    remove_asset_publication_journal,
)
from backend.career.models import (
    CandidateProfile,
    CareerAsset,
)
from backend.career.repository import CareerProfileRepository
from backend.career.source_parsing import PreparedSourceDocument, prepare_source_document
from backend.models.user import User
from backend.storage.atomic import (
    durable_unlink,
    resolve_data_path,
)

_SAFE_MEDIA_TYPE_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".html": "text/plain",
    ".htm": "text/plain",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".py": "text/plain",
    ".sh": "text/plain",
    ".js": "text/plain",
    ".css": "text/plain",
    ".json": "application/json",
}


class CampaignImportError(ValueError):
    """Raised on campaign import validation, preflight, or transaction failure."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def get_safe_media_type(filename: str) -> str:
    """Return a deterministic safe media type; never permits executable or active HTML types."""
    ext = Path(filename).suffix.lower()
    return _SAFE_MEDIA_TYPE_MAP.get(ext, "application/octet-stream")


def to_json_safe(val: Any) -> Any:
    """Recursively convert dates/datetimes to ISO strings and immutable containers to lists/dicts."""
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if isinstance(val, Mapping):
        return {str(k): to_json_safe(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set, frozenset)):
        return [to_json_safe(v) for v in val]
    return val


def owner_scoped_uuid(identity_scope: str, fingerprint: str, entity_tag: str, item_id: str = "") -> str:
    """Derive deterministic UUID5 scoped to the specific owner, campaign, and entity."""
    urn = f"urn:careeros:campaign:{identity_scope}:{fingerprint}:{entity_tag}"
    if item_id:
        urn = f"{urn}:{item_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, urn))


def validate_import_preflight(
    db: Session,
    user_id: int,
    imported_at: datetime,
    campaign_name: str | None,
    profile_display_name: str | None,
) -> tuple[CandidateProfile | None, str]:
    """Validate import arguments and profile existence before writes."""
    if not isinstance(imported_at, datetime) or imported_at.tzinfo is None:
        raise CampaignImportError("imported_at must be timezone-aware UTC", status_code=422)
    offset = imported_at.utcoffset()
    if offset is not None and offset.total_seconds() != 0:
        raise CampaignImportError("imported_at must be timezone-aware UTC", status_code=422)

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise CampaignImportError("User does not exist", status_code=404)

    profile = CareerProfileRepository(db).get_by_user(user_id)
    if profile is None:
        if not profile_display_name or not profile_display_name.strip():
            raise CampaignImportError(
                "profile_display_name is required when creating a new profile",
                status_code=422,
            )
        clean_profile_name = profile_display_name.strip()
        if len(clean_profile_name) > 160:
            raise CampaignImportError("profile_display_name exceeds 160 characters", status_code=422)
    else:
        clean_profile_name = profile.display_name

    if campaign_name is not None:
        clean_camp_name = campaign_name.strip()
        if not clean_camp_name:
            raise CampaignImportError("campaign name must not be blank", status_code=422)
        if len(clean_camp_name) > 160:
            raise CampaignImportError("campaign name exceeds 160 characters", status_code=422)

    return profile, clean_profile_name


def build_campaign_summary(
    planned: PlannedCampaign,
    prepared_source_docs: list[PreparedSourceDocument],
) -> dict[str, Any]:
    """Build bounded aggregate-only summary dict for campaign persistence."""
    return {
        "application_count": len(planned.applications),
        "artifact_count": len(planned.artifacts),
        "source_document_count": len(prepared_source_docs),
        "task_count": sum(1 for a in planned.applications if a.task is not None),
        "tracker_rows": sum(1 for a in planned.applications if "tracker" in a.source.provenance.get("sources", ())),
        "dossier_count": sum(1 for a in planned.applications if "dossier" in a.source.provenance.get("sources", ())),
        "matched_count": sum(1 for a in planned.applications if set(a.source.provenance.get("sources", ())) >= {"tracker", "dossier"}),
        "tracker_only_count": sum(1 for a in planned.applications if set(a.source.provenance.get("sources", ())) == {"tracker"}),
        "dossier_only_count": sum(1 for a in planned.applications if set(a.source.provenance.get("sources", ())) == {"dossier"}),
        "status_counts": dict(planned.status_counts),
        "omitted_credential_count": planned.credentials_count,
        "warning_count": len(planned.warnings),
    }


def prepare_root_source_documents(parsed: ParsedCampaign) -> list[PreparedSourceDocument]:
    """Preflight and prepare root Profile.md, Goal.md, Storytelling.md, and PDFs before writes."""
    prepared_list: list[PreparedSourceDocument] = []
    for path in sorted(parsed.inspection.members.keys()):
        member = parsed.inspection.members[path]
        role: str | None = None
        if path == "Profile.md":
            role = "profile"
        elif path == "Goal.md":
            role = "goals"
        elif path == "Storytelling.md":
            role = "narrative"
        elif "/" not in path and path.lower().endswith(".pdf"):
            role = "template_reference"

        if role is not None:
            media_type = get_safe_media_type(member.canonical_path)
            prep = prepare_source_document(
                filename=member.canonical_path,
                media_type=media_type,
                data=member.raw_bytes,
                source_role=role,
            )
            prepared_list.append(prep)
    return prepared_list


def cleanup_unreferenced_files(db: Session, new_files: set[str]) -> None:
    """Unlink newly created files that have no committed DB references in CareerAsset."""
    for storage_path in sorted(new_files):
        try:
            ref = db.query(CareerAsset).filter(CareerAsset.storage_path == storage_path).first()
            if ref is None:
                durable_unlink(resolve_data_path(storage_path, create_root=False))
        except Exception:
            pass


def cleanup_journals(journal_paths: list[str]) -> None:
    """Best-effort cleanup of asset publication journals."""
    for j_path in journal_paths:
        try:
            remove_asset_publication_journal(j_path)
        except Exception:
            pass


def verify_campaign_graph(*args: Any, **kwargs: Any) -> bool:
    """Compatibility import for callers of the pre-split helper module."""
    from backend.campaigns.graph_verifier import verify_campaign_graph as _verify

    return _verify(*args, **kwargs)


def publish_or_reuse_campaign_asset(*args: Any, **kwargs: Any) -> CareerAsset:
    """Compatibility import for the split publication helper."""
    from backend.campaigns.asset_import import publish_or_reuse_campaign_asset as _publish

    return _publish(*args, **kwargs)


def publish_root_source_document(*args: Any, **kwargs: Any) -> None:
    """Compatibility import for the split source-document helper."""
    from backend.campaigns.asset_import import publish_root_source_document as _publish

    _publish(*args, **kwargs)
