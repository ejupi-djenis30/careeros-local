"""Add durable per-application dossier drafts.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | Sequence[str] | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_dossier_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("application_id", sa.String(length=36), nullable=False),
        sa.Column("resume_version_id", sa.String(length=36), nullable=False),
        sa.Column("application_revision", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("application_revision >= 1", name="ck_dossier_draft_application_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_dossier_draft_revision"),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resume_version_id"],
            ["resume_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "application_id",
            name="uq_application_dossier_draft_application",
        ),
    )
    op.create_index(
        "ix_application_dossier_drafts_resume_version_id",
        "application_dossier_drafts",
        ["resume_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_application_dossier_drafts_resume_version_id",
        table_name="application_dossier_drafts",
    )
    op.drop_table("application_dossier_drafts")
