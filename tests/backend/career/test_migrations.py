from pathlib import Path
from tempfile import TemporaryDirectory

import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from backend.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_scraped_job_migration_preserves_sqlite_rows_and_round_trips(monkeypatch):
    temporary = TemporaryDirectory()
    database_path = Path(temporary.name) / "migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    config = _alembic_config(database_url)

    command.upgrade(config, "a1b2c3d4e5f6")
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "INSERT INTO users (id, username, hashed_password) "
                        "VALUES (1, 'migration-user', 'local-hash')"
                    )
                )
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO jobs (
                            id, user_id, title, company, description, external_url,
                            platform, platform_job_id, affinity_score
                        ) VALUES
                            (1, 1, 'Engineer', 'Local Co', 'First',
                             'https://jobs.example/1', 'fixture', 'job-1', 90),
                            (2, 1, 'Engineer duplicate', 'Local Co', 'Second',
                             'https://jobs.example/duplicate', 'fixture', 'job-1', 80),
                            (3, 1, NULL, NULL, 'Legacy nullable row',
                             NULL, NULL, NULL, 70)
                        """
                    )
                )

        command.upgrade(config, "7d76134d9a36")
        with engine.connect() as connection:
                assert connection.scalar(sa.text("SELECT count(*) FROM jobs")) == 3
                assert connection.scalar(sa.text("SELECT count(*) FROM scraped_jobs")) == 2
                assert (
                    connection.scalar(
                        sa.text("SELECT count(*) FROM jobs WHERE scraped_job_id IS NULL")
                    )
                    == 0
                )
                fallback = connection.execute(
                    sa.text(
                        "SELECT title, company, external_url FROM scraped_jobs "
                        "WHERE platform = 'unknown'"
                    )
                ).one()
                assert fallback == ("Untitled role", "Unknown company", "local://legacy-job/3")
                foreign_keys = connection.execute(sa.text("PRAGMA foreign_key_list(jobs)")).all()
                assert any(row[2] == "scraped_jobs" for row in foreign_keys)

        command.downgrade(config, "a1b2c3d4e5f6")
        inspector = sa.inspect(engine)
        assert "scraped_jobs" not in inspector.get_table_names()
        assert "external_url" in {column["name"] for column in inspector.get_columns("jobs")}
        with engine.connect() as connection:
                assert connection.scalar(sa.text("SELECT count(*) FROM jobs")) == 3
                restored = connection.execute(
                    sa.text("SELECT title, company, external_url FROM jobs WHERE id = 3")
                ).one()
                assert restored == (
                    "Untitled role",
                    "Unknown company",
                    "local://legacy-job/3",
                )

        command.upgrade(config, "7d76134d9a36")
        with engine.connect() as connection:
                assert connection.scalar(sa.text("SELECT count(*) FROM jobs")) == 3
                assert connection.scalar(sa.text("SELECT count(*) FROM scraped_jobs")) == 2
    finally:
        engine.dispose()
        temporary.cleanup()


def test_resume_schema_migrates_to_head_and_round_trips(monkeypatch):
    temporary = TemporaryDirectory()
    database_path = Path(temporary.name) / "head.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    config = _alembic_config(database_url)

    command.upgrade(config, "head")
    engine = sa.create_engine(database_url)
    try:
        expected = {"resume_drafts", "resume_versions", "resume_artifacts"}
        assert expected <= set(sa.inspect(engine).get_table_names())
        command.downgrade(config, "s9t0u1v2w3x4")
        assert expected.isdisjoint(sa.inspect(engine).get_table_names())
        command.upgrade(config, "head")
        assert expected <= set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()
        temporary.cleanup()
