"""Add durable workflow runs with leases and checkpoints.

Revision ID: x4y5z6a7b8c9
Revises: w3x4y5z6a7b8
Create Date: 2026-07-17
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "x4y5z6a7b8c9"
down_revision: Union[str, None] = "w3x4y5z6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workflow_type", sa.String(length=60), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("result_reference", sa.JSON(), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "workflow_type", "idempotency_key", name="uq_workflow_idempotency"
        ),
    )
    op.create_index("ix_workflow_runs_user_id", "workflow_runs", ["user_id"])
    op.create_index("ix_workflow_runs_workflow_type", "workflow_runs", ["workflow_type"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("ix_workflow_runs_lease_owner", "workflow_runs", ["lease_owner"])
    op.create_index("ix_workflow_runs_lease_expires_at", "workflow_runs", ["lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_lease_expires_at", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_lease_owner", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workflow_type", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_user_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
