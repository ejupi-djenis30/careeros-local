"""Add template preset ID, version, and locale to resume drafts and versions.

Revision ID: b1c2d3e4f5a6
Revises: b0c1d2e3f4a5
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "b0c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("resume_drafts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("template_id", sa.String(length=64), server_default="software-en", nullable=False)
        )
        batch_op.add_column(
            sa.Column("template_version", sa.Integer(), server_default="1", nullable=False)
        )
        batch_op.add_column(
            sa.Column("locale", sa.String(length=8), server_default="en", nullable=False)
        )

    with op.batch_alter_table("resume_versions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("template_id", sa.String(length=64), server_default="software-en", nullable=False)
        )
        batch_op.add_column(
            sa.Column("template_version", sa.Integer(), server_default="1", nullable=False)
        )
        batch_op.add_column(
            sa.Column("locale", sa.String(length=8), server_default="en", nullable=False)
        )

    # Backfill legacy records based on legacy template_kind
    op.execute(
        sa.text(
            "UPDATE resume_drafts SET template_id = 'swiss-software-en', locale = 'en' WHERE template_kind = 'photo'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE resume_drafts SET template_id = 'software-en', locale = 'en' WHERE template_kind = 'ats'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE resume_versions SET template_id = 'swiss-software-en', locale = 'en' WHERE template_kind = 'photo'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE resume_versions SET template_id = 'software-en', locale = 'en' WHERE template_kind = 'ats'"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("resume_versions", schema=None) as batch_op:
        batch_op.drop_column("locale")
        batch_op.drop_column("template_version")
        batch_op.drop_column("template_id")

    with op.batch_alter_table("resume_drafts", schema=None) as batch_op:
        batch_op.drop_column("locale")
        batch_op.drop_column("template_version")
        batch_op.drop_column("template_id")
