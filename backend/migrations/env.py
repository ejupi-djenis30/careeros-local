"""
Alembic environment configuration.

Reads DATABASE_URL from environment and uses the application's
SQLAlchemy Base metadata for auto-generating migrations.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

# Keep direct `alembic` development commands importable from outside the checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv

load_dotenv()
load_dotenv("backend/.env")

from backend import model_registry  # noqa: E402, F401
from backend.db.sqlite import (  # noqa: E402
    ensure_sqlite_database_parent,
    sqlite_database_path,
    validate_sqlite_database_location,
)
from backend.migrations.runtime import (  # noqa: E402
    configure_migration_connection,
    database_url_from_config,
    migration_lock,
    sqlite_busy_timeout_ms,
    validate_sqlite_integrity,
)
from backend.models.base_model import Base  # noqa: E402

config = context.config
database_url = database_url_from_config(config)

if config.config_file_name is not None:
    # Alembic runs in-process in tests and operational tooling. Disabling
    # application loggers here silently breaks observability after a migration.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _refuse_unsafe_production_command() -> None:
    """Production vaults advance through upgrades; rollback uses verified backups."""

    migration_function = context.get_context().opts.get("fn")
    command_name = getattr(migration_function, "__name__", "")
    if os.environ.get("ENVIRONMENT", "development").strip().lower() == "production" and (
        command_name in {"downgrade", "do_stamp"}
    ):
        raise RuntimeError(
            "Production schema downgrades/stamps are disabled; restore a verified backup instead"
        )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    _refuse_unsafe_production_command()
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connect to DB and apply."""
    timeout_ms = sqlite_busy_timeout_ms()
    # Programmatic callers (desktop recovery and isolated tests) provide an
    # authoritative database URL that may intentionally differ from process
    # settings. Their caller already hardened the data-root chain, so Alembic
    # repeats the immediate-parent/file reservation only. Direct CLI startup
    # has no attributed URL and can safely apply its explicit DATA_DIR chain.
    attributed_database_url = config.attributes.get("database_url")
    configured_data_root = (
        os.environ.get("DATA_DIR", "").strip() if attributed_database_url is None else ""
    )
    data_root = Path(configured_data_root) if configured_data_root else None
    database_path = (
        validate_sqlite_database_location(database_url, data_root=data_root)
        if data_root is not None
        else sqlite_database_path(database_url)
    )
    with migration_lock(database_path):
        database_path = ensure_sqlite_database_parent(
            database_url,
            data_root=data_root,
        )
        connectable = create_engine(
            database_url,
            poolclass=NullPool,
            connect_args={"timeout": timeout_ms / 1000},
        )
        try:
            with connectable.connect() as connection:
                configure_migration_connection(connection, busy_timeout_ms=timeout_ms)
                # SQLAlchemy autobegins for PRAGMA statements even though the
                # sqlite3 driver has not started DML. End that wrapper so
                # Alembic owns and commits its version-table transaction.
                connection.commit()
                context.configure(
                    connection=connection,
                    target_metadata=target_metadata,
                )
                _refuse_unsafe_production_command()
                with context.begin_transaction():
                    context.run_migrations()
                validate_sqlite_integrity(connection)
        finally:
            connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
