"""Remove the obsolete remote identity column.

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-07-17
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, None] = "t0u1v2w3x4y5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_users_supabase_id", table_name="users")
    with op.batch_alter_table("users", recreate="always") as batch_op:
        batch_op.drop_column("supabase_id")


def downgrade() -> None:
    op.add_column("users", sa.Column("supabase_id", sa.String(), nullable=True))
    op.create_index("ix_users_supabase_id", "users", ["supabase_id"], unique=True)
