"""Add revocable, scoped automation grants.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automation_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_grants_user_id", "automation_grants", ["user_id"])
    op.create_index("ix_automation_grants_expires_at", "automation_grants", ["expires_at"])
    op.create_index("ix_automation_grants_revoked_at", "automation_grants", ["revoked_at"])
    op.create_index(
        "ix_automation_grants_token_digest",
        "automation_grants",
        ["token_digest"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_automation_grants_token_digest", table_name="automation_grants")
    op.drop_index("ix_automation_grants_revoked_at", table_name="automation_grants")
    op.drop_index("ix_automation_grants_expires_at", table_name="automation_grants")
    op.drop_index("ix_automation_grants_user_id", table_name="automation_grants")
    op.drop_table("automation_grants")
