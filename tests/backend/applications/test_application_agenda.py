from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.applications.agenda import ApplicationAgendaService
from backend.applications.models import Application
from backend.applications.schemas import ApplicationAgendaResponse
from backend.applications.service import ApplicationValidationError
from backend.db.base import Base, configure_sqlite_connection
from backend.models import User
from backend.services.auth import get_password_hash


def _application(
    *,
    user_id: int,
    title: str,
    latest_event_at: datetime,
    due_at: datetime | None | object = ...,
    priority: str = "normal",
    stage: str = "applied",
) -> Application:
    task_values = {}
    if due_at is not ...:
        task_values = {
            "next_action_task_id": f"task-{title.casefold().replace(' ', '-')}",
            "next_action_title": f"Act on {title}",
            "next_action_at": due_at,
            "next_action_priority": priority,
        }
    return Application(
        user_id=user_id,
        revision=1,
        current_stage=stage,
        job_snapshot={"title": title, "company": "Private Company"},
        job_title=title,
        job_company="Private Company",
        latest_event_at=latest_event_at,
        **task_values,
    )


@pytest.fixture
def agenda_database_path():
    with TemporaryDirectory(prefix="careeros-agenda-snapshot-") as directory:
        yield Path(directory) / "agenda.sqlite3"


def test_agenda_classifies_local_day_orders_and_accounts_for_omissions(
    db_session, test_user
):
    now = datetime(2026, 7, 23, 20, 30, tzinfo=timezone.utc)
    rows = [
        _application(
            user_id=test_user.id,
            title="Overdue",
            latest_event_at=now - timedelta(days=2),
            due_at=now - timedelta(hours=2),
            priority="low",
        ),
        _application(
            user_id=test_user.id,
            title="Today",
            latest_event_at=now - timedelta(days=1),
            due_at=now + timedelta(hours=1),
            priority="normal",
        ),
        _application(
            user_id=test_user.id,
            title="Upcoming",
            latest_event_at=now - timedelta(hours=3),
            due_at=now + timedelta(hours=2),
            priority="urgent",
        ),
        _application(
            user_id=test_user.id,
            title="Later",
            latest_event_at=now,
            due_at=now + timedelta(days=10),
            priority="urgent",
        ),
        _application(
            user_id=test_user.id,
            title="Undated",
            latest_event_at=now - timedelta(days=4),
            due_at=None,
            priority="high",
        ),
        _application(
            user_id=test_user.id,
            title="No next action",
            latest_event_at=now - timedelta(days=8),
        ),
        _application(
            user_id=test_user.id,
            title="Closed",
            latest_event_at=now,
            due_at=now - timedelta(days=1),
            stage="archived",
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()

    result = ApplicationAgendaService(db_session).build(
        test_user.id,
        local_day_end=datetime(2026, 7, 23, 22, 0, tzinfo=timezone.utc),
        horizon_days=7,
        limit=3,
        now=now,
    )

    assert result.generated_at == now
    assert result.local_day_end == datetime(2026, 7, 23, 22, 0, tzinfo=timezone.utc)
    assert result.horizon_end == now + timedelta(days=7)
    assert result.active_count == 6
    assert result.visible_count == 5
    assert result.later_count == 1
    assert result.truncated_count == 2
    assert [(item.title, item.state) for item in result.items] == [
        ("Overdue", "overdue"),
        ("Today", "today"),
        ("Upcoming", "upcoming"),
    ]

    complete = ApplicationAgendaService(db_session).build(
        test_user.id,
        local_day_end=datetime(2026, 7, 23, 22, 0, tzinfo=timezone.utc),
        horizon_days=7,
        limit=20,
        now=now,
    )
    assert [(item.title, item.state) for item in complete.items] == [
        ("Overdue", "overdue"),
        ("Today", "today"),
        ("Upcoming", "upcoming"),
        ("Undated", "unscheduled"),
        ("No next action", "needs_action"),
    ]


def test_agenda_is_user_scoped_and_reads_only_scalar_projections(db_session, test_user):
    now = datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc)
    foreign_user = User(
        username="agenda-foreign",
        hashed_password=get_password_hash("Foreignpass1"),
    )
    db_session.add(foreign_user)
    db_session.flush()
    db_session.add_all(
        [
            _application(
                user_id=test_user.id,
                title="Owned role",
                latest_event_at=now,
                due_at=now + timedelta(hours=1),
            ),
            _application(
                user_id=foreign_user.id,
                title="Foreign secret role",
                latest_event_at=now,
                due_at=now - timedelta(hours=1),
                priority="urgent",
            ),
        ]
    )
    db_session.commit()

    statements: list[tuple[str, object]] = []

    def capture_sql(_connection, _cursor, statement, parameters, _context, _executemany):
        statements.append((statement, parameters))

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        result = ApplicationAgendaService(db_session).build(
            test_user.id,
            local_day_end=now + timedelta(hours=14),
            now=now,
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)

    assert [item.title for item in result.items] == ["Owned role"]
    assert result.active_count == 1
    assert statements
    normalized_statements = [statement.casefold() for statement, _ in statements]
    assert sum("select" in statement for statement in normalized_statements) == 1
    assert normalized_statements[0].lstrip().startswith("with agenda_classified")
    assert all("application_events" not in statement for statement in normalized_statements)
    assert all("job_snapshot" not in statement for statement in normalized_statements)
    assert all("payload" not in statement for statement in normalized_statements)
    assert "row_number() over" in normalized_statements[0]

    statement, parameters = statements[0]
    query_plan = db_session.connection().exec_driver_sql(
        f"EXPLAIN QUERY PLAN {statement}",
        parameters,
    )
    plan_details = [str(row[-1]) for row in query_plan]
    assert plan_details
    assert all("application_events" not in detail.casefold() for detail in plan_details)
    index_rows = db_session.connection().exec_driver_sql(
        "PRAGMA index_list('applications')"
    )
    index_names = {str(row[1]) for row in index_rows}
    assert "ix_applications_user_stage_next_action" in index_names


def test_agenda_counts_and_rows_share_one_snapshot_during_interleaved_write(
    agenda_database_path,
):
    engine = create_engine(
        f"sqlite:///{agenda_database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", configure_sqlite_connection)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc)
    with Session() as setup:
        user = User(username="agenda-snapshot", hashed_password="test-only")
        setup.add(user)
        setup.flush()
        setup.add(
            _application(
                user_id=user.id,
                title="Before statement",
                latest_event_at=now,
                due_at=now + timedelta(hours=1),
            )
        )
        setup.commit()
        user_id = user.id

    interleaved = False

    def write_after_statement(_connection, _cursor, statement, *_args):
        nonlocal interleaved
        if interleaved or not statement.casefold().lstrip().startswith("with agenda_classified"):
            return
        interleaved = True
        with Session() as writer:
            writer.add(
                _application(
                    user_id=user_id,
                    title="After statement",
                    latest_event_at=now,
                    due_at=now + timedelta(hours=2),
                )
            )
            writer.commit()

    event.listen(engine, "after_cursor_execute", write_after_statement)
    try:
        with Session() as reader:
            before = ApplicationAgendaService(reader).build(
                user_id,
                local_day_end=now + timedelta(hours=14),
                now=now,
            )
    finally:
        event.remove(engine, "after_cursor_execute", write_after_statement)

    assert interleaved is True
    assert before.active_count == before.visible_count + before.later_count == 1
    assert [item.title for item in before.items] == ["Before statement"]
    with Session() as verification:
        after = ApplicationAgendaService(verification).build(
            user_id,
            local_day_end=now + timedelta(hours=14),
            now=now,
        )
    assert after.active_count == 2
    assert [item.title for item in after.items] == ["Before statement", "After statement"]
    engine.dispose()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"horizon_days": 0}, "Agenda horizon"),
        ({"limit": 201}, "Agenda limit"),
        ({"now": datetime(2026, 7, 23, 10, 0)}, "include a timezone"),
        ({"local_day_end": datetime(2026, 7, 24, 0, 0)}, "include a timezone"),
        (
            {
                "local_day_end": datetime(2026, 7, 23, 9, 59, tzinfo=timezone.utc),
            },
            "must be in the future",
        ),
        (
            {
                "local_day_end": datetime(2026, 7, 24, 12, 1, tzinfo=timezone.utc),
            },
            "more than 26 hours",
        ),
    ],
)
def test_agenda_rejects_unbounded_or_ambiguous_inputs(db_session, test_user, kwargs, message):
    kwargs = {
        "local_day_end": datetime(2026, 7, 24, 0, 0, tzinfo=timezone.utc),
        "now": datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc),
        **kwargs,
    }
    with pytest.raises(ApplicationValidationError, match=message):
        ApplicationAgendaService(db_session).build(test_user.id, **kwargs)


def test_agenda_rejects_an_incomplete_next_action_projection(db_session, test_user):
    now = datetime(2026, 7, 23, 10, 0, tzinfo=timezone.utc)
    application = _application(
        user_id=test_user.id,
        title="Broken projection",
        latest_event_at=now,
    )
    application.next_action_task_id = "task-broken"
    db_session.add(application)
    db_session.commit()

    with pytest.raises(ApplicationValidationError, match="projection is incomplete"):
        ApplicationAgendaService(db_session).build(
            test_user.id,
            local_day_end=now + timedelta(hours=14),
            now=now,
        )


def test_agenda_api_is_static_authenticated_and_bounds_inputs(
    client, auth_headers, db_session, test_user
):
    now = datetime.now(timezone.utc)
    foreign_user = User(
        username="agenda-api-foreign",
        hashed_password=get_password_hash("Foreignpass1"),
    )
    db_session.add(foreign_user)
    db_session.flush()
    db_session.add_all(
        [
            _application(
                user_id=test_user.id,
                title="Owned API role",
                latest_event_at=now,
                due_at=now + timedelta(hours=1),
            ),
            _application(
                user_id=foreign_user.id,
                title="Foreign API role",
                latest_event_at=now,
                due_at=now - timedelta(hours=1),
            ),
        ]
    )
    db_session.commit()

    valid_params = {
        "local_day_end": (now + timedelta(hours=12)).isoformat(),
        "horizon_days": 7,
        "limit": 50,
    }
    response = client.get(
        "/api/v1/applications/agenda",
        params=valid_params,
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["active_count"] == 1
    assert [item["title"] for item in payload["items"]] == ["Owned API role"]
    assert "Foreign API role" not in response.text

    unauthenticated = client.get("/api/v1/applications/agenda", params=valid_params)
    assert unauthenticated.status_code == 401
    for params in (
        {**valid_params, "horizon_days": 0},
        {**valid_params, "limit": 201},
        {**valid_params, "local_day_end": now.replace(tzinfo=None).isoformat()},
        {
            **valid_params,
            "local_day_end": (now + timedelta(hours=27)).isoformat(),
        },
    ):
        invalid = client.get(
            "/api/v1/applications/agenda",
            params=params,
            headers=auth_headers,
        )
        assert invalid.status_code == 422


def test_agenda_route_translates_schema_validation_to_422(
    client, auth_headers, monkeypatch
):
    now = datetime.now(timezone.utc)

    def invalid_response(*_args, **_kwargs):
        return ApplicationAgendaResponse(
            generated_at=now,
            local_day_end=now + timedelta(hours=12),
            horizon_end=now + timedelta(days=7),
            active_count=1,
            visible_count=0,
            later_count=0,
            truncated_count=0,
            items=[],
        )

    monkeypatch.setattr(ApplicationAgendaService, "build", invalid_response)
    response = client.get(
        "/api/v1/applications/agenda",
        params={"local_day_end": (now + timedelta(hours=12)).isoformat()},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Application agenda projection is invalid"
