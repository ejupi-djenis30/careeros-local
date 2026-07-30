"""Restore the database-managed updated timestamp for jobs.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
"""

from collections.abc import Sequence
from typing import Literal, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _recreate_policy() -> Literal["auto", "always"]:
    """SQLite needs a table rebuild to change a column default."""
    return "always" if op.get_bind().dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    with op.batch_alter_table("jobs", recreate=_recreate_policy()) as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            existing_server_default=None,
            server_default=sa.func.now(),
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs", recreate=_recreate_policy()) as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            existing_server_default=sa.func.now(),
            server_default=None,
        )
