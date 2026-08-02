from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.core.config import settings
from backend.db.base import configure_sqlite_connection, ensure_sqlite_parent

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PREVIOUS_HEAD = "e7f8a9b0c1d2"
AUTH_SESSION_REVISION = "f8a9b0c1d2e3"
VAULT_LIFECYCLE_REVISION = "a9b0c1d2e3f4"
CURRENT_HEAD = "b0c1d2e3f4a5"


def _alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_auth_session_migration_is_empty_bounded_and_round_trips(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "auth-session-migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    config = _alembic_config(database_url)
    ensure_sqlite_parent(database_url)
    engine = sa.create_engine(database_url)
    sa.event.listen(engine, "connect", configure_sqlite_connection)

    try:
        command.upgrade(config, PREVIOUS_HEAD)
        assert "auth_sessions" not in sa.inspect(engine).get_table_names()

        command.upgrade(config, AUTH_SESSION_REVISION)
        inspector = sa.inspect(engine)
        assert "auth_sessions" in inspector.get_table_names()
        assert {column["name"] for column in inspector.get_columns("auth_sessions")} == {
            "id",
            "user_id",
            "slot",
            "refresh_jti_digest",
            "expires_at",
            "revoked_at",
            "created_at",
            "updated_at",
        }
        assert inspector.get_pk_constraint("auth_sessions")["constrained_columns"] == ["id"]
        assert any(
            constraint["name"] == "uq_auth_session_user_slot"
            and constraint["column_names"] == ["user_id", "slot"]
            for constraint in inspector.get_unique_constraints("auth_sessions")
        )
        assert any(
            foreign_key["constrained_columns"] == ["user_id"]
            and foreign_key["referred_table"] == "users"
            and foreign_key["options"].get("ondelete") == "CASCADE"
            for foreign_key in inspector.get_foreign_keys("auth_sessions")
        )
        assert any(
            index["name"] == "ix_auth_sessions_refresh_jti_digest" and index["unique"]
            for index in inspector.get_indexes("auth_sessions")
        )

        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO users (id, username, hashed_password) "
                    "VALUES (9001, 'auth-migration', 'unused')"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO auth_sessions "
                    "(id, user_id, slot, refresh_jti_digest, expires_at) "
                    "VALUES (:id, 9001, 0, :digest, '2030-01-01 00:00:00')"
                ),
                {"id": "a" * 32, "digest": "b" * 64},
            )
        with engine.begin() as connection:
            connection.execute(sa.text("DELETE FROM users WHERE id = 9001"))
        with engine.connect() as connection:
            assert connection.scalar(sa.text("SELECT count(*) FROM auth_sessions")) == 0

        command.downgrade(config, PREVIOUS_HEAD)
        assert "auth_sessions" not in sa.inspect(engine).get_table_names()
        assert "users" in sa.inspect(engine).get_table_names()
        command.upgrade(config, "head")
        assert "auth_sessions" in sa.inspect(engine).get_table_names()
        assert ScriptDirectory.from_config(config).get_heads() == [CURRENT_HEAD]
    finally:
        engine.dispose()


def test_vault_lifecycle_state_migration_is_durable_and_round_trips(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "vault-lifecycle-migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    config = _alembic_config(database_url)
    ensure_sqlite_parent(database_url)
    engine = sa.create_engine(database_url)
    sa.event.listen(engine, "connect", configure_sqlite_connection)

    try:
        command.upgrade(config, AUTH_SESSION_REVISION)
        assert "vault_lifecycle_state" not in {
            column["name"] for column in sa.inspect(engine).get_columns("users")
        }

        command.upgrade(config, VAULT_LIFECYCLE_REVISION)
        inspector = sa.inspect(engine)
        columns = {column["name"]: column for column in inspector.get_columns("users")}
        assert columns["vault_lifecycle_state"]["nullable"] is False
        assert columns["vault_maintenance_fingerprint"]["nullable"] is True
        assert "ready" in str(columns["vault_lifecycle_state"]["default"])
        check_names = {
            constraint["name"] for constraint in inspector.get_check_constraints("users")
        }
        assert {
            "ck_user_vault_lifecycle_state",
            "ck_user_vault_maintenance_fingerprint",
            "ck_user_vault_maintenance_fingerprint_shape",
        }.issubset(check_names)
        assert any(
            index["name"] == "ix_users_vault_lifecycle_state"
            for index in inspector.get_indexes("users")
        )
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO users (id, username, hashed_password) "
                    "VALUES (9002, 'lifecycle-migration', 'unused')"
                )
            )
            assert (
                connection.scalar(
                    sa.text("SELECT vault_lifecycle_state FROM users WHERE id = 9002")
                )
                == "ready"
            )

        for pending_state, fingerprint in (
            ("reset_pending", None),
            ("restore_pending", "a" * 64),
            ("erasure_pending", None),
        ):
            with engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "UPDATE users SET vault_lifecycle_state = :state, "
                        "vault_maintenance_fingerprint = :fingerprint WHERE id = 9002"
                    ),
                    {"state": pending_state, "fingerprint": fingerprint},
                )
            with pytest.raises(RuntimeError, match="maintenance is pending"):
                command.downgrade(config, AUTH_SESSION_REVISION)
            with engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "UPDATE users SET vault_lifecycle_state = 'ready', "
                        "vault_maintenance_fingerprint = NULL WHERE id = 9002"
                    )
                )

        for invalid_fingerprint in ("a" * 63, "A" * 64, "z" * 64):
            with pytest.raises(sa.exc.IntegrityError):
                with engine.begin() as connection:
                    connection.execute(
                        sa.text(
                            "UPDATE users SET vault_lifecycle_state = 'restore_pending', "
                            "vault_maintenance_fingerprint = :fingerprint WHERE id = 9002"
                        ),
                        {"fingerprint": invalid_fingerprint},
                    )

        command.downgrade(config, AUTH_SESSION_REVISION)
        assert "vault_lifecycle_state" not in {
            column["name"] for column in sa.inspect(engine).get_columns("users")
        }
        assert "vault_maintenance_fingerprint" not in {
            column["name"] for column in sa.inspect(engine).get_columns("users")
        }
        command.upgrade(config, "head")
        assert "vault_lifecycle_state" in {
            column["name"] for column in sa.inspect(engine).get_columns("users")
        }
    finally:
        engine.dispose()
