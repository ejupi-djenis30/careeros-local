"""drop jobs.is_scraped column (dead code)

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-03-28 00:00:00.000000

The ``is_scraped`` column on the ``jobs`` table was never set or read by
any production code path — all jobs originate from scraping.  Removing it
reduces dead columns and schema noise.
"""

import sqlalchemy as sa

from alembic import op

revision = "l2m3n4o5p6q7"
down_revision = "k1l2m3n4o5p6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("is_scraped")


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_scraped", sa.Boolean(), nullable=True, server_default=sa.false())
        )
