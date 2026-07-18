"""Add the application-list covering index.

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op

revision: str = "y5z6a7b8c9d0"
down_revision: Union[str, None] = "x4y5z6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_applications_user_updated_at",
        "applications",
        ["user_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_applications_user_updated_at", table_name="applications")
