from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_ai_audit_migration_upgrades_and_downgrades_cleanly(monkeypatch) -> None:
    revision_path = (
        Path(__file__).resolve().parents[3]
        / "alembic"
        / "versions"
        / "b8c9d0e1f2a3_add_local_ai_audit.py"
    )
    spec = importlib.util.spec_from_file_location("careeros_ai_audit_revision", revision_path)
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE users (id INTEGER NOT NULL PRIMARY KEY, username VARCHAR NOT NULL)"
            )
        )
        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(revision, "op", operations)

        revision.upgrade()
        inspector = sa.inspect(connection)
        assert {"ai_executions", "ai_evaluation_runs"} <= set(inspector.get_table_names())
        execution_columns = {item["name"] for item in inspector.get_columns("ai_executions")}
        assert {
            "input_fingerprint",
            "output_fingerprint",
            "validation_codes",
            "repair_count",
        } <= execution_columns
        foreign_keys = inspector.get_foreign_keys("ai_executions")
        assert foreign_keys[0]["referred_table"] == "users"
        assert foreign_keys[0]["options"].get("ondelete") == "CASCADE"

        revision.downgrade()
        assert "ai_executions" not in sa.inspect(connection).get_table_names()
        assert "ai_evaluation_runs" not in sa.inspect(connection).get_table_names()
