import json
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command
from backend.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PREVIOUS_HEAD = "a3b4c5d6e7f8"
RECEIPT_REVISION = "b4c5d6e7f8a9"


def _alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_search_receipt_migration_backfills_only_valid_done_statuses(tmp_path, monkeypatch):
    database_path = tmp_path / "search-receipt.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    config = _alembic_config(database_url)
    engine = sa.create_engine(database_url)

    command.upgrade(config, PREVIOUS_HEAD)
    metadata = sa.MetaData()
    users = sa.Table("users", metadata, autoload_with=engine)
    profiles = sa.Table("search_profiles", metadata, autoload_with=engine)
    started_at = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)
    finished_at = datetime(2026, 7, 25, 8, 5, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            users.insert().values(
                id=101,
                username="receipt-migration",
                hashed_password="unused",
            )
        )
        connection.execute(
            profiles.insert(),
            [
                {
                    "id": 201,
                    "user_id": 101,
                    "name": "Completed",
                    "search_status_state": "done",
                    "search_status_started_at": started_at,
                    "search_status_updated_at": finished_at,
                    "search_status_finished_at": finished_at,
                    "search_status_payload": {
                        "state": "done",
                        "started_at": started_at.isoformat(),
                        "finished_at": finished_at.isoformat(),
                        "jobs_found": 10**100,
                        "jobs_new": 4,
                        "provider_successes": 2,
                        "provider_failures": 1,
                        "current_query": "SECRET-QUERY",
                        "cv_content": "SECRET-CV",
                        "log": ["SECRET-LOG"],
                    },
                },
                {
                    "id": 202,
                    "user_id": 101,
                    "name": "Failed",
                    "search_status_state": "error",
                    "search_status_started_at": started_at,
                    "search_status_updated_at": finished_at,
                    "search_status_finished_at": finished_at,
                    "search_status_payload": {
                        "state": "error",
                        "started_at": started_at.isoformat(),
                        "finished_at": finished_at.isoformat(),
                    },
                },
                {
                    "id": 203,
                    "user_id": 101,
                    "name": "Invalid done",
                    "search_status_state": "done",
                    "search_status_started_at": None,
                    "search_status_updated_at": None,
                    "search_status_finished_at": None,
                    "search_status_payload": {"state": "done"},
                },
            ],
        )

    command.upgrade(config, RECEIPT_REVISION)

    inspector = sa.inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("search_profiles")}
    assert columns["search_run_count"]["nullable"] is False
    assert {
        "last_search_started_at",
        "last_search_completed_at",
        "last_search_state",
        "search_run_count",
        "last_search_summary",
    }.issubset(columns)
    assert "ix_search_profiles_last_search_completed_at" in {
        index["name"] for index in inspector.get_indexes("search_profiles")
    }

    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                """
                SELECT id, last_search_state, search_run_count,
                       last_search_started_at, last_search_completed_at,
                       last_search_summary
                FROM search_profiles
                ORDER BY id
                """
            )
        ).mappings()
        by_id = {row["id"]: row for row in rows}

    completed = by_id[201]
    assert completed["last_search_state"] == "done"
    assert completed["search_run_count"] == 1
    assert completed["last_search_started_at"] is not None
    assert completed["last_search_completed_at"] is not None
    summary = json.loads(completed["last_search_summary"])
    assert summary["counts"]["jobs_found"] == 2_147_483_647
    assert summary["providers"]["status"] == "partial"
    assert "SECRET" not in json.dumps(summary)

    for profile_id in (202, 203):
        assert by_id[profile_id]["last_search_state"] is None
        assert by_id[profile_id]["search_run_count"] == 0
        assert by_id[profile_id]["last_search_summary"] is None

    command.downgrade(config, PREVIOUS_HEAD)
    downgraded_columns = {
        column["name"] for column in sa.inspect(engine).get_columns("search_profiles")
    }
    assert {
        "last_search_started_at",
        "last_search_completed_at",
        "last_search_state",
        "search_run_count",
        "last_search_summary",
    }.isdisjoint(downgraded_columns)

    command.upgrade(config, "head")
    script = ScriptDirectory.from_config(config)
    assert len(script.get_heads()) == 1
    assert script.get_revision(RECEIPT_REVISION) is not None
    engine.dispose()
