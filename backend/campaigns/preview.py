"""Side-effect-free campaign archive preview projected from ParsedCampaign."""

from __future__ import annotations

from typing import Final

from backend.campaigns.parser import (
    classify_artifact_category,
    parse_campaign_workspace,
    reconcile_dossier_directory_name,
)
from backend.campaigns.parser_types import ParsedCampaign
from backend.campaigns.schemas import (
    CampaignPreviewResponse,
    CampaignSampleItem,
)

__all__ = [
    "SAMPLE_LIMIT",
    "build_campaign_preview",
    "classify_artifact_category",
    "preview_from_parsed_campaign",
    "reconcile_dossier_directory_name",
]

SAMPLE_LIMIT: Final = 10


def preview_from_parsed_campaign(
    parsed: ParsedCampaign,
    *,
    user_has_profile: bool = True,
) -> CampaignPreviewResponse:
    """Project a CampaignPreviewResponse from an immutable ParsedCampaign."""
    sample_items = [
        CampaignSampleItem(
            source_application_id=app.source_application_id,
            title=app.title,
            company=app.company,
            source_status=app.source_status,
            provenance=list(app.provenance.get("sources", [])),
        )
        for app in parsed.applications[:SAMPLE_LIMIT]
    ]

    return CampaignPreviewResponse(
        fingerprint=parsed.fingerprint,
        suggested_name=parsed.suggested_name,
        suggested_profile_name=parsed.suggested_profile_name,
        tracker_rows=len(parsed.tracker_rows),
        dossier_count=parsed.dossier_count,
        matched_count=parsed.matched_count,
        tracker_only_count=parsed.tracker_only_count,
        dossier_only_count=parsed.dossier_only_count,
        logical_application_count=parsed.logical_application_count,
        artifact_count=len(parsed.artifacts),
        expanded_bytes=parsed.inspection.total_byte_size,
        status_counts=dict(parsed.status_counts),
        credential_rows_omitted=parsed.credentials_count,
        warnings=list(parsed.warnings),
        sample=sample_items,
        requires_profile_name=not user_has_profile,
    )


def build_campaign_preview(
    archive_bytes: bytes,
    archive_name: str = "campaign.zip",
    *,
    user_has_profile: bool = True,
) -> CampaignPreviewResponse:
    """Construct preview by parsing the campaign workspace without side effects."""
    parsed = parse_campaign_workspace(archive_bytes, archive_name=archive_name)
    return preview_from_parsed_campaign(parsed, user_has_profile=user_has_profile)
