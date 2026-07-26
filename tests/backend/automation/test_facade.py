from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from backend.applications.schemas import ApplicationCreate, ManualJobSnapshot
from backend.applications.service import ApplicationService
from backend.automation.facade import AutomationFacade, AutomationFacadeError
from backend.automation.grants import AutomationPrincipal
from backend.db.base import SessionLocal
from backend.models import User


def _facade(user_id: int, *scopes: str) -> AutomationFacade:
    return AutomationFacade(
        SessionLocal,
        AutomationPrincipal(
            grant_id="test-grant",
            user_id=user_id,
            scopes=frozenset(scopes),  # type: ignore[arg-type]
        ),
    )


def test_facade_exposes_only_owned_bounded_application_projections(db_session, test_user) -> None:
    application = ApplicationService(db_session).create(
        test_user.id,
        ApplicationCreate(
            manual_job=ManualJobSnapshot(
                title="Platform Engineer",
                company="Example Cooperative",
                location="Zurich",
            )
        ),
    )
    facade = _facade(test_user.id, "applications:read")

    listing = facade.list_applications(limit=10)
    readiness = facade.application_readiness(application.id)
    agenda = facade.application_agenda(
        horizon_days=7,
        limit=10,
        timezone_offset_minutes=120,
    )

    assert listing.returned_count == 1
    assert listing.items[0].id == application.id
    assert listing.items[0].company == "Example Cooperative"
    assert readiness.application_id == application.id
    assert readiness.blocker_count >= 1
    assert agenda.active_count == 1
    assert agenda.items[0].application_id == application.id
    assert "events" not in listing.items[0].model_dump()
    assert "job_snapshot" not in listing.items[0].model_dump()


def test_application_tools_never_cross_the_authorized_user_boundary(db_session, test_user) -> None:
    foreign_user = User(username="foreign-automation-user", hashed_password="not-used")
    db_session.add(foreign_user)
    db_session.commit()
    db_session.refresh(foreign_user)
    owned = ApplicationService(db_session).create(
        test_user.id,
        ApplicationCreate(
            manual_job=ManualJobSnapshot(title="Owned role", company="Owned cooperative")
        ),
    )
    foreign = ApplicationService(db_session).create(
        foreign_user.id,
        ApplicationCreate(
            manual_job=ManualJobSnapshot(title="Private role", company="Foreign private company")
        ),
    )
    facade = _facade(test_user.id, "applications:read")

    listing = facade.list_applications(limit=10)
    agenda = facade.application_agenda(limit=10)

    assert [item.id for item in listing.items] == [owned.id]
    assert {item.application_id for item in agenda.items} == {owned.id}
    assert foreign.id not in str(listing.model_dump())
    assert "Foreign private company" not in str(listing.model_dump())
    with pytest.raises(AutomationFacadeError) as raised:
        facade.application_readiness(foreign.id)
    assert raised.value.code == "application_not_found"


def test_read_operations_do_not_mutate_domain_rows(db_session, test_user) -> None:
    ApplicationService(db_session).create(
        test_user.id,
        ApplicationCreate(manual_job=ManualJobSnapshot(title="SRE", company="Example Association")),
    )
    before = db_session.execute(
        text("SELECT id, revision, updated_at FROM applications ORDER BY id")
    ).all()
    facade = _facade(test_user.id, "career:read", "resume:read", "applications:read")

    assert facade.career_summary().profile_exists is False
    assert facade.resume_catalog().resumes == []
    facade.list_applications()
    facade.application_agenda()

    db_session.expire_all()
    after = db_session.execute(
        text("SELECT id, revision, updated_at FROM applications ORDER BY id")
    ).all()
    assert after == before


def test_scope_checks_and_page_bounds_fail_before_data_access(db_session, test_user) -> None:
    facade = _facade(test_user.id, "system:read")
    with pytest.raises(AutomationFacadeError) as denied:
        facade.list_applications()
    assert denied.value.code == "scope_denied"

    scoped = _facade(test_user.id, "applications:read")
    with pytest.raises(AutomationFacadeError) as invalid:
        scoped.list_applications(limit=51)
    assert invalid.value.code == "invalid_page"


def test_system_status_discloses_no_local_path_or_principal_id(db_session, test_user) -> None:
    db_session.execute(
        text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
    )
    db_session.execute(text("DELETE FROM alembic_version"))
    db_session.execute(text("INSERT INTO alembic_version VALUES ('test-head')"))
    db_session.commit()
    facade = _facade(test_user.id, "system:read", "applications:read")

    payload = facade.system_status().model_dump(mode="json")

    assert payload["database_revision"] == "test-head"
    assert payload["access_mode"] == "read_only"
    rendered = str(payload)
    assert "user_id" not in payload
    assert "grant_id" not in payload
    assert "data_dir" not in rendered
    assert "database_url" not in rendered
    assert "get_application_agenda" in payload["available_tools"]


def test_agenda_uses_explicit_timezone_boundary(db_session, test_user) -> None:
    facade = _facade(test_user.id, "applications:read")
    agenda = facade.application_agenda(timezone_offset_minutes=-300)
    assert agenda.generated_at.tzinfo is not None
    assert agenda.local_day_end.tzinfo is not None
    assert agenda.local_day_end > datetime.now(UTC)
