"""Add DB-backed search status columns to search profiles

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-04-02 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "q7r8s9t0u1v2"
down_revision = "p6q7r8s9t0u1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("search_profiles", sa.Column("search_status_state", sa.String(), nullable=True))
    op.add_column("search_profiles", sa.Column("search_status_payload", sa.JSON(), nullable=True))
    op.add_column(
        "search_profiles",
        sa.Column("search_status_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "search_profiles",
        sa.Column("search_status_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "search_profiles",
        sa.Column("search_status_finished_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("search_profiles", "search_status_finished_at")
    op.drop_column("search_profiles", "search_status_updated_at")
    op.drop_column("search_profiles", "search_status_started_at")
    op.drop_column("search_profiles", "search_status_payload")
    op.drop_column("search_profiles", "search_status_state")
