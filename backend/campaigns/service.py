"""Campaign import orchestration service."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.campaigns.archive_policy import ArchivePolicyError
from backend.campaigns.graph_verifier import verify_campaign_graph
from backend.campaigns.import_planner import CampaignPlanError, plan_campaign_import
from backend.campaigns.import_planner_types import PlannedCampaign
from backend.campaigns.models import Campaign
from backend.campaigns.parser import parse_campaign_workspace
from backend.campaigns.persistence import persist_entities
from backend.campaigns.schemas import CampaignImportResponse
from backend.campaigns.service_helpers import (
    CampaignImportError,
    build_campaign_summary,
    cleanup_journals,
    cleanup_unreferenced_files,
    owner_scoped_uuid,
    prepare_root_source_documents,
    validate_import_preflight,
)
from backend.career.asset_publication import begin_asset_publication_write
from backend.career.models import CandidateProfile
from backend.career.reference_parsing import SourceImportError
from backend.career.source_parsing import PreparedSourceDocument


def _build_response(
    campaign_id: str, fingerprint: str, created: bool,
    planned: PlannedCampaign, prepared_source_docs: list[PreparedSourceDocument],
    summary_dict: dict[str, Any],
) -> CampaignImportResponse:
    return CampaignImportResponse(
        campaign_id=campaign_id, fingerprint=fingerprint, created=created,
        application_count=len(planned.applications), artifact_count=len(planned.artifacts),
        source_document_count=len(prepared_source_docs), task_count=summary_dict["task_count"],
        warning_count=len(planned.warnings),
    )


def import_campaign(
    db: Session,
    *,
    user_id: int,
    archive_bytes: bytes,
    expected_fingerprint: str,
    imported_at: datetime,
    campaign_name: str | None = None,
    profile_display_name: str | None = None,
) -> CampaignImportResponse:
    """Import campaign workspace archive with atomic transaction, idempotency, and full rollback."""
    try:
        profile, clean_profile_name = validate_import_preflight(
            db, user_id, imported_at, campaign_name, profile_display_name
        )
    except CampaignImportError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise CampaignImportError("Campaign import validation failed", status_code=400)
    try:
        parsed = parse_campaign_workspace(archive_bytes)
    except ArchivePolicyError:
        db.rollback()
        raise CampaignImportError("Campaign archive validation failed", status_code=400)
    except Exception:
        db.rollback()
        raise CampaignImportError("Campaign archive could not be processed", status_code=422)

    if expected_fingerprint != parsed.fingerprint:
        db.rollback()
        raise CampaignImportError("Campaign preview fingerprint does not match archive", status_code=409)

    final_camp_name = (campaign_name.strip() if campaign_name else None) or "Legacy application campaign"
    try:
        prepared_source_docs = prepare_root_source_documents(parsed)
    except (SourceImportError, ValueError):
        db.rollback()
        raise CampaignImportError("Root source document preflight failed", status_code=422)
    except Exception:
        db.rollback()
        raise CampaignImportError("Root source document preflight failed", status_code=422)

    identity_scope = f"user:{user_id}"
    existing = db.query(Campaign).filter(
        Campaign.user_id == user_id,
        Campaign.source_fingerprint == parsed.fingerprint,
    ).first()
    if existing is not None:
        # The persisted import instant and display name are the source of truth for
        # an idempotent retry. Replanning with request values would change event
        # timestamps or incorrectly reject a harmless name change.
        persisted_at = existing.created_at
        if persisted_at.tzinfo is None:
            persisted_at = persisted_at.replace(tzinfo=imported_at.tzinfo)
        try:
            planned = plan_campaign_import(
                parsed,
                persisted_at,
                identity_scope=identity_scope,
                campaign_name=existing.name,
            )
        except CampaignPlanError:
            db.rollback()
            raise CampaignImportError("Campaign plan validation failed", status_code=422)
        except Exception:
            db.rollback()
            raise CampaignImportError("Campaign plan could not be prepared", status_code=500)
        summary_dict = build_campaign_summary(planned, prepared_source_docs)
        verified = verify_campaign_graph(
            db,
            existing.id,
            user_id,
            identity_scope,
            planned.fingerprint,
            planned,
            summary_dict,
            prepared_source_docs,
            campaign_name=parsed.suggested_name if existing.name == parsed.suggested_name else existing.name,
        )
        db.rollback()
        if not verified:
            raise CampaignImportError("Existing campaign state is incomplete or corrupt", status_code=409)
        return _build_response(existing.id, existing.source_fingerprint, False, planned, prepared_source_docs, summary_dict)

    try:
        planned = plan_campaign_import(parsed, imported_at, identity_scope=identity_scope, campaign_name=final_camp_name)
    except CampaignPlanError:
        db.rollback()
        raise CampaignImportError("Campaign plan validation failed", status_code=422)
    except Exception:
        db.rollback()
        raise CampaignImportError("Campaign plan could not be prepared", status_code=500)

    campaign_id = owner_scoped_uuid(identity_scope, planned.fingerprint, "campaign")
    summary_dict = build_campaign_summary(planned, prepared_source_docs)

    try:
        begin_asset_publication_write(db)
    except Exception:
        db.rollback()
        raise CampaignImportError("Campaign persistence could not be started", status_code=500)

    existing = db.query(Campaign).filter(Campaign.user_id == user_id, Campaign.source_fingerprint == planned.fingerprint).first()
    if existing is not None:
        persisted_at = existing.created_at
        if persisted_at.tzinfo is None:
            persisted_at = persisted_at.replace(tzinfo=imported_at.tzinfo)
        try:
            planned = plan_campaign_import(
                parsed,
                persisted_at,
                identity_scope=identity_scope,
                campaign_name=existing.name,
            )
        except Exception:
            db.rollback()
            raise CampaignImportError("Campaign plan could not be prepared", status_code=500)
        summary_dict = build_campaign_summary(planned, prepared_source_docs)
        verified = verify_campaign_graph(
            db,
            existing.id,
            user_id,
            identity_scope,
            planned.fingerprint,
            planned,
            summary_dict,
            prepared_source_docs,
            campaign_name=parsed.suggested_name if existing.name == parsed.suggested_name else existing.name,
        )
        db.rollback()
        if not verified:
            raise CampaignImportError("Existing campaign state is incomplete or corrupt", status_code=409)
        return _build_response(existing.id, existing.source_fingerprint, False, planned, prepared_source_docs, summary_dict)

    new_files: set[str] = set()
    new_journals: list[str] = []
    try:
        if profile is None:
            profile = CandidateProfile(id=str(uuid.uuid4()), user_id=user_id, display_name=clean_profile_name, revision=1)
            db.add(profile)
            db.flush()
        campaign = Campaign(
            id=campaign_id, user_id=user_id, name=planned.campaign_name,
            source_fingerprint=planned.fingerprint, tracker_sha256=planned.tracker_sha256,
            name_integrity=hashlib.sha256(planned.campaign_name.encode("utf-8")).hexdigest(),
            summary=summary_dict, created_at=planned.imported_at, updated_at=planned.imported_at,
        )
        db.add(campaign)
        persist_entities(
            db, profile=profile, user_id=user_id, identity_scope=identity_scope,
            planned=planned, campaign=campaign, prepared_source_docs=prepared_source_docs,
            new_files=new_files, new_journals=new_journals,
        )
    except CampaignImportError:
        db.rollback()
        cleanup_unreferenced_files(db, new_files)
        db.rollback()
        cleanup_journals(new_journals)
        raise CampaignImportError("Campaign persistence conflict", status_code=409)
    except Exception:
        db.rollback()
        cleanup_unreferenced_files(db, new_files)
        db.rollback()
        cleanup_journals(new_journals)
        raise CampaignImportError("Campaign persistence failed", status_code=500)

    try:
        db.commit()
    except Exception:
        db.rollback()
        recovery_ok = False
        try:
            begin_asset_publication_write(db)
            recovery_ok = verify_campaign_graph(
                db, campaign_id, user_id, identity_scope, planned.fingerprint,
                planned, summary_dict, prepared_source_docs,
                campaign_name=planned.campaign_name,
            )
        except Exception:
            recovery_ok = False
        finally:
            db.rollback()
        if recovery_ok:
            cleanup_journals(new_journals)
            return _build_response(campaign_id, planned.fingerprint, True, planned, prepared_source_docs, summary_dict)
        cleanup_unreferenced_files(db, new_files)
        db.rollback()
        cleanup_journals(new_journals)
        raise CampaignImportError("Campaign commit could not be verified", status_code=500)

    cleanup_journals(new_journals)
    return _build_response(campaign_id, planned.fingerprint, True, planned, prepared_source_docs, summary_dict)
