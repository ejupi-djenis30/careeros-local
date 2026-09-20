"""Live authorization and revision checks shared by agent transactions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from sqlalchemy.orm import Session

from backend.agent_work.context import build_context_snapshot
from backend.agent_work.errors import AgentWorkError
from backend.agent_work.models import AgentWorkRequest
from backend.agent_work.schemas import WorkKind
from backend.automation.models import AutomationGrant
from backend.models.user import VAULT_STATE_READY, User


def require_ready(db: Session, user_id: int) -> None:
    if (
        db.query(User.vault_lifecycle_state).filter(User.id == user_id).scalar()
        != VAULT_STATE_READY
    ):
        raise AgentWorkError("vault_unavailable", "Career Vault maintenance is pending")


def require_grant(
    db: Session, grant_id: str | None, scope: str | None = None, user_id: int | None = None
) -> AutomationGrant:
    grant = (
        db.query(AutomationGrant).populate_existing().filter(AutomationGrant.id == grant_id).first()
    )
    if grant is None or (user_id is not None and grant.user_id != user_id):
        raise AgentWorkError("grant_required", "A live bound grant is required")
    if grant.revoked_at is not None:
        raise AgentWorkError("grant_revoked", "The grant has been revoked")
    if grant.expires_at <= datetime.now(UTC):
        raise AgentWorkError("grant_expired", "The grant has expired")
    if scope is not None and scope not in grant.scope_set():
        raise AgentWorkError("scope_denied", "The grant does not permit this operation")
    require_ready(db, grant.user_id)
    return grant


def require_work_live(req: AgentWorkRequest) -> None:
    if req.expires_at <= datetime.now(UTC) or req.state == "expired":
        raise AgentWorkError("work_expired", "The work request has expired")
    if req.state == "canceled":
        raise AgentWorkError("work_canceled", "The work request was canceled")


def current_input_state(
    db: Session, req: AgentWorkRequest
) -> tuple[str, dict[str, int | None]]:
    try:
        _, digest, revisions = build_context_snapshot(
            db,
            user_id=req.user_id,
            request_id=req.id,
            work_kind=cast(WorkKind, req.work_kind),
            instruction=req.instruction,
            historical_grant_id=req.context_snapshot.get("historical_grant_id"),
            target_job_id=req.target_job_id,
            target_application_id=req.target_application_id,
            target_resume_id=req.target_resume_id,
            selected_fact_ids=req.selected_fact_ids,
            preset={"id": req.preset_id, "version": req.preset_version, "locale": req.locale}
            if req.preset_id
            else None,
        )
    except AgentWorkError:
        raise AgentWorkError("stale_input", "The selected inputs are no longer available") from None
    return digest, revisions


def require_current_inputs(db: Session, req: AgentWorkRequest) -> None:
    digest, revisions = current_input_state(db, req)
    if revisions != req.input_revisions or digest != req.input_digest:
        raise AgentWorkError(
            "stale_input", "The selected inputs changed; create a new work request"
        )
