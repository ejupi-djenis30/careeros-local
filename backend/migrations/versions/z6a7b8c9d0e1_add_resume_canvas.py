"""Add versioned resume canvas documents.

Revision ID: z6a7b8c9d0e1
Revises: y5z6a7b8c9d0
Create Date: 2026-07-17
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "z6a7b8c9d0e1"
down_revision: Union[str, None] = "y5z6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("resume_drafts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "canvas_document", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
            )
        )
        batch_op.add_column(
            sa.Column(
                "generation_context", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("resume_drafts") as batch_op:
        batch_op.drop_column("generation_context")
        batch_op.drop_column("canvas_document")
