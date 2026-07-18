import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from backend.workflows.models import WorkflowRun
from backend.workflows.schemas import WorkflowEnqueue, WorkflowRunResponse


class WorkflowNotFoundError(LookupError):
    pass


class WorkflowConflictError(RuntimeError):
    pass


class WorkflowLeaseError(RuntimeError):
    pass


class WorkflowCancelledError(RuntimeError):
    pass


def _payload_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _error_code(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_.-]+", "_", value.lower()).strip("_")
    return (normalized or "workflow_error")[:80]


class WorkflowService:
    def __init__(self, db: Session):
        self.db = db

    def enqueue(self, user_id: int, data: WorkflowEnqueue) -> WorkflowRun:
        existing = (
            self.db.query(WorkflowRun)
            .filter(
                WorkflowRun.user_id == user_id,
                WorkflowRun.workflow_type == data.workflow_type,
                WorkflowRun.idempotency_key == data.idempotency_key,
            )
            .first()
        )
        if existing is not None:
            if _payload_hash(existing.payload) != _payload_hash(data.payload):
                raise WorkflowConflictError(
                    "Idempotency key is already associated with a different payload"
                )
            return existing
        run = WorkflowRun(
            user_id=user_id,
            workflow_type=data.workflow_type,
            idempotency_key=data.idempotency_key,
            status="queued",
            payload=data.payload,
            checkpoint={},
            result_reference={},
            progress=0.0,
            attempt_count=0,
            max_attempts=data.max_attempts,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def _reap_terminal_leases(self, now: datetime) -> None:
        self.db.execute(
            update(WorkflowRun)
            .where(
                WorkflowRun.status == "running",
                WorkflowRun.lease_expires_at < now,
                WorkflowRun.cancel_requested_at.is_not(None),
            )
            .values(
                status="cancelled",
                lease_owner=None,
                lease_expires_at=None,
                finished_at=now,
                error_code=None,
            )
        )
        self.db.execute(
            update(WorkflowRun)
            .where(
                WorkflowRun.status == "running",
                WorkflowRun.lease_expires_at < now,
                WorkflowRun.attempt_count >= WorkflowRun.max_attempts,
            )
            .values(
                status="failed",
                lease_owner=None,
                lease_expires_at=None,
                finished_at=now,
                error_code="lease_expired",
            )
        )

    def claim(
        self,
        *,
        worker_id: str,
        workflow_types: Sequence[str] | None = None,
        lease_seconds: int = 30,
    ) -> WorkflowRun | None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        now = datetime.now(timezone.utc)
        self._reap_terminal_leases(now)
        eligible = and_(
            WorkflowRun.cancel_requested_at.is_(None),
            WorkflowRun.attempt_count < WorkflowRun.max_attempts,
            or_(
                WorkflowRun.status == "queued",
                and_(
                    WorkflowRun.status == "running",
                    WorkflowRun.lease_expires_at.is_not(None),
                    WorkflowRun.lease_expires_at < now,
                ),
            ),
        )
        if workflow_types:
            eligible = and_(eligible, WorkflowRun.workflow_type.in_(list(workflow_types)))
        candidate = (
            select(WorkflowRun.id)
            .where(eligible)
            .order_by(WorkflowRun.created_at, WorkflowRun.id)
            .limit(1)
            .scalar_subquery()
        )
        statement = (
            update(WorkflowRun)
            .where(WorkflowRun.id == candidate)
            .values(
                status="running",
                lease_owner=worker_id,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                attempt_count=WorkflowRun.attempt_count + 1,
                started_at=func.coalesce(WorkflowRun.started_at, now),
                finished_at=None,
                error_code=None,
            )
            .returning(WorkflowRun.id)
        )
        run_id = self.db.execute(statement).scalar_one_or_none()
        self.db.commit()
        if run_id is None:
            return None
        return self.db.query(WorkflowRun).filter(WorkflowRun.id == run_id).one()

    def _leased(self, run_id: str, worker_id: str) -> WorkflowRun:
        run = self.db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if run is None:
            raise WorkflowNotFoundError("Workflow not found")
        if run.status != "running" or run.lease_owner != worker_id:
            raise WorkflowLeaseError("Workflow lease is not owned by this worker")
        if run.cancel_requested_at is not None:
            raise WorkflowCancelledError("Workflow cancellation was requested")
        now = datetime.now(timezone.utc)
        expires = run.lease_expires_at
        if expires is None or expires.replace(tzinfo=timezone.utc) < now:
            raise WorkflowLeaseError("Workflow lease has expired")
        return run

    def checkpoint(
        self,
        run_id: str,
        *,
        worker_id: str,
        checkpoint: dict[str, Any],
        progress: float,
        lease_seconds: int = 30,
    ) -> WorkflowRun:
        run = self._leased(run_id, worker_id)
        if not 0 <= progress <= 1:
            raise ValueError("progress must be between 0 and 1")
        run.checkpoint = checkpoint
        run.progress = progress
        run.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
        self.db.commit()
        self.db.refresh(run)
        return run

    def complete(
        self, run_id: str, *, worker_id: str, result_reference: dict[str, Any] | None = None
    ) -> WorkflowRun:
        run = self._leased(run_id, worker_id)
        now = datetime.now(timezone.utc)
        run.status = "succeeded"
        run.progress = 1.0
        run.result_reference = result_reference or {}
        run.lease_owner = None
        run.lease_expires_at = None
        run.finished_at = now
        run.error_code = None
        self.db.commit()
        self.db.refresh(run)
        return run

    def fail(
        self,
        run_id: str,
        *,
        worker_id: str,
        error_code: str,
        retryable: bool,
    ) -> WorkflowRun:
        run = self._leased(run_id, worker_id)
        should_retry = retryable and run.attempt_count < run.max_attempts
        run.status = "queued" if should_retry else "failed"
        run.error_code = _error_code(error_code)
        run.lease_owner = None
        run.lease_expires_at = None
        run.finished_at = None if should_retry else datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(run)
        return run

    def request_cancel(self, user_id: int, run_id: str) -> WorkflowRun:
        run = self._owned(user_id, run_id)
        if run.status in {"succeeded", "failed", "cancelled"}:
            return run
        now = datetime.now(timezone.utc)
        run.cancel_requested_at = now
        if run.status == "queued":
            run.status = "cancelled"
            run.finished_at = now
        self.db.commit()
        self.db.refresh(run)
        return run

    def acknowledge_cancellation(self, run_id: str, *, worker_id: str) -> WorkflowRun:
        run = self.db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if run is None:
            raise WorkflowNotFoundError("Workflow not found")
        if run.status != "running" or run.lease_owner != worker_id:
            raise WorkflowLeaseError("Workflow lease is not owned by this worker")
        if run.cancel_requested_at is None:
            raise WorkflowConflictError("Workflow cancellation was not requested")
        run.status = "cancelled"
        run.lease_owner = None
        run.lease_expires_at = None
        run.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(run)
        return run

    def retry(self, user_id: int, run_id: str) -> WorkflowRun:
        run = self._owned(user_id, run_id)
        if run.status not in {"failed", "cancelled"}:
            raise WorkflowConflictError("Only failed or cancelled workflows can be retried")
        run.status = "queued"
        run.attempt_count = 0
        run.error_code = None
        run.cancel_requested_at = None
        run.finished_at = None
        run.lease_owner = None
        run.lease_expires_at = None
        self.db.commit()
        self.db.refresh(run)
        return run

    def _owned(self, user_id: int, run_id: str) -> WorkflowRun:
        run = (
            self.db.query(WorkflowRun)
            .filter(WorkflowRun.id == run_id, WorkflowRun.user_id == user_id)
            .first()
        )
        if run is None:
            raise WorkflowNotFoundError("Workflow not found")
        return run

    def get(self, user_id: int, run_id: str) -> WorkflowRunResponse:
        return WorkflowRunResponse.model_validate(self._owned(user_id, run_id))

    def list(self, user_id: int) -> list[WorkflowRunResponse]:
        runs = (
            self.db.query(WorkflowRun)
            .filter(WorkflowRun.user_id == user_id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(200)
            .all()
        )
        return [WorkflowRunResponse.model_validate(run) for run in runs]
