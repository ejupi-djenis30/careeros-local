from datetime import datetime

from sqlalchemy import Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

from backend.db.types import UTCDateTime


class Base(DeclarativeBase):
    """Typed SQLAlchemy 2 declarative base shared by every persistence model."""


class TimestampMixin:
    """Mixin to add created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BaseModel(Base):
    """Base class for all models with an integer ID."""

    __abstract__ = True
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
