"""Campaign import acknowledgement construction."""

from __future__ import annotations

from typing import Any

from backend.campaigns.import_planner_types import PlannedCampaign
from backend.campaigns.schemas import CampaignImportResponse
from backend.career.source_parsing import PreparedSourceDocument


def _build_response(
    campaign_id: str,
    fingerprint: str,
    created: bool,
    planned: PlannedCampaign,
    prepared_source_docs: list[PreparedSourceDocument],
    summary_dict: dict[str, Any],
) -> CampaignImportResponse:
    return CampaignImportResponse(
        campaign_id=campaign_id,
        fingerprint=fingerprint,
        created=created,
        application_count=len(planned.applications),
        artifact_count=len(planned.artifacts),
        source_document_count=len(prepared_source_docs),
        task_count=summary_dict["task_count"],
        warning_count=len(planned.warnings),
    )
