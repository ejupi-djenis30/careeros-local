"""Flush-only acceptance handler for reviewed external match analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy.orm import Session

from backend.agent_work.errors import AgentWorkError
from backend.agent_work.models import AgentProposal, AgentWorkRequest
from backend.agent_work.schemas import AnalysisProposalPayload
from backend.agent_work.validation import eligibility
from backend.models.job import Job


def accept_analysis_flush_only(
    db: Session,
    *,
    user_id: int,
    req: AgentWorkRequest,
    proposal: AgentProposal,
    payload: AnalysisProposalPayload,
    now: datetime,
) -> None:
    if req.target_job_id is None:
        raise AgentWorkError("work_not_found", "Target job not found for analysis acceptance")
    job = db.query(Job).filter_by(id=req.target_job_id, user_id=user_id).first()
    if job is None:
        raise AgentWorkError("work_not_found", "Target job not found for analysis acceptance")

    scores = payload.scores
    overall = scores.overall_score
    target = cast(Any, job)
    # Remove every value derived by a previous analysis before applying fields
    # represented by the external contract. This prevents trusted old scores
    # from being displayed or exported alongside the new receipt.
    for field in (
        "affinity_score",
        "affinity_analysis",
        "worth_applying",
        "skill_match_score",
        "experience_match_score",
        "intent_match_score",
        "language_match_score",
        "location_match_score",
        "transferability_score",
        "qualification_gap_score",
        "analysis_structured",
        "analysis_provenance",
        "analysis_model_id",
        "analysis_contract_version",
        "analysis_validated_at",
        "analysis_execution_id",
        "analysis_output_fingerprint",
        "analysis_row_fingerprint",
        "analysis_execution_row_index",
        "analysis_input_fingerprint",
        "analysis_legacy_snapshot",
        "red_flags",
    ):
        setattr(target, field, None)

    target.affinity_score = float(overall)
    target.worth_applying = eligibility(payload.gates) == "eligible" and payload.recommendation in (
        "strong_fit",
        "consider",
    )
    target.analysis_provenance = "external_agent_proposal"
    target.analysis_model_id = proposal.model_label or proposal.client_label or "external-agent"
    target.analysis_contract_version = "1.0"
    target.analysis_validated_at = now
    target.analysis_structured = {
        "recommendation": payload.recommendation,
        "gates": [gate.model_dump(mode="json") for gate in payload.gates],
        "claims": [claim.model_dump(mode="json") for claim in payload.claims],
        "scores": scores.model_dump(mode="json"),
        "source": "external_agent",
        "request_id": req.id,
        "proposal_id": proposal.id,
        "grant_id": proposal.submitting_grant_id,
        "input_digest": req.input_digest,
        "payload_digest": proposal.payload_digest,
    }
    target.skill_match_score = float(scores.role.score)
    target.experience_match_score = float(scores.requirements.score)
    target.language_match_score = float(scores.language.score)
    target.location_match_score = float(scores.location.score)
    target.affinity_analysis = (
        f"External Agent Analysis: {payload.recommendation} (Score: {overall})"
    )
    db.flush()
