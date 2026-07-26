from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from backend.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PREVIOUS_HEAD = "f2a3b4c5d6e7"
OBSERVATION_REVISION = "a3b4c5d6e7f8"


def _alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_listing_observation_migration_backfills_conservatively(tmp_path, monkeypatch):
    database_path = tmp_path / "listing-observation.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    config = _alembic_config(database_url)
    engine = sa.create_engine(database_url)

    command.upgrade(config, PREVIOUS_HEAD)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO scraped_jobs (
                    platform,
                    platform_job_id,
                    title,
                    company,
                    external_url,
                    created_at,
                    updated_at
                )
                VALUES (
                    'fixture',
                    'job-1',
                    'Existing role',
                    'Example',
                    'https://example.test/jobs/1',
                    '2026-07-01 08:30:00',
                    '2026-07-20 17:45:00'
                )
                """
            )
        )

    command.upgrade(config, OBSERVATION_REVISION)
    inspector = sa.inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("scraped_jobs")}
    assert columns["first_seen_at"]["nullable"] is False
    assert columns["last_seen_at"]["nullable"] is False
    assert columns["last_changed_at"]["nullable"] is False
    assert columns["content_revision"]["nullable"] is False
    assert "ix_scraped_jobs_last_seen_at" in {
        index["name"] for index in inspector.get_indexes("scraped_jobs")
    }

    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                """
                SELECT
                    first_seen_at = created_at AS first_matches_created,
                    last_seen_at = created_at AS last_matches_created,
                    last_changed_at = created_at AS changed_matches_created,
                    content_revision
                FROM scraped_jobs
                WHERE platform = 'fixture' AND platform_job_id = 'job-1'
                """
            )
        ).one()
    assert tuple(row) == (1, 1, 1, 1)

    command.downgrade(config, PREVIOUS_HEAD)
    downgraded_columns = {
        column["name"] for column in sa.inspect(engine).get_columns("scraped_jobs")
    }
    assert {
        "first_seen_at",
        "last_seen_at",
        "last_changed_at",
        "content_revision",
    }.isdisjoint(downgraded_columns)
