from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.db.base import configure_sqlite_connection
from backend.models import User
from backend.models.base_model import Base
from backend.workflows.models import WorkflowRun
from backend.workflows.schemas import WorkflowEnqueue
from backend.workflows.service import (
    WorkflowCancelledError,
    WorkflowConflictError,
    WorkflowLeaseError,
    WorkflowService,
)


def _enqueue(service: WorkflowService, user_id: int, key="run-1", payload=None):
    return service.enqueue(
        user_id,
        WorkflowEnqueue(
            workflow_type="resume.render",
            idempotency_key=key,
            payload=payload or {"resume_id": "resume-1"},
            max_attempts=3,
        ),
    )


def test_enqueue_is_idempotent_and_rejects_key_reuse(db_session, test_user):
    service = WorkflowService(db_session)
    first = _enqueue(service, test_user.id)
    second = _enqueue(service, test_user.id)
    assert second.id == first.id
    assert db_session.query(WorkflowRun).count() == 1
    with pytest.raises(WorkflowConflictError, match="different payload"):
        _enqueue(service, test_user.id, payload={"resume_id": "different"})


def test_checkpoint_survives_expired_lease_and_new_worker_reclaims(db_session, test_user):
    service = WorkflowService(db_session)
    queued = _enqueue(service, test_user.id)
    claimed = service.claim(worker_id="worker-a", lease_seconds=30)
    assert claimed.id == queued.id
    assert claimed.attempt_count == 1
    service.checkpoint(
        claimed.id,
        worker_id="worker-a",
        checkpoint={"stage": "pdf-rendered", "artifact": "sha256"},
        progress=0.6,
    )
    claimed.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    reclaimed = service.claim(worker_id="worker-b", lease_seconds=30)
    assert reclaimed.id == claimed.id
    assert reclaimed.attempt_count == 2
    assert reclaimed.checkpoint == {"stage": "pdf-rendered", "artifact": "sha256"}
    with pytest.raises(WorkflowLeaseError):
        service.complete(claimed.id, worker_id="worker-a")
    completed = service.complete(
        reclaimed.id,
        worker_id="worker-b",
        result_reference={"version_id": "version-1"},
    )
    assert completed.status == "succeeded"
    assert completed.progress == 1


def test_cancel_retry_and_redacted_failure_lifecycle(db_session, test_user):
    service = WorkflowService(db_session)
    queued = _enqueue(service, test_user.id)
    claimed = service.claim(worker_id="worker-a")
    service.request_cancel(test_user.id, queued.id)
    with pytest.raises(WorkflowCancelledError):
        service.checkpoint(
            claimed.id,
            worker_id="worker-a",
            checkpoint={"private": "never logged"},
            progress=0.2,
        )
    cancelled = service.acknowledge_cancellation(claimed.id, worker_id="worker-a")
    assert cancelled.status == "cancelled"
    retried = service.retry(test_user.id, queued.id)
    assert retried.status == "queued"
    assert retried.attempt_count == 0
    claimed_again = service.claim(worker_id="worker-b")
    failed = service.fail(
        claimed_again.id,
        worker_id="worker-b",
        error_code="Disk full: C:\\private\\candidate-name.pdf",
        retryable=False,
    )
    assert failed.status == "failed"
    assert failed.error_code == "disk_full_c_private_candidate-name.pdf"
    assert "\\" not in failed.error_code


def test_sqlite_atomic_claim_allows_only_one_worker():
    with TemporaryDirectory(dir="cmd_outputs") as directory:
        database_path = Path(directory) / "workflow.db"
        engine = create_engine(
            f"sqlite:///{database_path.as_posix()}", connect_args={"check_same_thread": False}
        )
        event.listen(engine, "connect", configure_sqlite_connection)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        Base.metadata.create_all(engine)
        with Session() as setup:
            user = User(username="workflow-user", hashed_password="local-hash")
            setup.add(user)
            setup.commit()
            user_id = user.id
            _enqueue(WorkflowService(setup), user_id)

        barrier = Barrier(2)

        def claim(worker_id):
            with Session() as session:
                barrier.wait()
                run = WorkflowService(session).claim(worker_id=worker_id, lease_seconds=30)
                return run.id if run else None

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, ["worker-a", "worker-b"]))
        assert sum(result is not None for result in results) == 1
        engine.dispose()


def test_workflow_api_hides_payload_and_supports_cancel(client, auth_headers):
    response = client.post(
        "/api/v1/workflows",
        json={
            "workflow_type": "vault.export",
            "idempotency_key": "export-1",
            "payload": {"private_path": "not-returned"},
        },
        headers=auth_headers,
    )
    assert response.status_code == 202, response.text
    run = response.json()
    assert run["status"] == "queued"
    assert "payload" not in run
    cancelled = client.post(
        f"/api/v1/workflows/{run['id']}/cancel", headers=auth_headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
