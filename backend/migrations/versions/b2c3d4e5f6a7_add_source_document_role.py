"""Add source_role to source documents.

Revision ID: b2c3d4e5f6a7
Revises: b1c2d3e4f5a6
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("source_documents", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_role",
                sa.String(length=40),
                server_default="profile",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_source_documents_source_role",
            "source_role IN ('profile', 'narrative', 'goals', 'template_reference')",
        )


def downgrade() -> None:
    with op.batch_alter_table("source_documents", schema=None) as batch_op:
        batch_op.drop_constraint("ck_source_documents_source_role", type_="check")
        batch_op.drop_column("source_role")
