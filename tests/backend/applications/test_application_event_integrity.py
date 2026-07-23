from __future__ import annotations

import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.applications.models import Application, ApplicationEvent
from backend.applications.schemas import ApplicationEventCreate
from backend.applications.service import (
    ApplicationConflictError,
    ApplicationService,
    ApplicationValidationError,
)
from backend.db.base import Base, configure_sqlite_connection
from backend.models import User


@pytest.fixture
def file_database_path():
    # Avoid pytest's Windows ``tmp_path`` current-symlink, which cannot be resolved on
    # hosts where that symlink type is disabled (WinError 1463).
    with tempfile.TemporaryDirectory(prefix="careeros-application-cas-") as directory:
        yield Path(directory) / "application-cas.sqlite3"


def _task_payload(*, task_id: str, revision: int, updated_at: datetime, title: str = "Apply"):
    created_at = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)
    return {
        "task": {
            "id": task_id,
            "title": title,
            "status": "pending",
            "priority": "normal",
            "due_at": None,
            "reminder_at": None,
            "completed_at": None,
            "revision": revision,
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat(),
        }
    }


def test_task_replay_selects_highest_revision_not_latest_event_timestamp():
    task_id = "10000000-0000-4000-8000-000000000001"
    first_time = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)
    second_time = first_time + timedelta(hours=1)
    application = SimpleNamespace(
        events=[
            # Relationship ordering is based on occurred_at.  A user-supplied historical
            # timestamp can therefore place revision 2 before revision 1 in this collection.
            SimpleNamespace(
                event_type="task_updated",
                payload=_task_payload(
                    task_id=task_id, revision=2, updated_at=second_time, title="Tailor resume"
                ),
            ),
            SimpleNamespace(
                event_type="task_created",
                payload=_task_payload(task_id=task_id, revision=1, updated_at=first_time),
            ),
        ]
    )

    replayed = ApplicationService._task_snapshots(application)

    assert [(task.revision, task.title) for task in replayed] == [(2, "Tailor resume")]


def test_task_replay_rejects_regression_and_conflicting_duplicate_revision():
    task_id = "10000000-0000-4000-8000-000000000002"
    first_time = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)
    regressed = SimpleNamespace(
        events=[
            SimpleNamespace(
                event_type="task_created",
                payload=_task_payload(task_id=task_id, revision=1, updated_at=first_time),
            ),
            SimpleNamespace(
                event_type="task_updated",
                payload=_task_payload(
                    task_id=task_id,
                    revision=2,
                    updated_at=first_time - timedelta(minutes=1),
                ),
            ),
        ]
    )
    with pytest.raises(ApplicationValidationError, match="regressed"):
        ApplicationService._task_snapshots(regressed)

    duplicate = SimpleNamespace(
        events=[
            SimpleNamespace(
                event_type="task_created",
                payload=_task_payload(task_id=task_id, revision=1, updated_at=first_time),
            ),
            SimpleNamespace(
                event_type="task_created",
                payload=_task_payload(
                    task_id=task_id, revision=1, updated_at=first_time, title="Changed payload"
                ),
            ),
        ]
    )
    with pytest.raises(ApplicationValidationError, match="Conflicting duplicate"):
        ApplicationService._task_snapshots(duplicate)


def test_application_board_reads_next_action_projection_without_replaying_events(
    db_session, test_user, monkeypatch
):
    now = datetime.now(timezone.utc)
    application = Application(
        user_id=test_user.id,
        revision=2,
        current_stage="preparing",
        job_snapshot={"title": "Platform Engineer", "company": "Local Systems"},
        next_action_task_id="10000000-0000-4000-8000-000000000003",
        next_action_title="Send tailored application",
        next_action_at=now + timedelta(days=1),
        next_action_priority="high",
    )
    db_session.add(application)
    db_session.flush()
    db_session.add(
        ApplicationEvent(
            application_id=application.id,
            event_type="stage",
            stage="preparing",
            occurred_at=now,
            payload={"initial": True},
            created_at=now,
        )
    )
    db_session.commit()

    def forbidden_replay(_application):
        raise AssertionError("the board must not replay task events")

    monkeypatch.setattr(ApplicationService, "_task_snapshots", staticmethod(forbidden_replay))
    statements: list[str] = []

    def capture_sql(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.casefold())

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        result = ApplicationService(db_session).list(test_user.id)
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)

    assert result[0].next_action is not None
    assert result[0].next_action.id == application.next_action_task_id
    assert result[0].next_action.title == "Send tailored application"
    assert not hasattr(result[0].next_action, "status")
    assert statements
    assert all("application_events" not in statement for statement in statements)
    assert all("job_snapshot" not in statement for statement in statements)
    assert sum("select" in statement for statement in statements) == 1


def test_stage_event_cas_has_one_winner(file_database_path):
    database_path = file_database_path
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", configure_sqlite_connection)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as bootstrap:
        user = User(username="application-cas-user", hashed_password="test-only")
        bootstrap.add(user)
        bootstrap.flush()
        now = datetime.now(timezone.utc)
        application = Application(
            user_id=user.id,
            revision=1,
            current_stage="saved",
            job_snapshot={"title": "Role", "company": "Company"},
        )
        bootstrap.add(application)
        bootstrap.flush()
        bootstrap.add(
            ApplicationEvent(
                application_id=application.id,
                event_type="stage",
                stage="saved",
                occurred_at=now,
                payload={"initial": True},
                created_at=now,
            )
        )
        bootstrap.commit()
        user_id = user.id
        application_id = application.id

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def worker(note: str) -> None:
        with Session() as session:
            service = ApplicationService(session)
            original_advance = service._advance_revision

            def synchronized_advance(application, expected_revision, now, values=None):
                barrier.wait(timeout=5)
                return original_advance(application, expected_revision, now, values)

            service._advance_revision = synchronized_advance  # type: ignore[method-assign]
            try:
                service.append_event(
                    user_id,
                    application_id,
                    ApplicationEventCreate(
                        expected_revision=1,
                        event_type="stage",
                        stage="preparing",
                        note=note,
                    ),
                )
            except ApplicationConflictError:
                outcome = "conflict"
            else:
                outcome = "success"
            with outcomes_lock:
                outcomes.append(outcome)

    threads = [
        threading.Thread(target=worker, args=("first",)),
        threading.Thread(target=worker, args=("second",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert sorted(outcomes) == ["conflict", "success"]
    with Session() as verification:
        application = verification.get(Application, application_id)
        assert application is not None
        assert application.revision == 2
        assert application.current_stage == "preparing"
        stage_events = (
            verification.query(ApplicationEvent)
            .filter(
                ApplicationEvent.application_id == application_id,
                ApplicationEvent.stage == "preparing",
            )
            .all()
        )
        assert len(stage_events) == 1
    engine.dispose()
