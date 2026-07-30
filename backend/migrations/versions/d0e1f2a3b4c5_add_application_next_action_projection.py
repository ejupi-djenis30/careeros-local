"""Add a queryable next-action projection to applications.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-22
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("applications") as batch_op:
        batch_op.add_column(sa.Column("job_title", sa.String(length=240)))
        batch_op.add_column(sa.Column("job_company", sa.String(length=240)))
        batch_op.add_column(sa.Column("job_location", sa.String(length=500)))
        batch_op.add_column(sa.Column("latest_event_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("next_action_task_id", sa.String(length=36)))
        batch_op.add_column(sa.Column("next_action_title", sa.String(length=500)))
        batch_op.add_column(sa.Column("next_action_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("next_action_priority", sa.String(length=20)))
        batch_op.create_index(
            "ix_applications_user_stage_next_action",
            ["user_id", "current_stage", "next_action_at"],
            unique=False,
        )

    applications = sa.table(
        "applications",
        sa.column("id", sa.String(length=36)),
        sa.column("job_snapshot", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("job_title", sa.String(length=240)),
        sa.column("job_company", sa.String(length=240)),
        sa.column("job_location", sa.String(length=500)),
        sa.column("latest_event_at", sa.DateTime(timezone=True)),
    )
    events = sa.table(
        "application_events",
        sa.column("application_id", sa.String(length=36)),
        sa.column("occurred_at", sa.DateTime(timezone=True)),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            applications.c.id,
            applications.c.job_snapshot,
            applications.c.created_at,
        )
    ).mappings()
    for row in rows:
        snapshot = row["job_snapshot"]
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except json.JSONDecodeError:
                snapshot = {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        latest_event_at = connection.execute(
            sa.select(sa.func.max(events.c.occurred_at)).where(
                events.c.application_id == row["id"]
            )
        ).scalar_one_or_none()
        connection.execute(
            applications.update()
            .where(applications.c.id == row["id"])
            .values(
                job_title=str(snapshot.get("title") or "Untitled role")[:240],
                job_company=str(snapshot.get("company") or "Unknown company")[:240],
                job_location=(
                    str(snapshot["location"])[:500]
                    if snapshot.get("location") is not None
                    else None
                ),
                latest_event_at=latest_event_at or row["created_at"],
            )
        )

    with op.batch_alter_table("applications") as batch_op:
        batch_op.alter_column("job_title", existing_type=sa.String(length=240), nullable=False)
        batch_op.alter_column(
            "job_company", existing_type=sa.String(length=240), nullable=False
        )
        batch_op.alter_column(
            "latest_event_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_index("ix_applications_user_stage_next_action")
        batch_op.drop_column("next_action_priority")
        batch_op.drop_column("next_action_at")
        batch_op.drop_column("next_action_title")
        batch_op.drop_column("next_action_task_id")
        batch_op.drop_column("latest_event_at")
        batch_op.drop_column("job_location")
        batch_op.drop_column("job_company")
        batch_op.drop_column("job_title")
