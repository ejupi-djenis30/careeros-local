"""Durable lifecycle service for agent work requests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.agent_work.context import build_context_snapshot
from backend.agent_work.errors import AgentWorkError
from backend.agent_work.models import AgentProposal, AgentWorkRequest
from backend.agent_work.schemas import (
    AgentWorkCreateRequest,
    AgentWorkDetailView,
    AgentWorkView,
    ProposalDetailView,
    WorkState,
)
from backend.applications.models import Application
from backend.automation.models import AutomationGrant
from backend.career.models import CandidateProfile
from backend.models.job import Job
from backend.models.user import VAULT_STATE_READY, User
from backend.resumes.models import ResumeDraft


def _view_from_model(req: AgentWorkRequest) -> AgentWorkView:
    return AgentWorkView(
        id=req.id,
        work_kind=req.work_kind,  # type: ignore[arg-type]
        state=req.state,  # type: ignore[arg-type]
        revision=req.revision,
        instruction=req.instruction,
        bound_grant_id=req.bound_grant_id,
        target_job_id=req.target_job_id,
        target_application_id=req.target_application_id,
        target_resume_id=req.target_resume_id,
        preset_id=req.preset_id,
        preset_version=req.preset_version,
        locale=req.locale,
        input_digest=req.input_digest,
        expires_at=req.expires_at,
        created_at=req.created_at,
        updated_at=req.updated_at,
        error_code=req.error_code,
    )


def _detail_view_from_model(req: AgentWorkRequest) -> AgentWorkDetailView:
    base = _view_from_model(req).model_dump()
    prop_view: ProposalDetailView | None = None
    if req.proposal is not None:
        p: AgentProposal = req.proposal
        prop_view = ProposalDetailView(
            id=p.id,
            request_id=p.request_id,
            submitting_grant_id=p.submitting_grant_id,
            idempotency_key=p.idempotency_key,
            payload_digest=p.payload_digest,
            contract_version=p.contract_version,
            client_label=p.client_label,
            model_label=p.model_label,
            payload=p.payload,
            review_required=p.review_required,
            created_at=p.created_at,
        )
    return AgentWorkDetailView(
        **base,
        input_revisions=req.input_revisions,
        selected_fact_ids=req.selected_fact_ids,
        proposal=prop_view,
        accepted_receipt=req.accepted_receipt,
    )


class AgentWorkService:
    """Service managing durable owner work requests and state transitions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_work_request(
        self,
        user_id: int,
        request_in: AgentWorkCreateRequest,
    ) -> AgentWorkView:
        now = datetime.now(UTC)
        lifecycle = self.db.query(User.vault_lifecycle_state).filter(User.id == user_id).scalar()
        if lifecycle != VAULT_STATE_READY:
            raise AgentWorkError("vault_unavailable", "Career Vault maintenance is pending")

        grant = (
            self.db.query(AutomationGrant)
            .filter(AutomationGrant.id == request_in.grant_id, AutomationGrant.user_id == user_id)
            .first()
        )
        if grant is None:
            raise AgentWorkError("grant_required", "The bound automation grant was not found")
        if grant.revoked_at is not None:
            raise AgentWorkError("grant_revoked", "The bound automation grant has been revoked")
        if grant.expires_at <= now:
            raise AgentWorkError("grant_expired", "The bound automation grant has expired")

        scopes = grant.scope_set()
        if not ("context:read" in scopes or "proposals:write" in scopes):
            raise AgentWorkError(
                "scope_denied",
                "The bound grant must include context:read or proposals:write scope",
            )

        # Lifetime: bounded by grant expiry and requested lifetime (max 7 days)
        req_lifetime = min(timedelta(hours=request_in.lifetime_hours), timedelta(days=7))
        calculated_expiry = min(now + req_lifetime, grant.expires_at)
        if calculated_expiry <= now:
            raise AgentWorkError("grant_expired", "The bound automation grant has expired")

        # Target verification
        if (
            request_in.target_job_id
            and not self.db.query(Job.id)
            .filter(Job.id == request_in.target_job_id, Job.user_id == user_id)
            .first()
        ):
            raise AgentWorkError("work_not_found", "Target job was not found")
        if (
            request_in.target_application_id
            and not self.db.query(Application.id)
            .filter(
                Application.id == request_in.target_application_id, Application.user_id == user_id
            )
            .first()
        ):
            raise AgentWorkError("work_not_found", "Target application was not found")
        if request_in.target_resume_id:
            profile_id = (
                self.db.query(CandidateProfile.id)
                .filter(CandidateProfile.user_id == user_id)
                .scalar()
            )
            if (
                not self.db.query(ResumeDraft.id)
                .filter(
                    ResumeDraft.id == request_in.target_resume_id,
                    ResumeDraft.profile_id == (profile_id or ""),
                )
                .first()
            ):
                raise AgentWorkError("work_not_found", "Target resume draft was not found")

        if request_in.work_kind == "materials" and request_in.preset_id is None:
            selected_resume = (
                self.db.query(ResumeDraft).filter_by(id=request_in.target_resume_id).one()
            )
            request_in = request_in.model_copy(
                update={
                    "preset_id": selected_resume.template_id,
                    "preset_version": selected_resume.template_version,
                    "locale": selected_resume.locale,
                }
            )

        request_id = str(uuid.uuid4())
        context, digest, input_revisions = build_context_snapshot(
            self.db,
            user_id=user_id,
            request_id=request_id,
            historical_grant_id=grant.id,
            work_kind=request_in.work_kind,
            instruction=request_in.instruction,
            target_job_id=request_in.target_job_id,
            target_application_id=request_in.target_application_id,
            target_resume_id=request_in.target_resume_id,
            selected_fact_ids=request_in.selected_fact_ids,
            preset={
                "id": request_in.preset_id,
                "version": request_in.preset_version,
                "locale": request_in.locale,
            }
            if request_in.preset_id
            else None,
        )

        work = AgentWorkRequest(
            id=request_id,
            user_id=user_id,
            bound_grant_id=grant.id,
            work_kind=request_in.work_kind,
            state="queued",
            revision=1,
            instruction=request_in.instruction,
            target_job_id=request_in.target_job_id,
            target_application_id=request_in.target_application_id,
            target_resume_id=request_in.target_resume_id,
            preset_id=request_in.preset_id,
            preset_version=request_in.preset_version,
            locale=request_in.locale,
            selected_fact_ids=request_in.selected_fact_ids,
            context_snapshot=context.model_dump(mode="json"),
            input_digest=digest,
            input_revisions=input_revisions,
            expires_at=calculated_expiry,
        )
        self.db.add(work)
        self.db.commit()
        self.db.refresh(work)
        return _view_from_model(work)

    def _expire_stale_work(self, user_id: int, now: datetime) -> None:
        self.db.query(AgentWorkRequest).filter(
            AgentWorkRequest.user_id == user_id,
            AgentWorkRequest.expires_at <= now,
            AgentWorkRequest.state.in_(("queued", "returned")),
        ).update(
            {
                AgentWorkRequest.state: "expired",
                AgentWorkRequest.updated_at: now,
                AgentWorkRequest.revision: AgentWorkRequest.revision + 1,
            },
            synchronize_session=False,
        )
        self.db.flush()

    def list_work_requests(
        self,
        user_id: int,
        *,
        offset: int = 0,
        limit: int = 25,
        state: WorkState | None = None,
        grant_id: str | None = None,
    ) -> tuple[list[AgentWorkView], int]:
        from backend.agent_work.guards import require_ready

        require_ready(self.db, user_id)
        now = datetime.now(UTC)
        self._expire_stale_work(user_id, now)
        self.db.commit()

        query = self.db.query(AgentWorkRequest).filter(AgentWorkRequest.user_id == user_id)
        if state is not None:
            query = query.filter(AgentWorkRequest.state == state)
        if grant_id is not None:
            query = query.filter(AgentWorkRequest.bound_grant_id == grant_id)

        total = query.count()
        rows = (
            query.order_by(AgentWorkRequest.created_at.desc(), AgentWorkRequest.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_view_from_model(r) for r in rows], total

    def get_work_request(self, user_id: int, request_id: str) -> AgentWorkDetailView:
        from backend.agent_work.guards import require_ready

        require_ready(self.db, user_id)
        now = datetime.now(UTC)
        self._expire_stale_work(user_id, now)
        self.db.commit()

        req = (
            self.db.query(AgentWorkRequest)
            .filter(AgentWorkRequest.id == request_id, AgentWorkRequest.user_id == user_id)
            .first()
        )
        if req is None:
            raise AgentWorkError("work_not_found", "Work request was not found")
        return _detail_view_from_model(req)

    def _transition(
        self, user_id: int, request_id: str, expected_revision: int, state: str
    ) -> AgentWorkView:
        from backend.agent_work.guards import require_ready

        require_ready(self.db, user_id)
        now = datetime.now(UTC)
        req = (
            self.db.query(AgentWorkRequest)
            .populate_existing()
            .filter_by(id=request_id, user_id=user_id)
            .first()
        )
        if req is None:
            raise AgentWorkError("work_not_found", "Work request was not found")
        if req.expires_at <= now:
            self._expire_stale_work(user_id, now)
            self.db.commit()
            raise AgentWorkError("work_expired", "Work request has expired")
        if req.state == "canceled":
            raise AgentWorkError("work_canceled", "Work request was canceled")
        allowed = ("queued", "returned") if state == "canceled" else ("returned",)
        changed = (
            self.db.query(AgentWorkRequest)
            .filter(
                AgentWorkRequest.id == request_id,
                AgentWorkRequest.user_id == user_id,
                AgentWorkRequest.revision == expected_revision,
                AgentWorkRequest.state.in_(allowed),
                AgentWorkRequest.expires_at > now,
            )
            .update(
                {
                    AgentWorkRequest.state: state,
                    AgentWorkRequest.revision: AgentWorkRequest.revision + 1,
                    AgentWorkRequest.updated_at: now,
                },
                synchronize_session=False,
            )
        )
        if changed != 1:
            self.db.rollback()
            raise AgentWorkError(
                "revision_conflict", "Work request changed; refresh before retrying"
            )
        self.db.commit()
        self.db.refresh(req)
        return _view_from_model(req)

    def cancel_work_request(
        self, user_id: int, request_id: str, expected_revision: int
    ) -> AgentWorkView:
        return self._transition(user_id, request_id, expected_revision, "canceled")

    def reject_work_request(
        self, user_id: int, request_id: str, expected_revision: int
    ) -> AgentWorkView:
        return self._transition(user_id, request_id, expected_revision, "rejected")
