"""add composite index on jobs for user dismissed created_at filter

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2025-01-01 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "o5p6q7r8s9t0"
down_revision = "n4o5p6q7r8s9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_job_user_dismissed_created",
        "jobs",
        ["user_id", "dismissed", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_job_user_dismissed_created", table_name="jobs")
