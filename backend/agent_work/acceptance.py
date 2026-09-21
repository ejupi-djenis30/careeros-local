"""Atomic, transaction-safe acceptance for external agent proposals."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from backend.agent_work.guards import (
    current_input_state,
    require_current_inputs,
    require_grant,
    require_ready,
    require_work_live,
)
from backend.agent_work.models import AgentWorkRequest
from backend.agent_work.schemas import (
    AgentWorkAcceptRequest,
    AnalysisProposalPayload,
    DiscoveryProposalPayload,
    MaterialsProposalPayload,
    ProposalPayload,
)
from backend.agent_work.service import AgentWorkError
from backend.agent_work.validation import validate_proposal_payload


def _accept_work_proposal(
    db: Session,
    *,
    user_id: int,
    request_id: str,
    accept_in: AgentWorkAcceptRequest,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    require_ready(db, user_id)
    req = (
        db.query(AgentWorkRequest)
        .populate_existing()
        .filter_by(id=request_id, user_id=user_id)
        .first()
    )
    if req is None:
        raise AgentWorkError("work_not_found", "Work request was not found")
    require_grant(db, req.bound_grant_id, "proposals:write", user_id)
    require_work_live(req)
    if req.state == "accepted" and req.accepted_receipt is not None:
        if accept_in.expected_revision not in {req.revision - 1, req.revision}:
            raise AgentWorkError(
                "revision_conflict", "Acceptance revision does not match its receipt"
            )
        if accept_in.expected_target_revisions != req.input_revisions:
            raise AgentWorkError(
                "stale_input", "Acceptance replay must use the reviewed target revisions"
            )
        digest, revisions = current_input_state(db, req)
        if (
            req.accepted_receipt.get("accepted_input_digest") != digest
            or req.accepted_receipt.get("accepted_input_revisions") != revisions
        ):
            raise AgentWorkError(
                "stale_input", "The accepted proposal targets have changed since acceptance"
            )
        return req.accepted_receipt
    changed = (
        db.query(AgentWorkRequest)
        .filter_by(
            id=req.id, user_id=user_id, state="returned", revision=accept_in.expected_revision
        )
        .filter(AgentWorkRequest.expires_at > now)
        .update(
            {AgentWorkRequest.revision: AgentWorkRequest.revision + 1}, synchronize_session=False
        )
    )
    if changed != 1:
        raise AgentWorkError("revision_conflict", "The request changed before acceptance")
    require_grant(db, req.bound_grant_id, "proposals:write", user_id)
    require_current_inputs(db, req)
    if accept_in.expected_target_revisions != req.input_revisions:
        raise AgentWorkError("stale_input", "Review must include the current target revisions")
    proposal = req.proposal
    if proposal is None:
        raise AgentWorkError("work_not_found", "No proposal was returned")
    payload: ProposalPayload = TypeAdapter(ProposalPayload).validate_python(proposal.payload)
    validate_proposal_payload(req, payload)
    from backend.agent_work.context import compute_payload_digest

    if compute_payload_digest(payload.model_dump(mode="json")) != proposal.payload_digest:
        raise AgentWorkError("invalid_result", "Stored proposal integrity verification failed")

    created_job_ids: list[int] = []
    created_app_ids: list[str] = []
    material_receipt: dict[str, Any] = {}
    if isinstance(payload, DiscoveryProposalPayload):
        from backend.agent_work.discovery_acceptance import accept_discovery_flush_only

        discovery = accept_discovery_flush_only(
            db,
            user_id=user_id,
            req=req,
            proposal=proposal,
            payload=payload,
            now=now,
        )
        created_job_ids = discovery.job_ids
        created_app_ids = discovery.application_ids
    elif isinstance(payload, AnalysisProposalPayload):
        from backend.agent_work.analysis_acceptance import accept_analysis_flush_only

        accept_analysis_flush_only(
            db,
            user_id=user_id,
            req=req,
            proposal=proposal,
            payload=payload,
            now=now,
        )
    elif isinstance(payload, MaterialsProposalPayload):
        from backend.agent_work.material_acceptance import accept_materials_flush_only

        material_receipt = accept_materials_flush_only(db, req, proposal)

    accepted_input_digest, accepted_input_revisions = current_input_state(db, req)
    receipt: dict[str, Any] = {
        "request_id": req.id,
        "proposal_id": proposal.id,
        "work_kind": req.work_kind,
        "accepted_at": now.isoformat(),
        "target_job_id": req.target_job_id,
        "created_job_ids": created_job_ids,
        "created_application_ids": created_app_ids,
        "accepted_input_digest": accepted_input_digest,
        "accepted_input_revisions": accepted_input_revisions,
        **material_receipt,
    }

    req.state = "accepted"
    req.revision = accept_in.expected_revision + 1
    req.accepted_receipt = receipt
    req.updated_at = now

    db.commit()
    return receipt


def accept_work_proposal(
    db: Session, *, user_id: int, request_id: str, accept_in: AgentWorkAcceptRequest
) -> dict[str, Any]:
    try:
        return _accept_work_proposal(
            db, user_id=user_id, request_id=request_id, accept_in=accept_in
        )
    except ValidationError:
        db.rollback()
        raise AgentWorkError(
            "invalid_result", "Stored proposal does not satisfy the current contract"
        ) from None
    except (IntegrityError, OperationalError):
        db.rollback()
        raise AgentWorkError(
            "revision_conflict", "The inputs changed during acceptance; refresh before retrying"
        ) from None
    except Exception:
        db.rollback()
        raise
