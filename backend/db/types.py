"""Database types with stable cross-dialect semantics."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator


def aware_utc(value: datetime | None) -> datetime | None:
    """Return an aware UTC datetime, treating legacy SQLite values as UTC."""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """Persist UTC and always return an aware datetime.

    SQLite discards timezone offsets for its native ``DATETIME`` adapter.  The
    decorator stores a naive UTC wall time for dialect compatibility and restores
    the UTC marker on read.  Other dialects get the same unambiguous contract.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: datetime | None, dialect: Dialect):
        normalized = aware_utc(value)
        if normalized is None:
            return None
        if dialect.name == "sqlite":
            return normalized.replace(tzinfo=None)
        return normalized

    def process_result_value(self, value: datetime | None, _dialect: Dialect):
        return aware_utc(value)
