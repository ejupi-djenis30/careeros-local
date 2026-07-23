"""Add user-facing names to immutable resume versions.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("resume_versions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "name",
                sa.String(length=200),
                nullable=False,
                server_default=sa.text("'Published version'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("resume_versions") as batch_op:
        batch_op.drop_column("name")
