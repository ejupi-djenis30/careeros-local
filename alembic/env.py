"""
Alembic environment configuration.

Reads DATABASE_URL from environment and uses the application's
SQLAlchemy Base metadata for auto-generating migrations.
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Add project root to path so we can import backend modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()
load_dotenv("backend/.env")

from backend.core.config import settings  # noqa: E402
from backend.db.base import Base  # noqa: E402

DATABASE_URL = (
    settings.DATABASE_URL.replace("sqlite:///", "postgresql+psycopg2://")
    if "postgres" in settings.DATABASE_URL
    else settings.DATABASE_URL
)
# Make sure we use psycopg2 driver for postgres in alembic context if needed, though usually handled by connection string
# Actually, let's just use settings.DATABASE_URL directly, assuming correct driver is installed or string format is correct.
DATABASE_URL = settings.DATABASE_URL

from backend import models  # noqa: E402, F401

config = context.config

# Override sqlalchemy.url from env
config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connect to DB and apply."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
