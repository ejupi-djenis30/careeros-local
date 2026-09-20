"""Add campaign workspace tables.

Revision ID: c0a1b2c3d4e5
Revises: b3c4d5e6f7a9
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c0a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "b3c4d5e6f7a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("name_integrity", sa.String(length=64), nullable=True),
        sa.Column("tracker_sha256", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_campaigns_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "source_fingerprint",
            name="uq_campaigns_user_fingerprint",
        ),
    )
    op.create_index("ix_campaigns_user_id", "campaigns", ["user_id"], unique=False)
    op.create_index(
        "ix_campaigns_user_created_at",
        "campaigns",
        ["user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "campaign_applications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("application_id", sa.String(length=36), nullable=False),
        sa.Column("source_application_id", sa.String(length=120), nullable=False),
        sa.Column("source_order", sa.Integer(), nullable=False),
        sa.Column("source_status", sa.String(length=60), nullable=True),
        sa.Column("priority", sa.String(length=60), nullable=True),
        sa.Column("platform", sa.String(length=120), nullable=True),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("outcome", sa.String(length=120), nullable=True),
        sa.Column("found_at", sa.Date(), nullable=True),
        sa.Column("applied_at", sa.Date(), nullable=True),
        sa.Column("follow_up_at", sa.Date(), nullable=True),
        sa.Column("last_update_at", sa.Date(), nullable=True),
        sa.Column("tracker_record", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name="fk_campaign_applications_campaign_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_campaign_applications_application_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "source_application_id",
            name="uq_campaign_app_campaign_source_id",
        ),
        sa.UniqueConstraint(
            "campaign_id",
            "application_id",
            name="uq_campaign_app_campaign_app_id",
        ),
    )
    op.create_index(
        "ix_campaign_applications_campaign_id",
        "campaign_applications",
        ["campaign_id"],
        unique=False,
    )
    op.create_index(
        "ix_campaign_applications_application_id",
        "campaign_applications",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        "ix_campaign_applications_campaign_source_order",
        "campaign_applications",
        ["campaign_id", "source_order"],
        unique=False,
    )
    op.create_index(
        "ix_campaign_applications_campaign_priority",
        "campaign_applications",
        ["campaign_id", "priority"],
        unique=False,
    )

    op.create_table(
        "campaign_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("application_id", sa.String(length=36), nullable=True),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("relative_path", sa.String(length=500), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("source_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('tracker', 'profile', 'goal', 'story', 'template', "
            "'vacancy', 'cv', 'letter', 'email', 'evidence', 'image', 'script', 'other')",
            name="ck_campaign_artifacts_category",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name="fk_campaign_artifacts_campaign_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_campaign_artifacts_application_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["career_assets.id"],
            name="fk_campaign_artifacts_asset_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "relative_path",
            name="uq_campaign_artifacts_campaign_path",
        ),
    )
    op.create_index(
        "ix_campaign_artifacts_campaign_id",
        "campaign_artifacts",
        ["campaign_id"],
        unique=False,
    )
    op.create_index(
        "ix_campaign_artifacts_application_id",
        "campaign_artifacts",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        "ix_campaign_artifacts_asset_id",
        "campaign_artifacts",
        ["asset_id"],
        unique=False,
    )
    op.create_index(
        "ix_campaign_artifacts_campaign_source_order",
        "campaign_artifacts",
        ["campaign_id", "source_order"],
        unique=False,
    )


def downgrade() -> None:
    connection = op.get_bind()
    for table_name in ("campaign_artifacts", "campaign_applications", "campaigns"):
        count = connection.execute(
            sa.text(f"SELECT COUNT(*) FROM {table_name}")
        ).scalar_one()
        if count:
            raise RuntimeError(
                "Cannot downgrade schema while campaign rows exist"
            )

    op.drop_index(
        "ix_campaign_artifacts_campaign_source_order",
        table_name="campaign_artifacts",
    )
    op.drop_index("ix_campaign_artifacts_asset_id", table_name="campaign_artifacts")
    op.drop_index(
        "ix_campaign_artifacts_application_id",
        table_name="campaign_artifacts",
    )
    op.drop_index("ix_campaign_artifacts_campaign_id", table_name="campaign_artifacts")
    op.drop_table("campaign_artifacts")

    op.drop_index(
        "ix_campaign_applications_campaign_priority",
        table_name="campaign_applications",
    )
    op.drop_index(
        "ix_campaign_applications_campaign_source_order",
        table_name="campaign_applications",
    )
    op.drop_index(
        "ix_campaign_applications_application_id",
        table_name="campaign_applications",
    )
    op.drop_index(
        "ix_campaign_applications_campaign_id",
        table_name="campaign_applications",
    )
    op.drop_table("campaign_applications")

    op.drop_index("ix_campaigns_user_created_at", table_name="campaigns")
    op.drop_index("ix_campaigns_user_id", table_name="campaigns")
    op.drop_table("campaigns")
