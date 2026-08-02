from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from backend.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[4]
PREVIOUS_HEAD = "a9b0c1d2e3f4"
CURRENT_HEAD = "b0c1d2e3f4a5"


def _alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_provider_installation_migration_supports_native_and_declarative_shapes(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "provider-installations.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)
    config = _alembic_config(database_url)
    engine = sa.create_engine(database_url)

    command.upgrade(config, PREVIOUS_HEAD)
    assert "job_provider_configurations" not in sa.inspect(engine).get_table_names()

    command.upgrade(config, CURRENT_HEAD)
    columns = {
        column["name"] for column in sa.inspect(engine).get_columns("job_provider_configurations")
    }
    assert {
        "native_adapter_id",
        "source_pack_id",
        "source_pack_version",
        "request_config",
        "extraction_config",
    }.issubset(columns)

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users (id, username, hashed_password) "
                "VALUES (901, 'provider-migration-owner', 'unused')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO job_provider_configurations "
                "(id, user_id, key, display_name, description, adapter_kind, "
                "native_adapter_id, source_pack_id, source_pack_version, enabled, revision, "
                "request_config, extraction_config, capabilities_config) VALUES "
                "('00000000-0000-4000-8000-000000000901', 901, 'job_room', 'Job-Room', '', "
                "'native', 'job_room', 'careeros.switzerland.core', '1.0.0', 0, 1, "
                "NULL, NULL, '{\"accepted_domains\":[\"*\"],\"supported_languages\":[\"en\"]}')"
            )
        )

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO job_provider_configurations "
                    "(id, user_id, key, display_name, description, adapter_kind, "
                    "native_adapter_id, enabled, revision, request_config, extraction_config, "
                    "capabilities_config) VALUES "
                    "('00000000-0000-4000-8000-000000000902', 901, 'invalid_native', "
                    "'Invalid', '', 'native', 'job_room', 0, 1, '{}', NULL, '{}')"
                )
            )

    command.downgrade(config, PREVIOUS_HEAD)
    assert "job_provider_configurations" not in sa.inspect(engine).get_table_names()
    engine.dispose()
