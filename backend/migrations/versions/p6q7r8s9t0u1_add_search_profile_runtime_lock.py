"""Add runtime search lock columns to search profiles

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-04-01 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "p6q7r8s9t0u1"
down_revision = "o5p6q7r8s9t0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("search_profiles", sa.Column("search_lock_token", sa.String(), nullable=True))
    op.add_column("search_profiles", sa.Column("search_lock_state", sa.String(), nullable=True))
    op.add_column(
        "search_profiles",
        sa.Column("search_lock_acquired_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("search_profiles", "search_lock_acquired_at")
    op.drop_column("search_profiles", "search_lock_state")
    op.drop_column("search_profiles", "search_lock_token")
