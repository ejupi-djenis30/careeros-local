from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command
from backend.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PREVIOUS_HEAD = "b4c5d6e7f8a9"
LOGICAL_OPPORTUNITY_REVISION = "c5d6e7f8a9b0"

_OLD_APPLICATION_ID = "00000000-0000-0000-0000-000000000003"
_LATEST_LOW_ID = "00000000-0000-0000-0000-000000000001"
_LATEST_HIGH_ID = "00000000-0000-0000-0000-000000000002"
_MANUAL_APPLICATION_ID = "00000000-0000-0000-0000-000000000004"
_OTHER_USER_APPLICATION_ID = "00000000-0000-0000-0000-000000000005"
_SECOND_MANUAL_APPLICATION_ID = "00000000-0000-0000-0000-000000000006"


def _alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _application_row(
    *,
    application_id: str,
    user_id: int,
    job_id: int | None,
    updated_at: datetime,
) -> dict[str, object]:
    return {
        "id": application_id,
        "user_id": user_id,
        "job_id": job_id,
        "job_snapshot": {
            "title": "Platform engineer",
            "company": "Private employer",
        },
        "job_title": "Platform engineer",
        "job_company": "Private employer",
        "latest_event_at": updated_at,
        "created_at": updated_at,
        "updated_at": updated_at,
    }


def test_logical_opportunity_migration_backfills_and_round_trips(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "application-logical-opportunity.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    config = _alembic_config(database_url)
    engine = sa.create_engine(database_url)

    command.upgrade(config, PREVIOUS_HEAD)
    metadata = sa.MetaData()
    metadata.reflect(
        bind=engine,
        only=["users", "search_profiles", "scraped_jobs", "jobs", "applications"],
    )
    users = metadata.tables["users"]
    profiles = metadata.tables["search_profiles"]
    scraped_jobs = metadata.tables["scraped_jobs"]
    jobs = metadata.tables["jobs"]
    applications = metadata.tables["applications"]

    older_at = datetime(2026, 7, 24, 9, 0, tzinfo=timezone.utc)
    latest_at = datetime(2026, 7, 25, 9, 0, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            users.insert(),
            [
                {
                    "id": 101,
                    "username": "logical-opportunity-owner",
                    "hashed_password": "unused",
                },
                {
                    "id": 102,
                    "username": "other-logical-opportunity-owner",
                    "hashed_password": "unused",
                },
            ],
        )
        connection.execute(
            profiles.insert(),
            [
                {"id": 201, "user_id": 101, "name": "Primary"},
                {"id": 202, "user_id": 101, "name": "Secondary"},
                {"id": 203, "user_id": 101, "name": "Tertiary"},
                {"id": 204, "user_id": 102, "name": "Other user"},
            ],
        )
        connection.execute(
            scraped_jobs.insert().values(
                id=301,
                platform="migration-test",
                platform_job_id="shared-opportunity",
                title="Platform engineer",
                company="Private employer",
                external_url="https://example.test/jobs/shared-opportunity",
            )
        )
        connection.execute(
            jobs.insert(),
            [
                {
                    "id": 401,
                    "user_id": 101,
                    "search_profile_id": 201,
                    "scraped_job_id": 301,
                    "updated_at": older_at,
                },
                {
                    "id": 402,
                    "user_id": 101,
                    "search_profile_id": 202,
                    "scraped_job_id": 301,
                    "updated_at": latest_at,
                },
                {
                    "id": 403,
                    "user_id": 101,
                    "search_profile_id": 203,
                    "scraped_job_id": 301,
                    "updated_at": latest_at,
                },
                {
                    "id": 404,
                    "user_id": 102,
                    "search_profile_id": 204,
                    "scraped_job_id": 301,
                    "updated_at": latest_at,
                },
            ],
        )
        connection.execute(
            applications.insert(),
            [
                _application_row(
                    application_id=_OLD_APPLICATION_ID,
                    user_id=101,
                    job_id=401,
                    updated_at=older_at,
                ),
                _application_row(
                    application_id=_LATEST_HIGH_ID,
                    user_id=101,
                    job_id=402,
                    updated_at=latest_at,
                ),
                _application_row(
                    application_id=_LATEST_LOW_ID,
                    user_id=101,
                    job_id=403,
                    updated_at=latest_at,
                ),
                _application_row(
                    application_id=_MANUAL_APPLICATION_ID,
                    user_id=101,
                    job_id=None,
                    updated_at=latest_at,
                ),
                _application_row(
                    application_id=_OTHER_USER_APPLICATION_ID,
                    user_id=102,
                    job_id=404,
                    updated_at=latest_at,
                ),
            ],
        )

    command.upgrade(config, LOGICAL_OPPORTUNITY_REVISION)

    inspector = sa.inspect(engine)
    columns = {
        column["name"]: column for column in inspector.get_columns("applications")
    }
    assert columns["scraped_job_id"]["nullable"] is True
    assert {
        index["name"] for index in inspector.get_indexes("applications")
    } >= {"ix_applications_scraped_job_id"}
    assert {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("applications")
    }["uq_application_user_scraped_job"] == ("user_id", "scraped_job_id")
    logical_fk = next(
        foreign_key
        for foreign_key in inspector.get_foreign_keys("applications")
        if foreign_key["name"] == "fk_applications_scraped_job_id"
    )
    assert logical_fk["constrained_columns"] == ["scraped_job_id"]
    assert logical_fk["referred_table"] == "scraped_jobs"
    assert logical_fk.get("options", {}).get("ondelete") == "SET NULL"

    upgraded_metadata = sa.MetaData()
    upgraded_applications = sa.Table(
        "applications",
        upgraded_metadata,
        autoload_with=engine,
    )
    with engine.connect() as connection:
        rows = connection.execute(
            sa.select(
                upgraded_applications.c.id,
                upgraded_applications.c.scraped_job_id,
            ).order_by(upgraded_applications.c.id)
        ).mappings()
        logical_ids = {row["id"]: row["scraped_job_id"] for row in rows}

    assert logical_ids[_LATEST_LOW_ID] == 301
    assert logical_ids[_OTHER_USER_APPLICATION_ID] == 301
    assert logical_ids[_LATEST_HIGH_ID] is None
    assert logical_ids[_OLD_APPLICATION_ID] is None
    assert logical_ids[_MANUAL_APPLICATION_ID] is None

    duplicate = _application_row(
        application_id="00000000-0000-0000-0000-000000000007",
        user_id=101,
        job_id=None,
        updated_at=latest_at,
    )
    duplicate["scraped_job_id"] = 301
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(upgraded_applications.insert().values(**duplicate))

    second_manual = _application_row(
        application_id=_SECOND_MANUAL_APPLICATION_ID,
        user_id=101,
        job_id=None,
        updated_at=latest_at,
    )
    second_manual["scraped_job_id"] = None
    with engine.begin() as connection:
        connection.execute(upgraded_applications.insert().values(**second_manual))

    command.downgrade(config, PREVIOUS_HEAD)
    downgraded_inspector = sa.inspect(engine)
    assert "scraped_job_id" not in {
        column["name"]
        for column in downgraded_inspector.get_columns("applications")
    }
    assert "ix_applications_scraped_job_id" not in {
        index["name"] for index in downgraded_inspector.get_indexes("applications")
    }
    assert "uq_application_user_scraped_job" not in {
        constraint["name"]
        for constraint in downgraded_inspector.get_unique_constraints("applications")
    }

    command.upgrade(config, "head")
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["e7f8a9b0c1d2"]

    round_trip_metadata = sa.MetaData()
    round_trip_applications = sa.Table(
        "applications",
        round_trip_metadata,
        autoload_with=engine,
    )
    with engine.connect() as connection:
        round_trip_rows = connection.execute(
            sa.select(
                round_trip_applications.c.id,
                round_trip_applications.c.scraped_job_id,
            )
        ).mappings()
        round_trip_ids = {
            row["id"]: row["scraped_job_id"] for row in round_trip_rows
        }
    assert round_trip_ids[_LATEST_LOW_ID] == 301
    assert round_trip_ids[_OTHER_USER_APPLICATION_ID] == 301
    assert round_trip_ids[_SECOND_MANUAL_APPLICATION_ID] is None
    assert len(round_trip_ids) == 6

    dossier_inspector = sa.inspect(engine)
    assert "application_dossier_drafts" in dossier_inspector.get_table_names()
    dossier_columns = {
        column["name"]: column
        for column in dossier_inspector.get_columns("application_dossier_drafts")
    }
    assert set(dossier_columns) == {
        "id",
        "application_id",
        "resume_version_id",
        "application_revision",
        "revision",
        "content",
        "created_at",
        "updated_at",
    }
    assert all(not column["nullable"] for column in dossier_columns.values())
    assert {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in dossier_inspector.get_unique_constraints(
            "application_dossier_drafts"
        )
    }["uq_application_dossier_draft_application"] == ("application_id",)
    dossier_foreign_keys = {
        tuple(foreign_key["constrained_columns"]): foreign_key
        for foreign_key in dossier_inspector.get_foreign_keys(
            "application_dossier_drafts"
        )
    }
    assert dossier_foreign_keys[("application_id",)]["referred_table"] == "applications"
    assert dossier_foreign_keys[("application_id",)].get("options", {}).get("ondelete") == (
        "CASCADE"
    )
    assert dossier_foreign_keys[("resume_version_id",)]["referred_table"] == "resume_versions"
    assert dossier_foreign_keys[("resume_version_id",)].get("options", {}).get("ondelete") == (
        "CASCADE"
    )

    command.downgrade(config, "d6e7f8a9b0c1")
    assert "application_dossier_drafts" not in sa.inspect(engine).get_table_names()
    command.upgrade(config, "head")
    assert "application_dossier_drafts" in sa.inspect(engine).get_table_names()
    engine.dispose()
