"""add composite index on jobs for user dismissed created_at filter

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-04-01 00:00:00.000000

This revision restores the migration chain expected by older databases and CI
artifacts while keeping the current schema forward-compatible.
"""

from alembic import op

revision = "o5p6q7r8s9t0"
down_revision = "n4o5p6q7r8s9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_jobs_user_dismissed_created_at",
        "jobs",
        ["user_id", "dismissed", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_user_dismissed_created_at", table_name="jobs")
