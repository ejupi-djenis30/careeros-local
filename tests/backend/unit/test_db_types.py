from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import dialect as postgresql_dialect
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect

from backend.db.types import UTCDateTime, aware_utc


def test_utc_datetime_uses_naive_utc_only_for_sqlite():
    value = datetime(2026, 8, 1, 9, 0, tzinfo=timezone(timedelta(hours=2)))
    field = UTCDateTime()

    sqlite_value = field.process_bind_param(value, sqlite_dialect())
    postgres_value = field.process_bind_param(value, postgresql_dialect())

    assert sqlite_value == datetime(2026, 8, 1, 7, 0)
    assert sqlite_value.tzinfo is None
    assert postgres_value == datetime(2026, 8, 1, 7, 0, tzinfo=timezone.utc)
    assert postgres_value.tzinfo is timezone.utc


def test_utc_datetime_restores_legacy_naive_values_as_aware_utc():
    legacy = datetime(2026, 8, 1, 7, 0)

    assert aware_utc(legacy) == datetime(2026, 8, 1, 7, 0, tzinfo=timezone.utc)
    assert UTCDateTime().process_result_value(legacy, sqlite_dialect()).tzinfo is timezone.utc
