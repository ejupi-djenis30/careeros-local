"""Add user-owned installed job-provider configurations.

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b0c1d2e3f4a5"
down_revision: str | Sequence[str] | None = "a9b0c1d2e3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_provider_configurations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("adapter_kind", sa.String(length=16), nullable=False),
        sa.Column("native_adapter_id", sa.String(length=64), nullable=True),
        sa.Column("source_pack_id", sa.String(length=160), nullable=True),
        sa.Column("source_pack_version", sa.String(length=64), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("request_config", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("extraction_config", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("capabilities_config", sa.JSON(), nullable=False),
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
        sa.CheckConstraint("revision >= 1", name="ck_job_provider_configuration_revision"),
        sa.CheckConstraint(
            "((adapter_kind IN ('json', 'html') AND native_adapter_id IS NULL "
            "AND request_config IS NOT NULL AND extraction_config IS NOT NULL) OR "
            "(adapter_kind = 'native' AND native_adapter_id IS NOT NULL "
            "AND request_config IS NULL AND extraction_config IS NULL))",
            name="ck_job_provider_configuration_adapter_kind",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_job_provider_configuration_user_key"),
    )
    op.create_index(
        "ix_job_provider_configurations_user_id",
        "job_provider_configurations",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_job_provider_configurations_user_enabled",
        "job_provider_configurations",
        ["user_id", "enabled"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_job_provider_configurations_user_enabled",
        table_name="job_provider_configurations",
    )
    op.drop_index(
        "ix_job_provider_configurations_user_id",
        table_name="job_provider_configurations",
    )
    op.drop_table("job_provider_configurations")
