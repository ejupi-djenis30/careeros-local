"""Drop summary column from scraped_jobs table

The summary column was used by the removed SUMMARY LLM step (opt-in job
description digest).  The step has been removed; the column is unused.

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-03-26 00:00:00.000000

"""

from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("scraped_jobs") as batch_op:
            batch_op.drop_column("summary")
    else:
        op.drop_column("scraped_jobs", "summary")


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("scraped_jobs") as batch_op:
            batch_op.add_column(sa.Column("summary", sa.Text(), nullable=True))
    else:
        op.add_column("scraped_jobs", sa.Column("summary", sa.Text(), nullable=True))
