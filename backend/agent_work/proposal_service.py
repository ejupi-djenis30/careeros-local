"""Authenticated immutable proposal receipts with database compare-and-swap."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from backend.agent_work.context import compute_payload_digest
from backend.agent_work.errors import AgentWorkError
from backend.agent_work.guards import require_current_inputs, require_grant, require_work_live
from backend.agent_work.models import AgentProposal, AgentWorkRequest
from backend.agent_work.schemas import ProposalReceiptView, ProposalSubmissionRequest, WorkState
from backend.agent_work.validation import validate_proposal_payload


def _receipt(proposal: AgentProposal, state: str) -> ProposalReceiptView:
    return ProposalReceiptView(
        proposal_id=proposal.id,
        request_id=proposal.request_id,
        state=cast(WorkState, state),
        payload_digest=proposal.payload_digest,
        review_required=proposal.review_required,
        created_at=proposal.created_at,
    )


class ProposalService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _request(
        self, grant_id: str, request_id: str, scope: str | None = None
    ) -> AgentWorkRequest:
        grant = require_grant(self.db, grant_id, scope)
        req = (
            self.db.query(AgentWorkRequest)
            .populate_existing()
            .filter_by(id=request_id, user_id=grant.user_id, bound_grant_id=grant_id)
            .first()
        )
        if req is None:
            raise AgentWorkError("work_not_found", "Work request was not found")
        require_work_live(req)
        return req

    def submit_proposal(
        self, grant_id: str, request_id: str, submission: ProposalSubmissionRequest
    ) -> ProposalReceiptView:
        if request_id != submission.request_id:
            raise AgentWorkError("invalid_result", "Submission identity does not match its request")
        try:
            req = self._request(grant_id, request_id, "proposals:write")
            if submission.input_digest != req.input_digest:
                raise AgentWorkError("stale_input", "Input digest does not match the request")
            validate_proposal_payload(req, submission.result)
            payload = submission.result.model_dump(mode="json")
            digest = compute_payload_digest(payload)
            existing = self.db.query(AgentProposal).filter_by(request_id=request_id).first()
            if existing is not None:
                if (
                    existing.idempotency_key == submission.idempotency_key
                    and existing.payload_digest == digest
                ):
                    return _receipt(existing, req.state)
                raise AgentWorkError("result_conflict", "A different result already exists")
            if req.state != "queued":
                raise AgentWorkError("revision_conflict", "The request no longer accepts proposals")
            now = datetime.now(UTC)
            # First write takes the SQLite writer reservation; all following checks and
            # inserts remain in this transaction. Conditional update prevents stale writers.
            changed = (
                self.db.query(AgentWorkRequest)
                .filter_by(
                    id=req.id,
                    user_id=req.user_id,
                    bound_grant_id=grant_id,
                    state="queued",
                    revision=req.revision,
                )
                .filter(AgentWorkRequest.expires_at > now)
                .update(
                    {
                        AgentWorkRequest.state: "returned",
                        AgentWorkRequest.revision: AgentWorkRequest.revision + 1,
                        AgentWorkRequest.updated_at: now,
                    },
                    synchronize_session=False,
                )
            )
            if changed != 1:
                raise AgentWorkError("result_conflict", "The request changed during submission")
            require_grant(self.db, grant_id, "proposals:write", req.user_id)
            require_current_inputs(self.db, req)
            proposal = AgentProposal(
                id=str(uuid.uuid4()),
                request_id=req.id,
                user_id=req.user_id,
                submitting_grant_id=grant_id,
                idempotency_key=submission.idempotency_key,
                payload_digest=digest,
                contract_version=1,
                client_label=submission.client,
                model_label=submission.model,
                payload=payload,
                review_required=True,
                created_at=now,
            )
            self.db.add(proposal)
            self.db.commit()
            self.db.refresh(proposal)
            return _receipt(proposal, "returned")
        except (IntegrityError, OperationalError):
            self.db.rollback()
            raise AgentWorkError(
                "result_conflict", "The request changed during submission; retry safely"
            ) from None
        except Exception:
            self.db.rollback()
            raise

    def get_work_result(self, grant_id: str, request_id: str) -> ProposalReceiptView:
        req = self._request(grant_id, request_id)
        grant = require_grant(self.db, grant_id)
        if not ({"context:read", "proposals:write"} & grant.scope_set()):
            raise AgentWorkError("scope_denied", "The grant does not permit work receipt access")
        proposal = (
            self.db.query(AgentProposal)
            .filter_by(request_id=request_id, user_id=req.user_id)
            .first()
        )
        if proposal is None:
            raise AgentWorkError("work_not_found", "No result has been returned")
        return _receipt(proposal, req.state)
