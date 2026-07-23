"""Add content-free local AI execution and evaluation audit tables.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("task", sa.String(length=40), nullable=False),
        sa.Column("contract_version", sa.String(length=20), nullable=False),
        sa.Column("model_id", sa.String(length=240), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("output_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("repair_count", sa.Integer(), nullable=False),
        sa.Column("validation_codes", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_executions_user_id", "ai_executions", ["user_id"])
    op.create_index("ix_ai_executions_task", "ai_executions", ["task"])
    op.create_index("ix_ai_executions_model_id", "ai_executions", ["model_id"])
    op.create_index("ix_ai_executions_created_at", "ai_executions", ["created_at"])
    op.create_index(
        "ix_ai_executions_task_created_at", "ai_executions", ["task", "created_at"]
    )
    op.create_index(
        "ix_ai_executions_model_created_at", "ai_executions", ["model_id", "created_at"]
    )

    op.create_table(
        "ai_evaluation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_version", sa.String(length=30), nullable=False),
        sa.Column("application_version", sa.String(length=30), nullable=False),
        sa.Column("model_id", sa.String(length=240), nullable=False),
        sa.Column("runtime_version", sa.String(length=80), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("peak_memory_bytes", sa.Integer(), nullable=True),
        sa.Column("result_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_evaluation_runs_dataset_version", "ai_evaluation_runs", ["dataset_version"]
    )
    op.create_index("ix_ai_evaluation_runs_model_id", "ai_evaluation_runs", ["model_id"])
    op.create_index("ix_ai_evaluation_runs_created_at", "ai_evaluation_runs", ["created_at"])
    op.create_index(
        "ix_ai_evaluation_dataset_model",
        "ai_evaluation_runs",
        ["dataset_version", "model_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_evaluation_dataset_model", table_name="ai_evaluation_runs")
    op.drop_index("ix_ai_evaluation_runs_created_at", table_name="ai_evaluation_runs")
    op.drop_index("ix_ai_evaluation_runs_model_id", table_name="ai_evaluation_runs")
    op.drop_index("ix_ai_evaluation_runs_dataset_version", table_name="ai_evaluation_runs")
    op.drop_table("ai_evaluation_runs")

    op.drop_index("ix_ai_executions_model_created_at", table_name="ai_executions")
    op.drop_index("ix_ai_executions_task_created_at", table_name="ai_executions")
    op.drop_index("ix_ai_executions_created_at", table_name="ai_executions")
    op.drop_index("ix_ai_executions_model_id", table_name="ai_executions")
    op.drop_index("ix_ai_executions_task", table_name="ai_executions")
    op.drop_index("ix_ai_executions_user_id", table_name="ai_executions")
    op.drop_table("ai_executions")
