from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.core.config import settings

# Configure connection pooling appropriately based on the database type
if "sqlite" in settings.DATABASE_URL:
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_size=getattr(settings, "DB_POOL_SIZE", 5),
        max_overflow=getattr(settings, "DB_MAX_OVERFLOW", 10),
        pool_pre_ping=True,
        pool_recycle=1800,
    )
from backend.models.base_model import Base

SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
