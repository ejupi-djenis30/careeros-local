from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PREVIOUS_HEAD = "c5d6e7f8a9b0"
TIMESTAMP_DEFAULT_REVISION = "d6e7f8a9b0c1"
CURRENT_HEAD = "a9b0c1d2e3f4"


def _alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _schema_contract(inspector: sa.Inspector) -> tuple[set[tuple], set[tuple], set[tuple]]:
    indexes = {
        (
            index["name"],
            tuple(index["column_names"]),
            bool(index["unique"]),
        )
        for index in inspector.get_indexes("jobs")
    }
    unique_constraints = {
        (
            constraint["name"],
            tuple(constraint["column_names"]),
        )
        for constraint in inspector.get_unique_constraints("jobs")
    }
    foreign_keys = {
        (
            foreign_key["name"],
            tuple(foreign_key["constrained_columns"]),
            foreign_key["referred_table"],
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys("jobs")
    }
    return indexes, unique_constraints, foreign_keys


def _has_current_timestamp_default(default: object) -> bool:
    normalized = str(default or "").lower().replace("(", "").replace(")", "")
    return "current_timestamp" in normalized or "now" in normalized


def test_job_timestamp_default_migration_supports_database_managed_inserts(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "job-timestamp-default.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    config = _alembic_config(database_url)
    engine = sa.create_engine(database_url)

    command.upgrade(config, PREVIOUS_HEAD)
    before_inspector = sa.inspect(engine)
    before_columns = {column["name"]: column for column in before_inspector.get_columns("jobs")}
    assert before_columns["updated_at"]["nullable"] is False
    assert before_columns["updated_at"]["default"] is None
    schema_before = _schema_contract(before_inspector)

    metadata = sa.MetaData()
    metadata.reflect(bind=engine, only=["users", "scraped_jobs", "jobs"])
    users = metadata.tables["users"]
    scraped_jobs = metadata.tables["scraped_jobs"]
    jobs = metadata.tables["jobs"]
    existing_updated_at = datetime(2026, 7, 26, 10, 30, tzinfo=timezone.utc)

    with engine.begin() as connection:
        connection.execute(
            users.insert().values(
                id=101,
                username="timestamp-default-owner",
                hashed_password="unused",
            )
        )
        connection.execute(
            scraped_jobs.insert(),
            [
                {
                    "id": 201,
                    "platform": "migration-test",
                    "platform_job_id": "existing",
                    "title": "Existing role",
                    "company": "Example",
                    "external_url": "https://example.test/jobs/existing",
                },
                {
                    "id": 202,
                    "platform": "migration-test",
                    "platform_job_id": "after-upgrade",
                    "title": "New role",
                    "company": "Example",
                    "external_url": "https://example.test/jobs/after-upgrade",
                },
                {
                    "id": 203,
                    "platform": "migration-test",
                    "platform_job_id": "after-round-trip",
                    "title": "Round-trip role",
                    "company": "Example",
                    "external_url": "https://example.test/jobs/after-round-trip",
                },
            ],
        )
        connection.execute(
            jobs.insert().values(
                id=301,
                user_id=101,
                scraped_job_id=201,
                updated_at=existing_updated_at,
            )
        )

    command.upgrade(config, TIMESTAMP_DEFAULT_REVISION)

    upgraded_inspector = sa.inspect(engine)
    upgraded_columns = {column["name"]: column for column in upgraded_inspector.get_columns("jobs")}
    assert upgraded_columns["updated_at"]["nullable"] is False
    assert _has_current_timestamp_default(upgraded_columns["updated_at"]["default"])
    assert _schema_contract(upgraded_inspector) == schema_before

    upgraded_metadata = sa.MetaData()
    upgraded_jobs = sa.Table("jobs", upgraded_metadata, autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(
            upgraded_jobs.insert().values(
                id=302,
                user_id=101,
                scraped_job_id=202,
            )
        )
    with engine.connect() as connection:
        rows = connection.execute(
            sa.select(upgraded_jobs.c.id, upgraded_jobs.c.updated_at).order_by(upgraded_jobs.c.id)
        ).all()
    assert [row.id for row in rows] == [301, 302]
    assert rows[0].updated_at == existing_updated_at.replace(tzinfo=None)
    assert rows[1].updated_at is not None

    command.downgrade(config, PREVIOUS_HEAD)
    downgraded_inspector = sa.inspect(engine)
    downgraded_columns = {
        column["name"]: column for column in downgraded_inspector.get_columns("jobs")
    }
    assert downgraded_columns["updated_at"]["nullable"] is False
    assert downgraded_columns["updated_at"]["default"] is None
    assert _schema_contract(downgraded_inspector) == schema_before

    downgraded_metadata = sa.MetaData()
    downgraded_jobs = sa.Table("jobs", downgraded_metadata, autoload_with=engine)
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                downgraded_jobs.insert().values(
                    id=303,
                    user_id=101,
                    scraped_job_id=203,
                )
            )

    command.upgrade(config, "head")
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == [CURRENT_HEAD]

    round_trip_metadata = sa.MetaData()
    round_trip_jobs = sa.Table("jobs", round_trip_metadata, autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(
            round_trip_jobs.insert().values(
                id=303,
                user_id=101,
                scraped_job_id=203,
            )
        )
    with engine.connect() as connection:
        round_trip_rows = connection.execute(
            sa.select(
                round_trip_jobs.c.id,
                round_trip_jobs.c.updated_at,
            ).order_by(round_trip_jobs.c.id)
        ).all()
    assert [row.id for row in round_trip_rows] == [301, 302, 303]
    assert all(row.updated_at is not None for row in round_trip_rows)
    assert _schema_contract(sa.inspect(engine)) == schema_before
    engine.dispose()
