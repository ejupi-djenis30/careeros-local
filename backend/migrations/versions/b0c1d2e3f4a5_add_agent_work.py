"""Add agent work requests and proposal models.

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b0c1d2e3f4a5"
down_revision: str | Sequence[str] | None = "a9b0c1d2e3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_work_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("bound_grant_id", sa.String(length=36), nullable=True),
        sa.Column("work_kind", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("target_job_id", sa.Integer(), nullable=True),
        sa.Column("target_application_id", sa.String(length=36), nullable=True),
        sa.Column("target_resume_id", sa.String(length=36), nullable=True),
        sa.Column("preset_id", sa.String(length=64), nullable=True),
        sa.Column("preset_version", sa.Integer(), nullable=True),
        sa.Column("locale", sa.String(length=8), nullable=True),
        sa.Column("selected_fact_ids", sa.JSON(), nullable=True),
        sa.Column("context_snapshot", sa.JSON(), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("input_revisions", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_receipt", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "work_kind IN ('discover', 'analyze', 'materials')",
            name="ck_agent_work_kind",
        ),
        sa.CheckConstraint(
            "state IN ('queued', 'returned', 'accepted', 'rejected', 'canceled', 'expired')",
            name="ck_agent_work_state",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_agent_work_revision"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bound_grant_id"], ["automation_grants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_resume_id"], ["resume_drafts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_work_requests_user_id", "agent_work_requests", ["user_id"])
    op.create_index("ix_agent_work_requests_bound_grant_id", "agent_work_requests", ["bound_grant_id"])
    op.create_index("ix_agent_work_requests_work_kind", "agent_work_requests", ["work_kind"])
    op.create_index("ix_agent_work_requests_state", "agent_work_requests", ["state"])
    op.create_index("ix_agent_work_requests_target_job_id", "agent_work_requests", ["target_job_id"])
    op.create_index("ix_agent_work_requests_target_application_id", "agent_work_requests", ["target_application_id"])
    op.create_index("ix_agent_work_requests_target_resume_id", "agent_work_requests", ["target_resume_id"])
    op.create_index("ix_agent_work_requests_expires_at", "agent_work_requests", ["expires_at"])

    op.create_table(
        "agent_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("submitting_grant_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("payload_digest", sa.String(length=64), nullable=False),
        sa.Column("contract_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("client_label", sa.String(length=120), nullable=False),
        sa.Column("model_label", sa.String(length=120), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("review_required", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("contract_version >= 1", name="ck_agent_proposal_contract_version"),
        sa.ForeignKeyConstraint(["request_id"], ["agent_work_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_proposals_request_id", "agent_proposals", ["request_id"], unique=True)
    op.create_index("ix_agent_proposals_user_id", "agent_proposals", ["user_id"])
    op.create_index("ix_agent_proposals_submitting_grant_id", "agent_proposals", ["submitting_grant_id"])
    op.create_index("ix_agent_proposals_idempotency_key", "agent_proposals", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_agent_proposals_idempotency_key", table_name="agent_proposals")
    op.drop_index("ix_agent_proposals_submitting_grant_id", table_name="agent_proposals")
    op.drop_index("ix_agent_proposals_user_id", table_name="agent_proposals")
    op.drop_index("ix_agent_proposals_request_id", table_name="agent_proposals")
    op.drop_table("agent_proposals")

    op.drop_index("ix_agent_work_requests_expires_at", table_name="agent_work_requests")
    op.drop_index("ix_agent_work_requests_target_resume_id", table_name="agent_work_requests")
    op.drop_index("ix_agent_work_requests_target_application_id", table_name="agent_work_requests")
    op.drop_index("ix_agent_work_requests_target_job_id", table_name="agent_work_requests")
    op.drop_index("ix_agent_work_requests_state", table_name="agent_work_requests")
    op.drop_index("ix_agent_work_requests_work_kind", table_name="agent_work_requests")
    op.drop_index("ix_agent_work_requests_bound_grant_id", table_name="agent_work_requests")
    op.drop_index("ix_agent_work_requests_user_id", table_name="agent_work_requests")
    op.drop_table("agent_work_requests")
