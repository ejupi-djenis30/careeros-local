from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.core.config import settings
from backend.db.base import configure_sqlite_connection, ensure_sqlite_parent

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PREVIOUS_HEAD = "a9b0c1d2e3f4"
AGENT_WORK_REVISION = "b0c1d2e3f4a5"


def _alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["database_url"] = database_url
    return config


def test_agent_work_migration_round_trips_and_preserves_data(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "agent-work-migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    config = _alembic_config(database_url)
    ensure_sqlite_parent(database_url)
    engine = sa.create_engine(database_url)
    sa.event.listen(engine, "connect", configure_sqlite_connection)

    try:
        # 1. Upgrade to previous head
        command.upgrade(config, PREVIOUS_HEAD)
        inspector = sa.inspect(engine)
        assert "agent_work_requests" not in inspector.get_table_names()
        assert "agent_proposals" not in inspector.get_table_names()

        # Insert seed data under PREVIOUS_HEAD: user and grant
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, username, hashed_password) "
                    "VALUES (1001, 'migrated_user', 'hash123')"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO automation_grants (id, user_id, label, token_digest, scopes, expires_at) "
                    "VALUES ('grant-1001', 1001, 'Test Grant', 'digest1001', :scopes, '2030-01-01 00:00:00')"
                ),
                {"scopes": json.dumps(["system:read", "career:read"])},
            )

        # 2. Upgrade to new agent_work revision
        command.upgrade(config, AGENT_WORK_REVISION)
        inspector = sa.inspect(engine)
        assert "agent_work_requests" in inspector.get_table_names()
        assert "agent_proposals" in inspector.get_table_names()

        req_columns = {col["name"] for col in inspector.get_columns("agent_work_requests")}
        assert {
            "id",
            "user_id",
            "bound_grant_id",
            "work_kind",
            "state",
            "revision",
            "instruction",
            "context_snapshot",
            "input_digest",
            "input_revisions",
            "expires_at",
            "created_at",
            "updated_at",
        }.issubset(req_columns)

        prop_columns = {col["name"] for col in inspector.get_columns("agent_proposals")}
        assert {
            "id",
            "request_id",
            "user_id",
            "submitting_grant_id",
            "idempotency_key",
            "payload_digest",
            "contract_version",
            "client_label",
            "payload",
            "review_required",
            "created_at",
        }.issubset(prop_columns)

        # Verify old user and grant are intact
        with engine.connect() as conn:
            user_count = conn.scalar(sa.text("SELECT count(*) FROM users WHERE id = 1001"))
            assert user_count == 1
            grant_label = conn.scalar(
                sa.text("SELECT label FROM automation_grants WHERE id = 'grant-1001'")
            )
            assert grant_label == "Test Grant"

        # Insert work request and proposal
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO agent_work_requests "
                    "(id, user_id, bound_grant_id, work_kind, state, revision, instruction, "
                    "context_snapshot, input_digest, input_revisions, expires_at) "
                    "VALUES ('req-1', 1001, 'grant-1001', 'discover', 'queued', 1, 'Find jobs', "
                    ":context, 'hash-digest', :revisions, '2030-01-01 00:00:00')"
                ),
                {"context": json.dumps({"facts": []}), "revisions": json.dumps({"profile": 1})},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO agent_proposals "
                    "(id, request_id, user_id, submitting_grant_id, idempotency_key, payload_digest, "
                    "client_label, payload) "
                    "VALUES ('prop-1', 'req-1', 1001, 'grant-1001', 'idem-1', 'p-digest', 'client-a', :payload)"
                ),
                {"payload": json.dumps({"kind": "discover", "listings": []})},
            )

        # Test grant deletion ondelete="SET NULL"
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM automation_grants WHERE id = 'grant-1001'"))
        with engine.connect() as conn:
            bound_id = conn.scalar(
                sa.text("SELECT bound_grant_id FROM agent_work_requests WHERE id = 'req-1'")
            )
            assert bound_id is None
            req_exists = conn.scalar(
                sa.text("SELECT count(*) FROM agent_work_requests WHERE id = 'req-1'")
            )
            assert req_exists == 1
            prop_exists = conn.scalar(
                sa.text("SELECT count(*) FROM agent_proposals WHERE id = 'prop-1'")
            )
            assert prop_exists == 1

        # 3. Downgrade to PREVIOUS_HEAD
        command.downgrade(config, PREVIOUS_HEAD)
        inspector = sa.inspect(engine)
        assert "agent_work_requests" not in inspector.get_table_names()
        assert "agent_proposals" not in inspector.get_table_names()
        assert "users" in inspector.get_table_names()

        # 4. Re-upgrade to AGENT_WORK_REVISION
        command.upgrade(config, AGENT_WORK_REVISION)
        inspector = sa.inspect(engine)
        assert "agent_work_requests" in inspector.get_table_names()
        assert "agent_proposals" in inspector.get_table_names()

        rev = ScriptDirectory.from_config(config).get_revision(AGENT_WORK_REVISION)
        assert rev is not None
        assert rev.down_revision == PREVIOUS_HEAD
    finally:
        engine.dispose()
