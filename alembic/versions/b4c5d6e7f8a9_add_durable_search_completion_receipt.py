"""Add durable privacy-safe search completion receipts.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MAX_COUNTER = 2_147_483_647
_MAX_DURATION_MS = 31 * 24 * 60 * 60 * 1000
_COUNTER_KEYS = (
    "total_searches",
    "searches_completed",
    "jobs_found",
    "jobs_new",
    "jobs_unique",
    "jobs_duplicates",
    "jobs_duplicates_runtime",
    "jobs_duplicates_history",
    "jobs_duplicates_catalog_conflicts",
    "jobs_skipped",
    "jobs_analyzed",
    "jobs_analyze_total",
    "errors",
    "plan_unique_count",
)


def _coerce_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str):
        text = value.strip()
        if not text or len(text) > 64:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            timestamp = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _counter(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return min(_MAX_COUNTER, max(0, number))


def _provider_status(successful: int, failed: int) -> str:
    if successful and failed:
        return "partial"
    if successful:
        return "succeeded"
    if failed:
        return "failed"
    return "not_contacted"


def _summary(
    payload: Mapping[str, Any],
    *,
    started_at: datetime,
    finished_at: datetime,
) -> dict[str, Any]:
    successful = _counter(payload.get("provider_successes"))
    failed = _counter(payload.get("provider_failures"))
    return {
        "schema_version": 1,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_ms": min(
            _MAX_DURATION_MS,
            max(0, int((finished_at - started_at).total_seconds() * 1000)),
        ),
        "counts": {key: _counter(payload.get(key)) for key in _COUNTER_KEYS},
        "providers": {
            "status": _provider_status(successful, failed),
            "successful_requests": successful,
            "failed_requests": failed,
            "queries_without_provider": _counter(payload.get("queries_without_provider")),
        },
    }


def upgrade() -> None:
    with op.batch_alter_table("search_profiles") as batch_op:
        batch_op.add_column(sa.Column("last_search_started_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("last_search_completed_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("last_search_state", sa.String()))
        batch_op.add_column(sa.Column("search_run_count", sa.Integer()))
        batch_op.add_column(sa.Column("last_search_summary", sa.JSON()))

    search_profiles = sa.table(
        "search_profiles",
        sa.column("id", sa.Integer()),
        sa.column("search_status_state", sa.String()),
        sa.column("search_status_payload", sa.JSON()),
        sa.column("search_status_started_at", sa.DateTime(timezone=True)),
        sa.column("search_status_updated_at", sa.DateTime(timezone=True)),
        sa.column("search_status_finished_at", sa.DateTime(timezone=True)),
        sa.column("last_search_started_at", sa.DateTime(timezone=True)),
        sa.column("last_search_completed_at", sa.DateTime(timezone=True)),
        sa.column("last_search_state", sa.String()),
        sa.column("search_run_count", sa.Integer()),
        sa.column("last_search_summary", sa.JSON()),
    )
    connection = op.get_bind()
    connection.execute(search_profiles.update().values(search_run_count=0))
    completed_rows = connection.execute(
        sa.select(
            search_profiles.c.id,
            search_profiles.c.search_status_payload,
            search_profiles.c.search_status_started_at,
            search_profiles.c.search_status_updated_at,
            search_profiles.c.search_status_finished_at,
        ).where(search_profiles.c.search_status_state == "done")
    ).mappings()
    for row in completed_rows:
        payload = row["search_status_payload"]
        safe_payload = payload if isinstance(payload, Mapping) else {}
        started_at = _coerce_timestamp(
            row["search_status_started_at"] or safe_payload.get("started_at")
        )
        finished_at = _coerce_timestamp(
            row["search_status_finished_at"]
            or safe_payload.get("finished_at")
            or row["search_status_updated_at"]
        )
        if started_at is None or finished_at is None or finished_at < started_at:
            continue
        connection.execute(
            search_profiles.update()
            .where(search_profiles.c.id == row["id"])
            .values(
                last_search_started_at=started_at,
                last_search_completed_at=finished_at,
                last_search_state="done",
                search_run_count=1,
                last_search_summary=_summary(
                    safe_payload,
                    started_at=started_at,
                    finished_at=finished_at,
                ),
            )
        )

    with op.batch_alter_table("search_profiles") as batch_op:
        batch_op.alter_column(
            "search_run_count",
            existing_type=sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        )
        batch_op.create_index(
            "ix_search_profiles_last_search_completed_at",
            ["last_search_completed_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("search_profiles") as batch_op:
        batch_op.drop_index("ix_search_profiles_last_search_completed_at")
        batch_op.drop_column("last_search_summary")
        batch_op.drop_column("search_run_count")
        batch_op.drop_column("last_search_state")
        batch_op.drop_column("last_search_completed_at")
        batch_op.drop_column("last_search_started_at")
