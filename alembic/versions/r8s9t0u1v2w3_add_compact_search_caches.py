"""Add compact search cache columns

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2026-04-03 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "r8s9t0u1v2w3"
down_revision = "q7r8s9t0u1v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("search_profiles", sa.Column("cached_profile_snapshot", sa.Text(), nullable=True))
    op.add_column(
        "search_profiles",
        sa.Column("cached_profile_snapshot_fingerprint", sa.String(), nullable=True),
    )
    op.add_column("scraped_jobs", sa.Column("content_fingerprint", sa.String(), nullable=True))
    op.add_column("scraped_jobs", sa.Column("compact_description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scraped_jobs", "compact_description")
    op.drop_column("scraped_jobs", "content_fingerprint")
    op.drop_column("search_profiles", "cached_profile_snapshot_fingerprint")
    op.drop_column("search_profiles", "cached_profile_snapshot")
