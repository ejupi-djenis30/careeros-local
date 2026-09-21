"""Add application materials, draft binding, and packet artifacts.

Revision ID: b3c4d5e6f7a9
Revises: b2c3d4e5f6a7
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Note: Reserved ID in coordinator notes was b3c4d5e6f7a8, but b3c4d5e6f7a8 was
# already assigned to historical revision b3c4d5e6f7a8_add_missing_columns.py.
# Using b3c4d5e6f7a9 to ensure uniqueness without mutating historical migrations.
revision: str = "b3c4d5e6f7a9"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("application_dossier_drafts", schema=None) as batch_op:
        batch_op.alter_column(
            "resume_version_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column(
                "resume_draft_id",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "resume_draft_revision",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.create_index(
            "ix_application_dossier_drafts_resume_draft_id",
            ["resume_draft_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_application_dossier_drafts_resume_draft_id",
            "resume_drafts",
            ["resume_draft_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_check_constraint(
            "ck_dossier_draft_binding",
            "(resume_draft_id IS NOT NULL AND resume_version_id IS NULL) OR "
            "(resume_draft_id IS NULL AND resume_version_id IS NOT NULL)",
        )
        batch_op.create_check_constraint(
            "ck_dossier_draft_binding_revision",
            "(resume_draft_id IS NOT NULL AND resume_draft_revision IS NOT NULL "
            "AND resume_draft_revision >= 1) OR "
            "(resume_draft_id IS NULL AND resume_draft_revision IS NULL)",
        )

    op.create_table(
        "application_packet_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("application_id", sa.String(length=36), nullable=False),
        sa.Column("dossier_id", sa.String(length=36), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column(
            "media_type",
            sa.String(length=100),
            server_default="application/zip",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_application_packet_artifacts_application_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "application_id",
            "dossier_id",
            name="uq_application_packet_artifact_dossier",
        ),
    )
    op.create_index(
        "ix_application_packet_artifacts_application_id",
        "application_packet_artifacts",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_packet_artifacts_dossier_id",
        "application_packet_artifacts",
        ["dossier_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_packet_artifacts_app_dossier",
        "application_packet_artifacts",
        ["application_id", "dossier_id"],
        unique=False,
    )


def downgrade() -> None:
    connection = op.get_bind()
    draft_bound_count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM application_dossier_drafts "
            "WHERE resume_draft_id IS NOT NULL"
        )
    ).scalar_one()
    packet_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM application_packet_artifacts")
    ).scalar_one()
    if draft_bound_count or packet_count:
        raise RuntimeError(
            "Cannot downgrade application materials while unpublished draft bindings "
            "or enhanced packet artifacts exist"
        )

    op.drop_index(
        "ix_application_packet_artifacts_app_dossier",
        table_name="application_packet_artifacts",
    )
    op.drop_index(
        "ix_application_packet_artifacts_dossier_id",
        table_name="application_packet_artifacts",
    )
    op.drop_index(
        "ix_application_packet_artifacts_application_id",
        table_name="application_packet_artifacts",
    )
    op.drop_table("application_packet_artifacts")

    with op.batch_alter_table("application_dossier_drafts", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_dossier_draft_binding_revision",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_dossier_draft_binding",
            type_="check",
        )
        batch_op.drop_constraint(
            "fk_application_dossier_drafts_resume_draft_id",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_application_dossier_drafts_resume_draft_id")
        batch_op.drop_column("resume_draft_revision")
        batch_op.drop_column("resume_draft_id")
        batch_op.alter_column(
            "resume_version_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
