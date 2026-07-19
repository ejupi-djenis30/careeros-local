import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.config import settings
from backend.models.base_model import Base as Base


def ensure_sqlite_parent(database_url: str) -> None:
    """Create the parent for a file-backed SQLite vault before opening it."""
    url = make_url(database_url)
    database = url.database
    if url.get_backend_name() != "sqlite" or not database or database == ":memory:":
        return
    # SQLite URI filenames have their own parsing rules and should be prepared by
    # the caller that opted into them. The normal local-vault URL is a filesystem path.
    if database.startswith("file:"):
        return
    Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    """Apply durability and integrity settings to every SQLite connection."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA secure_delete=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={int(settings.SQLITE_BUSY_TIMEOUT_MS)}")
    finally:
        cursor.close()

# Configure connection pooling appropriately based on the database type
if os.environ.get("TESTING") == "1":
    # Use a shared in-memory database for testing to ensure background tasks
    # and the main thread see the same data.
    SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
elif "sqlite" in settings.DATABASE_URL:
    ensure_sqlite_parent(settings.DATABASE_URL)
    engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=1800,
    )

if "sqlite" in str(engine.url):
    event.listen(engine, "connect", configure_sqlite_connection)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
